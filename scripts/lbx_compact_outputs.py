#!/usr/bin/env python3
"""Create compact, reviewable candidate reports from LBX discovery outputs."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

OUT = Path("compact_output")
OUT.mkdir(exist_ok=True)

WORDS = [
    "门店", "药房", "药店", "网点", "地址", "配送", "收货", "门店编码", "机构编码",
    "store", "shop", "branch", "nearby", "location", "poi", "address", "longitude",
    "latitude", "lng", "lat", "api", "org", "dealer", "pharmacy", "outlet",
]
STRONG = ["门店清单", "门店列表", "门店地址", "配送地址", "收货地址", "门店编码", "药房清单", "storelist", "store/list", "shop/list", "nearby/store"]


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def clean(s: object, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", str(s or "")).strip()
    return text[:limit]


def score_text(text: str) -> int:
    low = unquote(text).lower()
    return sum(8 for w in STRONG if w.lower() in low) + sum(1 for w in WORDS if w.lower() in low)


def compact_bidding() -> None:
    items = load_json(Path("fast_output/bidding_candidates.json"), [])
    rows = []
    for idx, item in enumerate(items, 1):
        ins = item.get("inspection") or {}
        sheets = ins.get("sheets") or []
        max_rows = max((s.get("max_row") or 0 for s in sheets), default=0)
        max_cols = max((s.get("max_col") or 0 for s in sheets), default=0)
        addr_rows = sum((s.get("address_like_rows") or 0 for s in sheets))
        hits = sorted({str(x) for s in sheets for x in (s.get("keyword_hits") or [])})
        sheet_names = [clean(s.get("name"), 120) for s in sheets]
        headers = []
        sample_text = []
        for s in sheets:
            samples = s.get("samples") or []
            for r in samples[:8]:
                vals = [clean(v, 100) for v in r if clean(v, 100)]
                if vals:
                    sample_text.append(" | ".join(vals[:12]))
                    if len(headers) < 4:
                        headers.append(" | ".join(vals[:12]))
        base_text = " ".join([
            str(item.get("label", "")), str(item.get("notice_title", "")),
            " ".join(sheet_names), " ".join(hits), " ".join(sample_text[:30]),
        ])
        score = score_text(base_text) + min(30, addr_rows) + min(30, max_rows // 100)
        rows.append({
            "rank": idx,
            "score": score,
            "label": clean(item.get("label"), 260),
            "notice_title": clean(item.get("notice_title"), 260),
            "url": item.get("url", ""),
            "notice_url": item.get("notice_url", ""),
            "ext": item.get("ext", ""),
            "status": item.get("status"),
            "size": item.get("size"),
            "max_rows": max_rows,
            "max_cols": max_cols,
            "address_like_rows": addr_rows,
            "keyword_hits": ",".join(hits),
            "sheet_names": " || ".join(sheet_names),
            "sample_headers": " || ".join(headers),
        })
    rows.sort(key=lambda r: (-r["score"], -r["max_rows"], -r["address_like_rows"], r["label"]))
    cols = ["score", "label", "notice_title", "ext", "status", "size", "max_rows", "max_cols", "address_like_rows", "keyword_hits", "sheet_names", "sample_headers", "url", "notice_url"]
    lines = ["\t".join(cols)]
    for r in rows:
        lines.append("\t".join(clean(r.get(c), 1000).replace("\t", " ") for c in cols))
    (OUT / "bidding_candidates.tsv").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "bidding_top.json").write_text(json.dumps(rows[:80], ensure_ascii=False, indent=2), encoding="utf-8")


def extract_strings(text: str) -> set[str]:
    vals: set[str] = set()
    # Absolute URLs.
    vals.update(m.group(0).rstrip("),.;}\"'") for m in re.finditer(r"https?://[^\s\"'<>\\]+", text, re.I))
    # Quoted paths or endpoint-like strings.
    for m in re.finditer(r"(?s)([\"'])(.{2,500}?)\1", text):
        v = m.group(2).replace("\\/", "/")
        if score_text(v) > 0 and ("/" in v or "." in v):
            vals.add(v)
    return vals


def compact_endpoints() -> None:
    records = []
    source_files = []
    for base in [Path("yx_discovery_output"), Path("fast_output"), Path("probe_output/discovery")]:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".js", ".txt", ".json", ".html"} and p.stat().st_size <= 8_000_000:
                source_files.append(p)
    seen = set()
    for p in source_files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for value in extract_strings(text):
            value = clean(value, 1000)
            s = score_text(value)
            if s <= 0:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            records.append({"score": s, "source_file": str(p), "value": value})
        # Contexts for strong terms/baseURL/ajax/fetch/axios.
        for pat in [r".{0,180}(?:baseURL|baseUrl|axios|fetch\(|\.ajax\(|\.get\(|\.post\().{0,350}", r".{0,180}(?:门店清单|门店列表|门店地址|配送地址|storeList|shopList|nearbyStore).{0,350}"]:
            for m in re.finditer(pat, text, re.I | re.S):
                value = clean(m.group(0), 700)
                s = score_text(value) + 5
                key = (str(p), value.lower())
                if key in seen:
                    continue
                seen.add(key)
                records.append({"score": s, "source_file": str(p), "value": value})
                if len(records) > 20000:
                    break
    records.sort(key=lambda r: (-r["score"], r["source_file"], r["value"]))
    (OUT / "endpoint_candidates.json").write_text(json.dumps(records[:4000], ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"{r['score']}\t{r['source_file']}\t{r['value'].replace(chr(9),' ')}" for r in records[:4000]]
    (OUT / "endpoint_candidates.tsv").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    compact_bidding()
    compact_endpoints()
    manifest = {p.name: p.stat().st_size for p in OUT.iterdir() if p.is_file()}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
