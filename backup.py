#!/usr/bin/env python3
"""Dump every users/* document from Firestore to a dated JSON file.

Spark plan has no scheduled backups, so run this now and then:
    .venv/bin/python backup.py            # -> ~/tznk-backups/users-YYYY-MM-DD.json
Needs `gcloud auth login` as a project owner.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

PROJECT = "tznk-trainer"
OUT_DIR = Path.home() / "tznk-backups"


def token() -> str:
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()


def plain(value: dict):
    """Firestore REST value -> plain Python."""
    (kind, v), = value.items()
    if kind == "mapValue":
        return {k: plain(x) for k, x in (v.get("fields") or {}).items()}
    if kind == "arrayValue":
        return [plain(x) for x in v.get("values") or []]
    if kind == "integerValue":
        return int(v)
    if kind == "nullValue":
        return None
    return v


def main() -> int:
    headers = {"Authorization": f"Bearer {token()}", "x-goog-user-project": PROJECT}
    base = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents/users"
    docs, page = [], None
    while True:
        r = requests.get(base, headers=headers, params={"pageSize": 100, "pageToken": page}, timeout=60)
        r.raise_for_status()
        body = r.json()
        for d in body.get("documents", []):
            docs.append({"uid": d["name"].rsplit("/", 1)[1], "updateTime": d.get("updateTime"),
                         **{k: plain(v) for k, v in d.get("fields", {}).items()}})
        page = body.get("nextPageToken")
        if not page:
            break
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"users-{time.strftime('%Y-%m-%d')}.json"
    out.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
    for d in docs:
        print(f"{d.get('email', d['uid'])}: attempts {len(d.get('attempts') or [])}, sessions {len(d.get('sessions') or [])}, "
              f"drill {len(d.get('drill') or {})}, errors {len(d.get('errors') or {})}, updated {d['updateTime']}")
    print(f"wrote {out} ({out.stat().st_size} B, {len(docs)} users)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
