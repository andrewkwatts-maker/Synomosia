#!/usr/bin/env python3
"""Bake news data into augur.db (SQLite) via the Firestore REST API.

Usage:
    python scripts/bake.py                          # pull from Firebase
    python scripts/bake.py --source /path/to/dir   # use local JSON export
    python scripts/bake.py --project PROJECT_ID --api-key KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Install bake deps: pip install 'augur[bake]'")

ROOT = Path(__file__).parent.parent
DATA_OUT = ROOT / "src" / "augur" / "_data" / "augur.db"

# Set AUGUR_PROJECT and AUGUR_API_KEY env vars when the Firebase project is ready
DEFAULT_PROJECT = os.getenv("AUGUR_PROJECT", "")
DEFAULT_API_KEY = os.getenv("AUGUR_API_KEY", os.getenv("FIREBASE_API_KEY", ""))

COLLECTIONS: dict[str, str] = {
    "articles": "article",
    "topics": "topic",
    "trends": "trend",
    "sources": "source",
    "events": "event",
}

TYPE_FIXES: dict[str, str] = {}

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
"""


# ── Firestore REST helpers ────────────────────────────────────────────────────

def _parse_value(val: dict):
    if "stringValue" in val:
        return val["stringValue"]
    if "integerValue" in val:
        return int(val["integerValue"])
    if "doubleValue" in val:
        return float(val["doubleValue"])
    if "booleanValue" in val:
        return val["booleanValue"]
    if "nullValue" in val:
        return None
    if "timestampValue" in val:
        return val["timestampValue"]
    if "arrayValue" in val:
        return [_parse_value(v) for v in val["arrayValue"].get("values", [])]
    if "mapValue" in val:
        return {k: _parse_value(v) for k, v in val["mapValue"].get("fields", {}).items()}
    return None


def _doc_to_dict(doc: dict) -> dict:
    result = {k: _parse_value(v) for k, v in doc.get("fields", {}).items()}
    result["id"] = doc["name"].rsplit("/", 1)[-1]
    return result


def _fetch_collection(session: requests.Session, base_url: str,
                      collection: str, api_key: str) -> list[dict]:
    url = f"{base_url}/{collection}"
    docs: list[dict] = []
    page_token: str | None = None
    while True:
        params: dict = {"key": api_key, "pageSize": 300}
        if page_token:
            params["pageToken"] = page_token
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for doc in data.get("documents", []):
            docs.append(_doc_to_dict(doc))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return docs


# ── DB helpers ────────────────────────────────────────────────────────────────

def _coerce_type(raw: str | None, fallback: str) -> str:
    if not raw:
        return fallback
    return TYPE_FIXES.get(raw, raw)


def _str_list(val) -> str:
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v)
    return str(val)


def _domains_text(e: dict) -> str:
    parts = [
        _str_list(e.get("tags")),
        _str_list(e.get("categories")),
        _str_list(e.get("keywords")),
    ]
    return " ".join(p for p in parts if p).lower()


def _search_text(e: dict) -> str:
    parts = [
        e.get("name", "") or e.get("title", ""),
        e.get("category", ""),
        e.get("description") or e.get("summary") or e.get("content", ""),
        _str_list(e.get("tags")),
        _str_list(e.get("keywords")),
    ]
    return " ".join(p for p in parts if p)


def _init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(str(db_path))
    for stmt in CREATE_SQL.strip().split(";"):
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
    db.executemany(
        "INSERT INTO entities_fts(id, search_text) VALUES (?,?)",
        fts_rows,
    )
    db.commit()


# ── Bake functions ────────────────────────────────────────────────────────────

def bake_from_firebase(db_path: Path, project_id: str, api_key: str) -> None:
    if not project_id or not api_key:
        sys.exit(
            "Firebase project pending. Set AUGUR_PROJECT and AUGUR_API_KEY env vars, "
            "or pass --project and --api-key."
        )
    base = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents"
    session = requests.Session()
    db = _init_db(db_path)
    total = 0
    for col_name, entity_type in COLLECTIONS.items():
        print(f"  {col_name}...", end=" ", flush=True)
        try:
            entities = _fetch_collection(session, base, col_name, api_key)
        except requests.HTTPError as exc:
            print(f"SKIP ({exc.response.status_code})")
            continue
        rows, fts_rows = [], []
        for e in entities:
            eid = e.get("id") or ""
            if not eid:
                continue
            etype = _coerce_type(e.get("type"), entity_type)
            e["type"] = etype
            name = e.get("name") or e.get("title") or eid
            e.setdefault("name", name)
            category = e.get("category")
            srch = _search_text(e)
            rows.append((eid, name, etype, category, _domains_text(e), srch,
                         json.dumps(e, ensure_ascii=False)))
            fts_rows.append((eid, srch))
        _insert_batch(db, rows, fts_rows)
        print(len(rows))
        total += len(rows)
    size = db_path.stat().st_size / 1_048_576
    print(f"\nDone: {total} entities → {db_path} ({size:.1f} MB)")
    db.close()


def bake_from_local(source_dir: Path, db_path: Path) -> None:
    if not source_dir.exists():
        sys.exit(f"Source not found: {source_dir}")
    db = _init_db(db_path)
    total = 0
    for col_name, entity_type in COLLECTIONS.items():
        col_dir = source_dir / col_name
        if not col_dir.exists():
            print(f"  SKIP {col_name} (not found)")
            continue
        files = [f for f in col_dir.glob("*.json") if not f.name.startswith("_")]
        print(f"  {col_name}: {len(files)} → {entity_type}")
        rows, fts_rows = [], []
        for jf in files:
            try:
                e = json.loads(jf.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            eid = e.get("id") or jf.stem
            e["id"] = eid
            etype = _coerce_type(e.get("type"), entity_type)
            e["type"] = etype
            name = e.get("name") or e.get("title") or eid
            e.setdefault("name", name)
            category = e.get("category")
            srch = _search_text(e)
            rows.append((eid, name, etype, category, _domains_text(e), srch,
                         json.dumps(e, ensure_ascii=False)))
            fts_rows.append((eid, srch))
        _insert_batch(db, rows, fts_rows)
        total += len(rows)
    size = db_path.stat().st_size / 1_048_576
    print(f"\nDone: {total} entities → {db_path} ({size:.1f} MB)")
    db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bake news data into augur.db")
    parser.add_argument("--source", metavar="DIR", help="Local JSON export directory (skips Firebase)")
    parser.add_argument("--project", default=DEFAULT_PROJECT, metavar="ID",
                        help="Firebase project ID (or set AUGUR_PROJECT)")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, metavar="KEY",
                        help="Firebase public API key (or set AUGUR_API_KEY)")
    parser.add_argument("--out", default=str(DATA_OUT), metavar="PATH")
    args = parser.parse_args()
    out = Path(args.out)
    if args.source:
        bake_from_local(Path(args.source), out)
    else:
        bake_from_firebase(out, args.project, args.api_key)


if __name__ == "__main__":
    main()
