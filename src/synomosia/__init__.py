"""
synomosia -- Conspiracy theories, hidden histories, and suppressed knowledge.

Quick start:
    import synomosia
    theory = synomosia.GetTheory("Illuminati")
    results = synomosia.Search("shadow government")
    orgs = synomosia.ByCategory("government")

The per-article hot path -- HTML normalisation, keyword extraction, article
scoring and ranking, article ids, batch deduplication and the daily-report
histogram -- is implemented in the `augur_core` Rust crate and reached through
the compiled `synomosia._core` extension. There is no Python fallback: if the
extension is missing, those functions raise :class:`RustBackendUnavailable`
rather than quietly answering differently. Query, storage, scraping and LLM
orchestration remain Python, because they wait on a socket or a disk.

    import synomosia
    synomosia.assert_rust_backend()   # fail fast if the backend is not live
    synomosia.backend_report()        # or ask what is actually loaded
"""
from __future__ import annotations

from ._backend import (
    PACKAGE_VERSION as __version__,
    RustBackendUnavailable,
    article_id,
    assert_rust_backend,
    backend_report,
    extract_keywords,
    first_occurrences,
    is_rust_backend,
    rank_articles,
    score_article,
    strip_html,
    top_categories,
    version_rust,
    _HAS_RUST,
)

#: Retained spelling of :data:`_HAS_RUST`; it was public in 1.0 and 1.1.
_RUST_CORE = _HAS_RUST

from ._query import (
    Get,
    Search,
    Refresh,
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
    # Imported since 1.1.0 and reachable as `synomosia.Refresh`, but left out
    # of __all__, so `from synomosia import *` and every documentation tool
    # that reads __all__ missed the delta sync entirely.
    "Refresh",
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
    # Rust core
    "article_id",
    "extract_keywords",
    "first_occurrences",
    "rank_articles",
    "score_article",
    "strip_html",
    "top_categories",
    # Backend health
    "RustBackendUnavailable",
    "assert_rust_backend",
    "backend_report",
    "is_rust_backend",
    "version_rust",
    "_HAS_RUST",
    "_RUST_CORE",
]
