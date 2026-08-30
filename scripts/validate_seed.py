#!/usr/bin/env python3
"""Validate seed_data/ before baking: required fields, unique ids, sane values."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SEED = Path(__file__).parent.parent / "seed_data"
REQUIRED = ("id", "name", "description")


def main() -> None:
    if not SEED.exists():
        sys.exit(f"No seed_data/ at {SEED}")
    seen: dict[str, Path] = {}
    errors: list[str] = []
    total = 0
    for jf in sorted(SEED.rglob("*.json")):
        if jf.name.startswith("_"):
            continue
        try:
            loaded = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{jf}: invalid JSON ({exc})")
            continue
        entities = loaded if isinstance(loaded, list) else [loaded]
        for i, e in enumerate(entities):
            if not isinstance(e, dict):
                errors.append(f"{jf}[{i}]: not an object")
                continue
            total += 1
            for field in REQUIRED:
                if not str(e.get(field) or "").strip():
                    errors.append(f"{jf}[{i}]: missing {field!r}")
            eid = str(e.get("id") or "")
            if eid in seen:
                errors.append(f"{jf}[{i}]: duplicate id {eid!r} (also in {seen[eid].name})")
            elif eid:
                seen[eid] = jf
            desc = str(e.get("description") or "")
            if desc and len(desc) < 60:
                errors.append(f"{jf}[{i}] {eid}: description too short ({len(desc)} chars)")
    if errors:
        print(f"{len(errors)} problem(s) in {total} entities:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    print(f"OK: {total} entities, {len(seen)} unique ids, all required fields present.")


if __name__ == "__main__":
    main()
