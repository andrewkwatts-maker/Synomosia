#!/usr/bin/env python3
"""Bake conspiracy-theory data into synomosia.db (SQLite).

Primary source is the committed seed data (one JSON per entity, or a JSON
array per file, grouped in per-collection folders):

    python scripts/bake.py --source seed_data

A Firestore source can be used once a conspiracy upstream exists:

    AUGUR_PROJECT=<project> AUGUR_API_KEY=<key> python scripts/bake.py
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

try:
    from eyecore import compress_db, GRAPH_SCHEMA, set_meta
except ImportError:
    sys.exit("eyecore not installed. Run: pip install 'eyecore>=1.1.0'")

ROOT = Path(__file__).parent.parent
DATA_OUT = ROOT / "src" / "synomosia" / "_data" / "synomosia.db"

DEFAULT_PROJECT = os.getenv("AUGUR_PROJECT", "")
DEFAULT_API_KEY = os.getenv("AUGUR_API_KEY", os.getenv("FIREBASE_API_KEY", ""))

# Collection -> entity type. Must match synomosia's public API
# (GetTheory / GetFigure / GetOrganization / GetEvent / GetDocument / GetConcept).
COLLECTIONS: dict[str, str] = {
    "theories": "theory",
    "figures": "figure",
    "organizations": "organization",
    "events": "event",
    "documents": "document",
    "concepts": "concept",
}

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    mythology TEXT,
    domains_text TEXT,
    search_text TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_name ON entities(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_mythology ON entities(mythology COLLATE NOCASE);
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id UNINDEXED,
    search_text,
    tokenize='unicode61 remove_diacritics 1'
);
CREATE TABLE IF NOT EXISTS entity_topics (
    entity_id  TEXT NOT NULL REFERENCES entities(id),
    topic_id   TEXT NOT NULL REFERENCES topics(id),
    weight     REAL DEFAULT 1.0,
    PRIMARY KEY (entity_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_entity_topics_entity ON entity_topics(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_topics_topic  ON entity_topics(topic_id);
"""


# ── Row helpers ───────────────────────────────────────────────────────────────

def _str_list(val) -> str:
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v)
    return str(val)


def _safe_str(val) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        return _str_list(val)
    return ""


def _domains_text(e: dict) -> str:
    parts = [
        _str_list(e.get("tags")),
        _str_list(e.get("themes")),
        _safe_str(e.get("status")),
        _safe_str(e.get("origin")),
    ]
    return " ".join(p for p in parts if p).lower()


def _search_text(e: dict) -> str:
    desc = e.get("description") or e.get("summary") or ""
    parts = [
        _safe_str(e.get("name", "")),
        _safe_str(e.get("category") or ""),
        _safe_str(desc),
        _safe_str(e.get("claim") or ""),
        _safe_str(e.get("origin") or ""),
        _safe_str(e.get("status") or ""),
        _str_list(e.get("tags")),
        _str_list(e.get("aliases")),
        _str_list(e.get("related")),
    ]
    return " ".join(p for p in parts if p)


def _entity_row(e: dict, fallback_type: str) -> tuple:
    eid = str(e.get("id") or "").strip()
    etype = e.get("type") or fallback_type
    e["type"] = etype
    name = e.get("name") or eid
    category = _safe_str(e.get("category") or "").lower() or None
    srch = _search_text(e)
    return (eid, name, etype, category, _domains_text(e), srch,
            json.dumps(e, ensure_ascii=False))


# ── DB setup / topic graph ────────────────────────────────────────────────────

def _init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(str(db_path))
    for block in (GRAPH_SCHEMA, CREATE_SQL):
        for stmt in block.strip().split(";"):
            s = stmt.strip()
            if s:
                db.execute(s)
    db.commit()
    return db


def _insert_batch(db: sqlite3.Connection, rows: list, fts_rows: list) -> None:
    db.executemany(
        "INSERT OR REPLACE INTO entities"
        "(id, name, type, mythology, domains_text, search_text, data) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    db.executemany("INSERT INTO entities_fts(id, search_text) VALUES (?,?)", fts_rows)
    db.commit()


def _build_topic_graph(db: sqlite3.Connection, all_rows: list[tuple]) -> None:
    from eyecore import TopicGraph

    graph = TopicGraph(db)
    categories: set[str] = set()
    types: set[str] = set()
    for row in all_rows:
        if row[3]:
            categories.add(row[3])
        types.add(row[2])
    for cat in sorted(categories):
        graph.upsert_topic(f"cat:{cat}", cat.title(), type="category",
                           description=f"Conspiracy category: {cat.title()}")
    for t in sorted(types):
        graph.upsert_topic(f"type:{t}", t.title(), type="entity_type",
                           description=f"Entity type: {t}")
    links = []
    for row in all_rows:
        if row[3]:
            links.append((row[0], f"cat:{row[3]}", 1.0))
        links.append((row[0], f"type:{row[2]}", 1.0))
    db.executemany(
        "INSERT OR IGNORE INTO entity_topics(entity_id, topic_id, weight) VALUES (?,?,?)",
        links,
    )
    db.commit()
    print(f"  Topics: {len(categories)} categories, {len(types)} types")


def _stamp_generated_at(db: sqlite3.Connection) -> None:
    from datetime import datetime, timezone

    set_meta(db, "generated_at",
             datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


# ── Bake paths ────────────────────────────────────────────────────────────────

def bake_from_local(source_dir: Path, db_path: Path) -> None:
    if not source_dir.exists():
        sys.exit(f"Source not found: {source_dir}")
    db = _init_db(db_path)
    total = 0
    all_rows: list[tuple] = []
    for col_name, entity_type in COLLECTIONS.items():
        col_dir = source_dir / col_name
        if not col_dir.exists():
            print(f"  SKIP {col_name} (not found)")
            continue
        rows, fts_rows = [], []
        for jf in sorted(col_dir.glob("*.json")):
            if jf.name.startswith("_"):
                continue
            try:
                loaded = json.loads(jf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                sys.exit(f"Invalid JSON in {jf}: {exc}")
            entities = loaded if isinstance(loaded, list) else [loaded]
            for e in entities:
                if not isinstance(e, dict):
                    continue
                e.setdefault("id", jf.stem)
                row = _entity_row(e, entity_type)
                if not row[0]:
                    continue
                rows.append(row)
                fts_rows.append((row[0], row[5]))
                all_rows.append(row)
        print(f"  {col_name}: {len(rows)} -> {entity_type}")
        _insert_batch(db, rows, fts_rows)
        total += len(rows)
    size = db_path.stat().st_size / 1_048_576
    print(f"\nDone: {total} entities -> {db_path} ({size:.1f} MB)")
    print("Building topic graph...")
    _build_topic_graph(db, all_rows)
    _stamp_generated_at(db)
    db.close()
    gz = compress_db(db_path)
    print(f"Compressed -> {gz}")


def bake_from_firebase(db_path: Path, project: str, api_key: str) -> None:
    if not project:
        sys.exit(
            "No conspiracy Firestore project exists yet. Bake from the "
            "committed seed data instead:\n    python scripts/bake.py --source seed_data"
        )
    try:
        import requests
    except ImportError:
        sys.exit("Install bake deps: pip install 'synomosia[bake]'")
    import time

    base = (f"https://firestore.googleapis.com/v1/projects/{project}"
            "/databases/(default)/documents")
    session = requests.Session()
    db = _init_db(db_path)
    total = 0
    all_rows: list[tuple] = []
    for col_name, entity_type in COLLECTIONS.items():
        url = f"{base}/{col_name}"
        docs: list[dict] = []
        token: str | None = None
        while True:
            params: dict = {"key": api_key, "pageSize": 300}
            if token:
                params["pageToken"] = token
            for attempt in range(5):
                resp = session.get(url, params=params, timeout=30)
                if resp.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                break
            if resp.status_code != 200:
                print(f"  SKIP {col_name} (HTTP {resp.status_code})")
                docs = []
                break
            data = resp.json()
            from eyecore import doc_to_dict
            docs.extend(doc_to_dict(d) for d in data.get("documents", []))
            token = data.get("nextPageToken")
            if not token:
                break
        rows, fts_rows = [], []
        for e in docs:
            row = _entity_row(e, entity_type)
            if not row[0]:
                continue
            rows.append(row)
            fts_rows.append((row[0], row[5]))
            all_rows.append(row)
        print(f"  {col_name}: {len(rows)} -> {entity_type}")
        _insert_batch(db, rows, fts_rows)
        total += len(rows)
    print(f"\nDone: {total} entities -> {db_path}")
    print("Building topic graph...")
    _build_topic_graph(db, all_rows)
    _stamp_generated_at(db)
    db.close()
    gz = compress_db(db_path)
    print(f"Compressed -> {gz}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bake conspiracy-theory data into synomosia.db"
    )
    parser.add_argument("--source", metavar="DIR",
                        help="Local JSON directory (default source: seed_data)")
    parser.add_argument("--project", default=DEFAULT_PROJECT, metavar="ID",
                        help="Firestore project id (env AUGUR_PROJECT)")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, metavar="KEY")
    parser.add_argument("--out", default=str(DATA_OUT), metavar="PATH")
    args = parser.parse_args()
    out = Path(args.out)
    if args.source:
        bake_from_local(Path(args.source), out)
    elif (ROOT / "seed_data").exists() and not args.project:
        bake_from_local(ROOT / "seed_data", out)
    else:
        bake_from_firebase(out, args.project, args.api_key)


if __name__ == "__main__":
    main()
