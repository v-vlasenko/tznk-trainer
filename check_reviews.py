#!/usr/bin/env python3
"""Lint explanations/<variant>.json against explanations/SPEC.md.

    .venv/bin/python check_reviews.py            # all files
    .venv/bin/python check_reviews.py 646 647    # selected variants
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPL = ROOT / "explanations"
ALLOWED = {"p", "strong", "em", "ul", "ol", "li", "br", "table", "tr", "td", "th", "sub", "sup", "tbody", "thead"}
# References to options by letter, which break when answers are shuffled.
LETTER_REF = re.compile(r"(варіант(?:и|ом|у|а)?|відповід(?:ь|і|ю))\s+[«\"]?[АБВГ][»\"]?(?![а-яіїєґА-ЯІЇЄҐ])")
BARE_LETTER = re.compile(r"(?<![а-яіїєґА-ЯІЇЄҐa-zA-Z])[БВГ](?![а-яіїєґА-ЯІЇЄҐa-zA-Z0-9])")


def check(path: Path) -> list[str]:
    problems = []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", {})
    keys = {str(i) for i in range(1, 34)}
    if set(items) != keys:
        problems.append(f"keys mismatch: missing {sorted(keys - set(items), key=int)}, extra {sorted(set(items) - keys)}")
    lengths = []
    for k in sorted(items, key=int):
        r = items[k].get("review", "") or ""
        text = re.sub(r"<[^>]+>", " ", r)
        lengths.append(len(text))
        tags = set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", r))
        bad = tags - ALLOWED
        if bad:
            problems.append(f"{k}: disallowed tags {sorted(bad)}")
        if "Відповідь:" not in r:
            problems.append(f"{k}: no 'Відповідь:' line")
        if "Чому інші варіанти" not in r:
            problems.append(f"{k}: no 'Чому інші варіанти' section")
        if "Як розпізнати" not in r:
            problems.append(f"{k}: no 'Як розпізнати' line")
        m = LETTER_REF.search(text)
        if m:
            problems.append(f"{k}: letter reference '{m.group(0)}'")
        if len(text) < 350:
            problems.append(f"{k}: short review ({len(text)} chars)")
        if items[k].get("flag"):
            problems.append(f"{k}: FLAG {items[k]['flag'][:160]}")
    for k, g in (data.get("groups") or {}).items():
        text = re.sub(r"<[^>]+>", " ", g)
        bad = set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", g)) - ALLOWED
        if bad:
            problems.append(f"group {k}: disallowed tags {sorted(bad)}")
        m = LETTER_REF.search(text)
        if m:
            problems.append(f"group {k}: letter reference '{m.group(0)}'")
        if len(text) < 300:
            problems.append(f"group {k}: short setup ({len(text)} chars)")
    if lengths:
        problems.append(f"lengths: min {min(lengths)}, median {sorted(lengths)[len(lengths)//2]}, max {max(lengths)}")
    return problems


def main(argv: list[str]) -> int:
    files = [EXPL / f"{a}.json" for a in argv] if argv else sorted(p for p in EXPL.glob("*.json") if p.stem.isdigit())
    rc = 0
    for f in files:
        if not f.exists():
            print(f"== {f.name}: missing")
            rc = 1
            continue
        problems = check(f)
        print(f"== {f.name}")
        for p in problems:
            print("  " + p)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
