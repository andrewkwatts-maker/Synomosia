"""The conspiracy collections must stay namespaced.

synomosia syncs deltas out of the shared `eyesofazrael` Firestore project,
which already holds azrael's mythology documents under `events`, `figures` and
`concepts`. Dropping the `con_` prefix from any collection would not fail —
it would quietly merge mythology deities and their events into the conspiracy
database on the next Refresh(). That is the regression this file guards.
"""
import re
from pathlib import Path

from synomosia._query import (
    CONSPIRACY_COLLECTIONS,
    _COLLECTION_TYPES,
    _DEFAULT_PROJECT,
)

# Names that exist unprefixed in the shared project and belong to other
# domains. None of these may ever appear in a synomosia collection list.
COLLIDING_NAMES = {"events", "figures", "concepts", "artifacts"}

EXPECTED = [
    "con_theories", "con_figures", "con_organizations", "con_events",
    "con_documents", "con_concepts",
]


def test_collections_are_exactly_the_prefixed_set():
    assert CONSPIRACY_COLLECTIONS == EXPECTED


def test_every_collection_is_prefixed():
    for coll in CONSPIRACY_COLLECTIONS:
        assert coll.startswith("con_"), coll


def test_no_unprefixed_colliding_name_can_appear():
    assert COLLIDING_NAMES.isdisjoint(CONSPIRACY_COLLECTIONS)
    for coll in CONSPIRACY_COLLECTIONS:
        tail = re.split(r"[^a-z]", coll)[-1]
        assert not (tail in COLLIDING_NAMES and not coll.startswith("con_")), coll


def test_collection_types_cover_every_collection():
    assert set(_COLLECTION_TYPES) == set(CONSPIRACY_COLLECTIONS)


def test_collection_types_map_onto_the_local_entity_types():
    """The prefix is a Firestore namespace only — baked rows and queries use
    the bare type, so a delta must land under the bare type too."""
    assert _COLLECTION_TYPES == {
        "con_theories": "theory",
        "con_figures": "figure",
        "con_organizations": "organization",
        "con_events": "event",
        "con_documents": "document",
        "con_concepts": "concept",
    }
    for entity_type in _COLLECTION_TYPES.values():
        assert not entity_type.startswith("con_")


def test_bake_script_targets_the_same_prefixed_collections():
    """A re-bake must read the same collections Refresh() does."""
    # Read rather than import: scripts/bake.py has bake-only dependencies.
    src = (Path(__file__).resolve().parents[1] / "scripts" / "bake.py").read_text(
        encoding="utf-8"
    )
    assert 'REMOTE_PREFIX = "con_"' in src
    assert "REMOTE_PREFIX + col_name" in src


# ── the project default ───────────────────────────────────────────────────────

def test_default_project_is_the_shared_one():
    assert _DEFAULT_PROJECT == "eyesofazrael"


def _record_sync(monkeypatch, seen: dict) -> None:
    """Capture what Refresh() asks the eyecore delta layer for."""
    import synomosia._query as q_mod

    def fake_sync(project, collections, collection_types, api_key=""):
        seen["project"] = project
        seen["collections"] = list(collections)
        seen["types"] = dict(collection_types)
        return 0

    monkeypatch.setattr(q_mod._db, "sync_deltas", fake_sync)


def test_refresh_uses_the_default_project_when_the_env_var_is_unset(monkeypatch):
    monkeypatch.delenv("AUGUR_PROJECT", raising=False)
    seen = {}
    _record_sync(monkeypatch, seen)
    from synomosia._query import Refresh

    assert Refresh() == 0
    assert seen["project"] == "eyesofazrael"
    assert seen["collections"] == EXPECTED


def test_env_var_still_overrides_the_project(monkeypatch):
    monkeypatch.setenv("AUGUR_PROJECT", "augur-isolated")
    seen = {}
    _record_sync(monkeypatch, seen)
    from synomosia._query import Refresh

    Refresh()
    assert seen["project"] == "augur-isolated"


def test_empty_env_var_falls_back_rather_than_querying_nothing(monkeypatch):
    """An empty override used to short-circuit Refresh() to a no-op 0."""
    monkeypatch.setenv("AUGUR_PROJECT", "")
    seen = {}
    _record_sync(monkeypatch, seen)
    from synomosia._query import Refresh

    Refresh()
    assert seen["project"] == "eyesofazrael"
