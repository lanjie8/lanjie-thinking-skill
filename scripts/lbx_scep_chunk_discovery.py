#!/usr/bin/env python3
"""Download SCEP dynamic chunks and identify store-related API endpoints."""
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import re
import threading
from pathlib import Path
from typing import Any

import requests

ROOT = Path("fast_output")
OUT = Path("scep_output")
OUT.mkdir(exist_ok=True)
RAW = OUT / "chunks"
RAW.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
LOCAL = threading.local()


def session() -> requests.Session:
    s = getattr(LOCAL, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept": "*/*", "Referer": "https://scep.lbxcn.com/"})
        LOCAL.s = s
    return s


def fetch_chunk(item: tuple[str, str]) -> dict[str, Any]:
    cid, hashv = item
    url = f"https://scep.lbxcn.com/js/{cid}.{hashv}.js"
    try:
        r = session().get(url, timeout=30)
        text = r.text
        if r.status_code == 200 and "javascript" in (r.headers.get("content-type") or "").lower():
            (RAW / f"{cid}.{hashv}.js").write_text(text, encoding="utf-8")
        return {"chunk_id": cid, "hash": hashv, "url": url, "status": r.status_code, "size": len(r.content), "content_type": r.headers.get("content-type")}
    except Exception as exc:  # noqa: BLE001
        return {"chunk_id": cid, "hash": hashv, "url": url, "status": None, "error": repr(exc)}


def extract_chunk_map() -> dict[str, str]:
    app_paths = sorted(ROOT.glob("js_app*.txt"))
    if not app_paths:
        raise FileNotFoundError("No app JS file under fast_output")
    text = max(app_paths, key=lambda p: p.stat().st_size).read_text(encoding="utf-8", errors="ignore")
    start = text.find('a.u=function(e){return"js/"')
    end = text.find('function(){a.miniCssF', start)
    section = text[start:end if end > start else None]
    # Last hash map in a.u is the JS chunk hash map. Capture all; IDs with locale name maps are overwritten later.
    pairs = re.findall(r'(\d+):"([0-9a-f]{8})"', section)
    mapping: dict[str, str] = {}
    for cid, hashv in pairs:
        mapping[cid] = hashv
    return mapping


def context(text: str, start: int, end: int, radius: int = 350) -> str:
    s = text[max(0, start-radius): min(len(text), end+radius)]
    return re.sub(r"\s+", " ", s).strip()[:2500]


def scan_chunks() -> dict[str, Any]:
    interest = re.compile(r"store|shop|branch|outlet|门店|药房|药店|storeCode|storeName|storeId|address|longitude|latitude|lng|lat|orgCode|orgName", re.I)
    quoted = re.compile(r"['\"]([^'\"]{2,800})['\"]")
    apiish = re.compile(r"^/?[A-Za-z0-9_./?=&%{}:-]+$")
    endpoint_rows: list[dict[str, Any]] = []
    api_hosts: set[str] = set()
    keyword_counts: list[dict[str, Any]] = []
    for path in sorted(RAW.glob("*.js")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        counts = {term: len(re.findall(term, text, flags=re.I)) for term in ["store", "shop", "门店", "药房", "address", "longitude", "latitude", "orgCode"]}
        total = sum(counts.values())
        if total:
            keyword_counts.append({"chunk": path.name, "size": path.stat().st_size, **counts, "total": total})
        seen: set[str] = set()
        for m in quoted.finditer(text):
            value = m.group(1)
            if not interest.search(value):
                continue
            if value in seen:
                continue
            seen.add(value)
            is_endpoint = bool(apiish.match(value)) and ("/" in value or value.startswith("http"))
            endpoint_rows.append({
                "chunk": path.name,
                "value": value,
                "is_endpoint": is_endpoint,
                "context": context(text, m.start(), m.end()),
            })
            if value.startswith("http"):
                api_hosts.add(value)
        # Extract literal endpoint-looking strings even when no interest term appears in path, if context has store term.
        for m in quoted.finditer(text):
            value = m.group(1)
            if not (3 <= len(value) <= 500 and apiish.match(value) and "/" in value):
                continue
            ctx = context(text, m.start(), m.end())
            if not interest.search(ctx):
                continue
            key = "CTX:" + value
            if key in seen:
                continue
            seen.add(key)
            endpoint_rows.append({"chunk": path.name, "value": value, "is_endpoint": True, "context": ctx})
    endpoint_rows.sort(key=lambda r: (0 if r["is_endpoint"] else 1, r["chunk"], r["value"]))
    keyword_counts.sort(key=lambda r: -r["total"])
    with (OUT / "endpoint_hits.tsv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["chunk", "value", "is_endpoint", "context"], delimiter="\t")
        w.writeheader(); w.writerows(endpoint_rows)
    with (OUT / "keyword_counts.tsv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["chunk", "size", "store", "shop", "门店", "药房", "address", "longitude", "latitude", "orgCode", "total"]
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader(); w.writerows(keyword_counts)
    return {"endpoint_count": len(endpoint_rows), "keyword_chunks": keyword_counts, "api_hosts": sorted(api_hosts), "top_endpoints": endpoint_rows[:300]}


def main() -> None:
    mapping = extract_chunk_map()
    (OUT / "chunk_map.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    items = sorted(mapping.items(), key=lambda x: int(x[0]))
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        downloads = list(ex.map(fetch_chunk, items, chunksize=2))
    (OUT / "download_report.json").write_text(json.dumps(downloads, ensure_ascii=False, indent=2), encoding="utf-8")
    scan = scan_chunks()
    summary = {
        "chunk_map_count": len(mapping),
        "download_success": sum(1 for x in downloads if x.get("status") == 200),
        "download_failed": [x for x in downloads if x.get("status") != 200],
        **scan,
    }
    (OUT / "scep_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:50000])


if __name__ == "__main__":
    main()
