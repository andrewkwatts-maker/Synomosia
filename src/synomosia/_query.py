"""Core query engine backed by a baked SQLite database — delegates to EntityDB."""
from __future__ import annotations

from pathlib import Path

from eyecore import EntityDB

_DATA_DIR = Path(__file__).parent / "_data"
_BASE = _DATA_DIR / "synomosia.db.gz"

# Baked snapshot hosted as a GitHub Release asset, downloaded lazily on first
# query. The `mythology` column stores the conspiracy *category*.
_DATA_URL = (
    "https://github.com/andrewkwatts-maker/Synomosia/releases/download/"
    "data-v1.1.0/synomosia.db.gz"
)

CONSPIRACY_COLLECTIONS = [
    "theories", "figures", "organizations", "events", "documents", "concepts",
]

_COLLECTION_TYPES = {
    "theories": "theory", "figures": "figure", "organizations": "organization",
    "events": "event", "documents": "document", "concepts": "concept",
}


class _SynomosiaDB(EntityDB):
    def __init__(self) -> None:
        super().__init__("synomosia", _BASE, None, remote_url=_DATA_URL)


_db = _SynomosiaDB()


def Refresh(api_key: str = "") -> int:
    """Merge Firestore changes since the bake. No conspiracy upstream exists
    yet, so until one is configured this is a fast no-op returning 0."""
    import os

    project = os.getenv("AUGUR_PROJECT", "")
    if not project:
        return 0  # no upstream project yet — the baked seed is authoritative
    return _db.sync_deltas(project, CONSPIRACY_COLLECTIONS, _COLLECTION_TYPES, api_key)


# ── Public thin wrappers ──────────────────────────────────────────────────────

def Get(name: str) -> dict | None:
    return _db.get(name)


def _typed(query: str, *types: str) -> dict | None:
    return _db._typed(query, *types)


def Search(query: str, limit: int = 20) -> list[dict]:
    return _db.search(query, limit)


def ByMythology(mythology: str, limit: int = 500) -> list[dict]:
    return _db.by_mythology(mythology, limit)


def ByCategory(category: str, limit: int = 500) -> list[dict]:
    """All entities in a conspiracy category (stored in the shared
    `mythology` column of the suite schema)."""
    return _db.by_mythology(category, limit)


def ByType(entity_type: str, mythology: str | None = None, limit: int = 500) -> list[dict]:
    return _db.by_type(entity_type, mythology, limit)


def Count(entity_type: str | None = None) -> int:
    return _db.count(entity_type)


def GetRandom(entity_type: str | None = None, mythology: str | None = None) -> dict | None:
    return _db.get_random(entity_type, mythology)


def GetFuzzy(query: str, limit: int = 5) -> list[dict]:
    return _db.get_fuzzy(query, limit)


def GetMost(field: str = "mythology", limit: int = 10) -> list[dict]:
    return _db.get_most(field, limit)


def GetAll(entity_type: str | None = None, mythology: str | None = None) -> list[dict]:
    return _db.get_all(entity_type, mythology)


def GetTopics(query: str | None = None, limit: int = 50) -> list[dict]:
    return _db.get_topics(query, limit)


def GetRelated(name_or_id: str, relation: str | None = None) -> list[dict]:
    return _db.get_related(name_or_id, relation)


def GetTopicTree(root: str) -> dict:
    return _db.get_topic_tree(root)


def SearchCorpus(query: str, corpus: str | None = None, limit: int = 20) -> list[dict]:
    return _db.search_corpus(query, corpus, limit)


def FetchCorpus(name: str) -> str:
    return _db.fetch_corpus(name)


def ListCorpuses() -> list[dict]:
    return _db.list_corpuses()
