"""
synomosia — Conspiracy theories, hidden histories, and suppressed knowledge.

Quick start:
    import synomosia
    theory = synomosia.GetTheory("Illuminati")
    results = synomosia.Search("shadow government")
    orgs = synomosia.ByCategory("government")
"""
from __future__ import annotations

try:
    from ._core import extract_keywords, score_article
    _RUST_CORE = True
except ImportError:
    _RUST_CORE = False

    def extract_keywords(text: str, stop_words: list, top_n: int) -> list:
        stop = set(stop_words)
        counts: dict = {}
        for word in text.split():
            w = "".join(c for c in word if c.isalpha()).lower()
            if len(w) >= 3 and w not in stop:
                counts[w] = counts.get(w, 0) + 1
        pairs = sorted(counts.items(), key=lambda x: -x[1])
        return pairs[:top_n]

    def score_article(title: str, content: str, query: str) -> float:
        q = query.lower()
        t = title.lower()
        if not q:
            return 0.0
        score = 0.0
        if t.startswith(q):
            score += 1000.0
        elif q in t:
            score += 500.0
        if q in content.lower():
            score += 100.0
        return score

from ._query import (
    Get,
    Search,
    ByCategory,
    ByMythology,
    ByType,
    Count,
    GetRandom,
    GetFuzzy,
    GetMost,
    GetAll,
    GetTopics,
    GetRelated,
    GetTopicTree,
    SearchCorpus,
    FetchCorpus,
    ListCorpuses,
    _typed,
)

from ._scraper import (
    add_feed as AddFeed,
    remove_feed as RemoveFeed,
    scrape_all as Scrape,
    load_sources as ListSources,
    add_reddit_sub as AddSubreddit,
)

from ._store import (
    available_days as AvailableDays,
    compress_old_days as Compress,
    data_dir as DataDir,
)

from ._llm_categorizer import (
    categorize_batch as Categorize,
    generate_daily_report as DailyReport,
)


def GetTheory(query: str) -> dict | None:
    """Return a conspiracy theory by name."""
    return _typed(query, "theory")


def GetEvent(query: str) -> dict | None:
    """Return an event by name."""
    return _typed(query, "event")


def GetFigure(query: str) -> dict | None:
    """Return a figure by name."""
    return _typed(query, "figure")


def GetOrganization(query: str) -> dict | None:
    """Return an organization by name."""
    return _typed(query, "organization")


def GetConcept(query: str) -> dict | None:
    """Return a concept by name."""
    return _typed(query, "concept")


def GetDocument(query: str) -> dict | None:
    """Return a document by name."""
    return _typed(query, "document")


__version__ = "1.0.0"

__all__ = [
    # Core query
    "Get",
    "GetTheory",
    "GetEvent",
    "GetFigure",
    "GetOrganization",
    "GetConcept",
    "GetDocument",
    "Search",
    "ByCategory",
    "ByMythology",
    "ByType",
    "Count",
    "GetRandom",
    "GetFuzzy",
    "GetMost",
    "GetAll",
    # Topic graph
    "GetTopics",
    "GetRelated",
    "GetTopicTree",
    # Corpus
    "SearchCorpus",
    "FetchCorpus",
    "ListCorpuses",
    # Scraper
    "AddFeed",
    "RemoveFeed",
    "Scrape",
    "ListSources",
    "AddSubreddit",
    # Store
    "AvailableDays",
    "Compress",
    "DataDir",
    # LLM
    "Categorize",
    "DailyReport",
    "_RUST_CORE",
]
