#!/usr/bin/env python3
"""Merge hand-written reviews into data.js.

Reads data.js (produced by scrape.py), attaches per-item fields from
explanations/<variant>.json ("review", "flag") and
explanations/official_<variant>.json ("official"), sorts variants by kind and
writes data.js back. Safe to run repeatedly.

    .venv/bin/python build.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data.js"
EXPL = ROOT / "explanations"
PATCHES = ROOT / "patches.json"
JS_PREFIX = "window.TZNK_DATA = "
KIND_ORDER = {"training": 0, "official": 1, "session": 2, "other": 3}


def load_data() -> dict:
    raw = DATA.read_text(encoding="utf-8")
    return json.loads(raw[len(JS_PREFIX):].rstrip().rstrip(";"))


def save_data(data: dict) -> None:
    DATA.write_text(JS_PREFIX + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
                    encoding="utf-8")


def apply_patches(data: dict) -> int:
    """Fix defects of the source pages listed in patches.json."""
    if not PATCHES.exists():
        return 0
    patches = {k: v for k, v in json.loads(PATCHES.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    applied = 0
    for v in data["variants"]:
        for it in v["items"]:
            patch = patches.get(f"{v['id']}:{it['n']}")
            if not patch:
                continue
            for letter, html in patch.get("answers", {}).items():
                for a in it["answers"]:
                    if a["letter"] == letter:
                        a["html"] = html
            for field in ("question", "passage", "correct"):
                if field in patch:
                    it[field] = patch[field]
            for old, new in patch.get("replace", []):
                it["question"] = it["question"].replace(old, new)
                it["explanation"] = it["explanation"].replace(old, new)
                # The passage is shared by every item of the group.
                for sib in v["items"]:
                    if sib.get("group") and sib["group"] == it.get("group") or sib is it:
                        sib["passage"] = sib["passage"].replace(old, new)
            applied += 1
    return applied


LATEX = [
    (re.compile(r"\\frac\s*\{([^}]*)\}\s*\{([^}]*)\}"), r"\1/\2"),
    (re.compile(r"\\frac\s*(\d)(\d)"), r"\1/\2"),
    (re.compile(r"\s*\^\\circ\s*\\mathrm\{C\}"), " °C"),
    (re.compile(r"\\cdot"), "·"), (re.compile(r"\\forall"), "∀"), (re.compile(r"\\exists"), "∃"),
    (re.compile(r"\\Rightarrow"), " ⇒ "), (re.compile(r"\\neg\s*"), "¬"), (re.compile(r"\\ "), " "),
    (re.compile(r"\s{2,}"), " "),
]


def delatex(html: str) -> str:
    """The source wraps numbers and fractions in MathJax \\( ... \\); the app has
    no math renderer, so turn them into plain text."""
    def inner(m):
        t = m.group(1)
        for rx, rep in LATEX:
            t = rx.sub(rep, t)
        return t.strip()
    return re.sub(r"\\\((.*?)\\\)", inner, html)


def merge(data: dict) -> list[str]:
    notes = [f"patches applied: {apply_patches(data)}"]
    for v in data["variants"]:
        for it in v["items"]:
            for f in ("question", "passage", "explanation"):
                it[f] = delatex(it[f])
            for a in it["answers"]:
                a["html"] = delatex(a["html"])
    for v in data["variants"]:
        vid = v["id"]
        review_file = EXPL / f"{vid}.json"
        official_file = EXPL / f"official_{vid}.json"
        reviews = json.loads(review_file.read_text(encoding="utf-8"))["items"] if review_file.exists() else {}
        official = json.loads(official_file.read_text(encoding="utf-8"))["items"] if official_file.exists() else {}
        missing, flagged = [], []
        for it in v["items"]:
            key = str(it["n"])
            r = reviews.get(key)
            if r and r.get("review"):
                it["review"] = r["review"]
                if r.get("flag"):
                    it["flag"] = r["flag"]
                    flagged.append(key)
                else:
                    it.pop("flag", None)
            else:
                it.pop("review", None)
                missing.append(key)
            if official.get(key):
                it["official"] = official[key]
            else:
                it.pop("official", None)
        notes.append(f"{vid} {v['title']}: reviews {len(v['items']) - len(missing)}/{len(v['items'])}"
                     + (f", missing {','.join(missing)}" if missing and reviews else "")
                     + (f", flagged {','.join(flagged)}" if flagged else "")
                     + (f", official {len(official)}" if official else ""))
    data["variants"].sort(key=lambda v: (KIND_ORDER.get(v.get("kind", "other"), 9), v["id"]))
    return notes


def main() -> None:
    data = load_data()
    notes = merge(data)
    save_data(data)
    print("\n".join(notes))


if __name__ == "__main__":
    sys.exit(main())
