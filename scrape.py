#!/usr/bin/env python3
"""Scrape ТЗНК training variants from zno.osvita.ua into data.js.

Usage:
    .venv/bin/python scrape.py            # default variants 646-650
    .venv/bin/python scrape.py 646 647    # explicit variant ids

Each variant page contains all 33 items as <form class="q-test">. The correct
answer is the hidden <input name="result">, the explanation is the
<div id="commentar_<id>"> already present in the page.
"""
import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString

BASE = "https://zno.osvita.ua"
ROOT = Path(__file__).resolve().parent
IMG_DIR = ROOT / "img"
OUT = ROOT / "data.js"
JS_PREFIX = "window.TZNK_DATA = "
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128 Safari/537.36")
DEFAULT_VARIANTS = [646, 647, 648, 649, 650]
LETTERS = {"a": "А", "b": "Б", "c": "В", "d": "Г"}
# Minimal shared prefix (in characters) for consecutive items to count as one
# group with a common passage.
MIN_PASSAGE = 300

KEEP_TAGS = {"p", "strong", "em", "b", "i", "u", "br", "img", "sub", "sup",
             "ul", "ol", "li", "table", "thead", "tbody", "tr", "td", "th",
             "span", "div"}
KEEP_ATTRS = {"img": {"src", "alt"}, "td": {"colspan", "rowspan"},
              "th": {"colspan", "rowspan"}}


def section_for(n: int) -> str:
    if n <= 10:
        return "lexis"
    if n <= 18:
        return "reading"
    return "logic"


SECTION_TITLES = {
    "lexis": "Лексика: мікротексти з пропусками",
    "reading": "Читання й розуміння тексту",
    "logic": "Логіко-аналітичний блок",
}


def clean(node, variant: int, session: requests.Session) -> str:
    """Return sanitized inner HTML of node, downloading images on the way."""
    for tag in list(node.find_all(True)):
        if tag.name not in KEEP_TAGS:
            tag.unwrap()
            continue
        allowed = KEEP_ATTRS.get(tag.name, set())
        for attr in list(tag.attrs):
            if attr not in allowed:
                del tag[attr]
        if tag.name == "img" and tag.get("src"):
            tag["src"] = fetch_image(tag["src"], variant, session)
    # drop empty paragraphs (&nbsp; fillers)
    for p in list(node.find_all("p")):
        if not p.get_text(strip=True).replace("\xa0", "") and not p.find("img"):
            p.decompose()
    html = "".join(str(c) for c in node.contents)
    html = html.replace("\u200b", "")
    html = re.sub(r"\s*\n\s*", " ", html)
    html = re.sub(r"\s{2,}", " ", html)
    return html.strip()


def fetch_image(src: str, variant: int, session: requests.Session) -> str:
    url = urljoin(BASE, src)
    name = Path(src).name
    target = IMG_DIR / str(variant) / name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        r = session.get(url, timeout=30)
        r.raise_for_status()
        target.write_bytes(r.content)
        print(f"    img {name} ({len(r.content)} B)")
        time.sleep(0.3)
    return f"img/{variant}/{name}"


def paragraphs(html: str) -> list[str]:
    """Split sanitized HTML into top-level block strings for prefix matching."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    out = []
    for c in body.contents:
        if isinstance(c, NavigableString):
            if c.strip():
                out.append(str(c).strip())
        else:
            out.append(str(c))
    return out


def _norm(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("\xa0", " ").replace("&nbsp;", " ").lower()
    return re.sub(r"[\s\W_]+", "", text)


def contained(para: str, other_text: str, other_paras: list[str]) -> bool:
    """Is this paragraph part of the shared passage that other_text also has?
    Source pages repeat the passage per item with small typos, tag changes
    and occasionally a paragraph split in two, so match on normalized text:
    substring for long paragraphs, fuzzy ratio for short headings."""
    n = _norm(para)
    if not n:
        return True
    if len(n) >= 40:
        return n in other_text
    return any(len(_norm(o)) < 40 and
               SequenceMatcher(None, n, _norm(o)).ratio() >= 0.8
               for o in other_paras)


def similar_items(a: list[str], b: list[str]) -> bool:
    na, nb = _norm("".join(a)), _norm("".join(b))
    if min(len(na), len(nb)) < MIN_PASSAGE:
        return False
    sm = SequenceMatcher(None, na, nb)
    return sm.quick_ratio() >= 0.7 and sm.ratio() >= 0.7


def question_start(paras: list[str], others: list[list[str]]) -> int:
    """Index where this item's own question starts. A paragraph belongs to
    the shared passage only when every other member of the group contains
    it; the source sometimes leaks one item's question into the next item,
    and that leaked paragraph is contained in one sibling but not in all."""
    texts = [_norm("".join(o)) for o in others]
    k = len(paras)
    while k > 0 and not all(contained(paras[k - 1], t, o)
                            for t, o in zip(texts, others)):
        k -= 1
    if k == len(paras):
        k = len(paras) - 1
    return k


def split_passages(items: list[dict]) -> None:
    """Group consecutive non-lexis items that share a long passage; store the
    passage once per item in item['passage'] and keep only the item-specific
    question in item['question']. Microtext items (1-10) stay whole because
    their text differs only in which gap is highlighted."""
    paras = [paragraphs(it["question"]) for it in items]
    i = 0
    group_no = 0
    while i < len(items):
        j = i + 1
        if items[i]["section"] != "lexis":
            while j < len(items) and items[j]["section"] != "lexis" \
                    and similar_items(paras[i], paras[j]):
                j += 1
        members = list(range(i, j))
        if len(members) > 1:
            group_no += 1
            starts = {m: question_start(paras[m], [paras[o] for o in members if o != m])
                      for m in members}
            passage = "".join(paras[i][:starts[i]])
            last = {m: _norm(paras[m][-1]) for m in members}
            for m in members:
                own = [p for p in paras[m][starts[m]:]
                       if p is paras[m][-1]
                       or _norm(p) not in {last[o] for o in members if o != m}]
                items[m]["passage"] = passage
                items[m]["question"] = "".join(own)
                items[m]["group"] = group_no
        else:
            items[i]["passage"] = ""
            items[i]["group"] = 0
        i = j


def scrape_variant(variant: int, session: requests.Session) -> dict:
    url = f"{BASE}/master/tznpk/{variant}/"
    print(f"== variant {variant}: {url}")
    r = session.get(url, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    title = soup.title.string.split("–")[0].strip() if soup.title else f"Варіант {variant}"
    items = []
    for form in soup.select("form.q-test"):
        qid = form.select_one('input[name="q[id]"]')["value"]
        n = int(form.select_one('input[name="q[out_order]"]')["value"])
        tip = form.select_one('input[name="q[tip]"]')["value"]
        result = form.select_one('input[name="result"]')
        if tip != "1" or result is None:
            print(f"  !! item {n} (id {qid}): unsupported tip={tip}, result={result}")
            continue
        answers = []
        for a in form.select(".answers .answer"):
            marker = a.select_one(".marker")
            letter = marker.get_text(strip=True) if marker else ""
            if marker:
                marker.decompose()
            answers.append({"letter": letter,
                            "html": clean(a, variant, session)})
        expl_node = soup.select_one(f"#commentar_{qid}")
        explanation = ""
        if expl_node is not None:
            head = expl_node.find("strong")
            if head and head.get_text(strip=True) == "Пояснення":
                head.decompose()
            explanation = clean(expl_node, variant, session)
            explanation = re.sub(r"^(<br\s*/?>\s*)+", "", explanation)
        items.append({
            "id": int(qid),
            "n": n,
            "section": section_for(n),
            "question": clean(form.select_one(".question"), variant, session),
            "answers": answers,
            "correct": LETTERS[result["value"]],
            "explanation": explanation,
        })
    items.sort(key=lambda x: x["n"])
    split_passages(items)
    groups = {}
    for it in items:
        groups.setdefault(it["group"], []).append(it["n"])
    print(f"  {len(items)} items; groups: "
          + ", ".join(f"{g}:{v[0]}-{v[-1]}" for g, v in groups.items() if g))
    return {"id": variant, "title": title, "source": url, "items": items}


def main(argv: list[str]) -> None:
    variants = [int(a) for a in argv] or DEFAULT_VARIANTS
    session = requests.Session()
    session.headers["User-Agent"] = UA
    data = {
        "generated": time.strftime("%Y-%m-%d"),
        "exam": {"minutes": 75, "max_points": 33},
        "sections": SECTION_TITLES,
        "variants": [],
    }
    if OUT.exists():
        raw = OUT.read_text(encoding="utf-8")
        old = json.loads(raw[len(JS_PREFIX):].rstrip().rstrip(";"))
        data["variants"] = [v for v in old.get("variants", []) if v["id"] not in variants]
    for v in variants:
        data["variants"].append(scrape_variant(v, session))
        time.sleep(1)
    data["variants"].sort(key=lambda v: v["id"])
    # data.js instead of data.json so index.html also works when opened from
    # disk (file:// blocks fetch of a sibling JSON file).
    OUT.write_text(JS_PREFIX + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
                   encoding="utf-8")
    total = sum(len(v["items"]) for v in data["variants"])
    print(f"wrote {OUT.name}: {len(data['variants'])} variants, {total} items")


if __name__ == "__main__":
    main(sys.argv[1:])
