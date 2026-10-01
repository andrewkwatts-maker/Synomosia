"""Use local LLM to categorize and enrich scraped conspiracy content.

The LLM calls stay in Python -- they are network round trips measured in
seconds. The counting underneath the daily report is Rust: see
:func:`generate_daily_report`.
"""
from __future__ import annotations

from eyecore import LLMClient

from ._backend import top_categories as _top_categories

CONSPIRACY_CATEGORIES = [
    "government-surveillance",
    "secret-societies",
    "false-flag",
    "extraterrestrial",
    "financial-manipulation",
    "medical-coverup",
    "media-control",
    "religion-occult",
    "geopolitical",
    "technology-control",
    "weather-manipulation",
    "historical-revision",
    "assassination",
    "mind-control",
    "new-world-order",
    "other",
]

#: How many category sections a daily report carries, busiest first.
REPORT_SECTIONS = 5


def categorize_article(article: dict) -> dict:
    """Add 'category', 'summary', and 'topics' fields to article dict using LLM."""
    llm = LLMClient.get()
    if not llm.is_available():
        return article
    text = (
        f"{article.get('title', '')}\n"
        f"{article.get('summary', article.get('content', ''))[:1000]}"
    )
    article["category"] = llm.categorize(text, CONSPIRACY_CATEGORIES)
    if not article.get("summary") or len(article.get("summary", "")) < 50:
        article["summary"] = llm.summarize(text, max_words=150)
    article["llm_topics"] = llm.extract_topics(text)
    return article


def categorize_batch(articles: list[dict], verbose: bool = False) -> list[dict]:
    """Categorize a list of articles. Returns enriched list."""
    result = []
    for i, article in enumerate(articles):
        if verbose:
            print(f"  Categorizing {i + 1}/{len(articles)}: {article.get('title', '')[:60]}")
        result.append(categorize_article(article))
    return result


def generate_daily_report(articles: list[dict], date: str) -> str:
    """Generate a daily conspiracy report from all articles for a given date."""
    llm = LLMClient.get()
    if not llm.is_available():
        return f"LLM not available -- {len(articles)} articles scraped on {date}"

    # Ranking used to build a second dict holding every article, purely to
    # take len() of each bucket. Rust counts the category strings instead, and
    # pins the tie order to first appearance so two runs over the same day
    # produce the same sections in the same order. `or "other"` is new: a row
    # whose category was explicitly None used to reach `cat.replace` and raise
    # AttributeError.
    names = [str(a.get("category") or "other") for a in articles]
    by_category: dict[str, list] = {}
    for name, article in zip(names, articles):
        by_category.setdefault(name, []).append(article)

    report_parts = [f"# Conspiracy Intelligence Report -- {date}\n"]
    for cat, _count in _top_categories(names, REPORT_SECTIONS):
        items = by_category[cat]
        section = llm.generate_report(
            items,
            cat,
            title_field="title",
            body_field="summary",
            max_words=300,
        )
        report_parts.append(f"\n## {cat.replace('-', ' ').title()}\n{section}")

    return "\n".join(report_parts)
