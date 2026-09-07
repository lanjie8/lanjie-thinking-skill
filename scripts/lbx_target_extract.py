#!/usr/bin/env python3
"""Fast targeted extraction of likely store-list endpoints and large store-list files."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

OUT = Path("target_output")
OUT.mkdir(exist_ok=True)

KEYS = (
    "门店", "药房", "药店", "网点", "店铺", "地址", "经度", "纬度", "store", "shop",
    "branch", "outlet", "nearby", "location", "poi", "address", "longitude", "latitude",
    "storelist", "shoplist", "store/list", "shop/list", "api", "baseurl",
)
STRONG = (
    "门店清单", "门店列表", "门店地址", "药房清单", "附近门店", "预约门店", "门店编码",
    "storelist", "shoplist", "store/list", "shop/list", "nearby/store", "nearbyshop",
)


def load(path: str, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def compact(v: object, limit: int = 700) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


def score(v: str) -> int:
    low = unquote(v).lower()
    s = sum(12 for k in STRONG if k.lower() in low)
    s += sum(1 for k in KEYS if k.lower() in low)
    if low.startswith("http"): s += 2
    if "/" in low: s += 1
    return s


def walk(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def extract_yx() -> list[dict]:
    report = load("yx_discovery_output/report.json", {})
    rows = []
    seen = set()
    for p, v in walk(report):
        v = compact(v)
        s = score(v)
        if s < 3 or len(v) < 3:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"score": s, "json_path": p, "value": v})

    # Only scan first-party/app JS files, not huge generic libraries.
    for f in sorted(Path("yx_discovery_output").glob("script_*.js")):
        if f.stat().st_size > 500_000:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"https?://[^\s\"'<>\\]+", text, re.I):
            v = compact(m.group(0).rstrip("),.;}"))
            s = score(v)
            if s >= 2 and v.lower() not in seen:
                seen.add(v.lower()); rows.append({"score": s, "json_path": str(f), "value": v})
        for m in re.finditer(r"(?i).{0,160}(?:baseURL|axios|fetch\(|ajax\(|门店清单|门店列表|附近门店|storeList|shopList).{0,300}", text):
            v = compact(m.group(0))
            s = score(v) + 5
            k = (str(f), v.lower())
            if k not in seen:
                seen.add(k); rows.append({"score": s, "json_path": str(f), "value": v})
    rows.sort(key=lambda r: (-r["score"], r["json_path"], r["value"]))
    return rows[:1200]


def extract_bidding() -> list[dict]:
    items = load("fast_output/bidding_candidates.json", [])
    rows = []
    for item in items:
        ins = item.get("inspection") or {}
        sheets = ins.get("sheets") or []
        max_rows = max((int(s.get("max_row") or 0) for s in sheets), default=0)
        max_cols = max((int(s.get("max_col") or 0) for s in sheets), default=0)
        addr_rows = sum(int(s.get("address_like_rows") or 0) for s in sheets)
        sheet_names = [compact(s.get("name"), 180) for s in sheets]
        hits = sorted({str(x) for s in sheets for x in (s.get("keyword_hits") or [])})
        text = " ".join([str(item.get("label", "")), str(item.get("notice_title", "")), " ".join(sheet_names), " ".join(hits)])
        s = score(text) + min(80, max_rows // 50) + min(80, addr_rows // 5)
        rows.append({
            "score": s,
            "label": compact(item.get("label"), 300),
            "notice_title": compact(item.get("notice_title"), 300),
            "url": item.get("url", ""),
            "notice_url": item.get("notice_url", ""),
            "status": item.get("status"),
            "size": item.get("size"),
            "max_rows": max_rows,
            "max_cols": max_cols,
            "address_like_rows": addr_rows,
            "sheet_names": sheet_names,
            "keyword_hits": hits,
        })
    rows.sort(key=lambda r: (-r["score"], -r["max_rows"], -r["address_like_rows"], r["label"]))
    return rows


def main():
    yx = extract_yx()
    bidding = extract_bidding()
    data = {"yx_candidates": yx, "bidding_candidates": bidding[:120]}
    (OUT / "target_candidates.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["YX_CANDIDATES"]
    lines += [f"{r['score']}\t{r['json_path']}\t{r['value']}" for r in yx[:600]]
    lines += ["", "BIDDING_CANDIDATES"]
    lines += [f"{r['score']}\trows={r['max_rows']}\taddr={r['address_like_rows']}\t{r['label']}\t{r['notice_title']}\t{r['url']}" for r in bidding[:120]]
    (OUT / "target_candidates.txt").write_text("\n".join(lines), encoding="utf-8")
    print("yx", len(yx), "bidding", len(bidding))
    print("\n".join(lines[:160]))


if __name__ == "__main__":
    main()
