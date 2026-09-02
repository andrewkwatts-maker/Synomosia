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

# SHA-256 of the release asset above, verified before the download is cached.
_DATA_SHA256 = "419cfe56e078498f2d7ea5c3109adfaba6611aec24c2b479fc799637268d36b0"

# The whole suite shares one Firestore project so that one sign-in works
# across every domain; collection names are therefore namespaced per domain.
_DEFAULT_PROJECT = "eyesofazrael"

# Conspiracy collections carry the `con_` prefix. This is load-bearing, not
# cosmetic: `events`, `figures` and `concepts` are live mythology collections
# in the same project. Querying them unprefixed would pull azrael's deities
# and their events straight into the conspiracy database. See
# EyesOfAzrael/docs/PLAN-MULTIDOMAIN.md §2.
CONSPIRACY_COLLECTIONS = [
    "con_theories", "con_figures", "con_organizations", "con_events",
    "con_documents", "con_concepts",
]

# Remote collection -> local entity type. The prefix is a Firestore namespace
# only; the baked rows and every query use the bare type.
_COLLECTION_TYPES = {
    "con_theories": "theory", "con_figures": "figure",
    "con_organizations": "organization", "con_events": "event",
    "con_documents": "document", "con_concepts": "concept",
}


class _SynomosiaDB(EntityDB):
    def __init__(self) -> None:
        super().__init__(
            "synomosia", _BASE, None,
            remote_url=_DATA_URL,
            remote_sha256=_DATA_SHA256,
        )


_db = _SynomosiaDB()


def Refresh(api_key: str = "") -> int:
    """Pull entities changed in Firestore since the bake (or last Refresh)
    and merge them into the local database. Returns entities applied.

    Reads the shared `eyesofazrael` project by default. Set `AUGUR_PROJECT` to
    point conspiracy at an isolated project instead.
    """
    import os

    project = os.getenv("AUGUR_PROJECT") or _DEFAULT_PROJECT
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
