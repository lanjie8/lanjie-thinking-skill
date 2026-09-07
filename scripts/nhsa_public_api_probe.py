#!/usr/bin/env python3
"""Discover public, unauthenticated query endpoints used by the NHSA service portal.

Temporary research utility. It fetches only public HTML/JavaScript resources and
records candidate API paths; it does not attempt authentication or bypass any
access control.
"""
from __future__ import annotations

import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

OUT = Path("nhsa_probe_output")
OUT.mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "script" and d.get("src"):
            self.scripts.append(d["src"])
        if tag.lower() == "link" and d.get("href"):
            self.links.append(d["href"])


def get(url: str, timeout: int = 25) -> dict[str, Any]:
    started = time.time()
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        text = r.text
        return {
            "url": url,
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("content-type"),
            "length": len(r.content),
            "elapsed": round(time.time() - started, 3),
            "headers": dict(r.headers),
            "text": text,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "url": url,
            "status": None,
            "elapsed": round(time.time() - started, 3),
            "error": repr(exc),
            "text": "",
        }


def safe_name(prefix: str, url: str) -> str:
    parsed = urlparse(url)
    raw = f"{prefix}_{parsed.netloc}_{parsed.path}_{parsed.query}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)[:180]


KEYWORDS = [
    "定点零售药店",
    "零售药店",
    "定点药店",
    "医药机构",
    "异地联网定点",
    "药店查询",
    "drugstore",
    "pharmacy",
    "retailpharmacy",
    "fixmedins",
    "fix_medins",
    "fixedmedical",
    "medins",
    "insutype",
    "querypharmacy",
    "querydrugstore",
]


def contexts(text: str, radius: int = 650, limit: int = 250) -> list[dict[str, str]]:
    low = text.lower()
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for kw in KEYWORDS:
        needle = kw.lower()
        pos = 0
        while len(found) < limit:
            idx = low.find(needle, pos)
            if idx < 0:
                break
            snippet = text[max(0, idx - radius): min(len(text), idx + len(kw) + radius)]
            snippet = snippet.replace("\x00", "")
            key = snippet[:250]
            if key not in seen:
                seen.add(key)
                found.append({"keyword": kw, "snippet": snippet})
            pos = idx + len(needle)
    return found


ABS_URL_RE = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
PATH_RE = re.compile(
    r"(?P<q>['\"])(?P<path>/(?:[A-Za-z0-9_~.@!$&()*+,;=:%?-]+/){0,12}"
    r"[A-Za-z0-9_~.@!$&()*+,;=:%?-]{1,120})(?P=q)"
)


def extract_candidates(text: str) -> dict[str, list[str]]:
    urls: list[str] = []
    paths: list[str] = []
    for u in ABS_URL_RE.findall(text):
        u = u.rstrip("'\"),;]")
        if u not in urls:
            urls.append(u)
    for m in PATH_RE.finditer(text):
        p = m.group("path")
        low = p.lower()
        if any(x in low for x in (
            "api", "query", "search", "service", "ebus", "hall", "medical",
            "pharmacy", "drug", "retail", "fix", "medins", "institution",
            "hospital", "common", "dict", "area", "region",
        )):
            if p not in paths:
                paths.append(p)
    return {"urls": urls[:1000], "paths": paths[:2000]}


def main() -> None:
    seeds = [
        "https://fuwu.nhsa.gov.cn/",
        "https://fuwu.nhsa.gov.cn/nationalHallSt/",
        "https://fuwu.nhsa.gov.cn/nationalHallSt/#/",
        "https://fuwu.nhsa.gov.cn/robots.txt",
        "https://fuwu.nhsa.gov.cn/sitemap.xml",
    ]
    page_records: list[dict[str, Any]] = []
    assets: list[str] = []
    for i, url in enumerate(seeds):
        result = get(url)
        text = result.pop("text", "")
        record = result
        record["contexts"] = contexts(text)
        record["candidates"] = extract_candidates(text)
        page_records.append(record)
        (OUT / f"page_{i}.txt").write_text(text, encoding="utf-8", errors="replace")
        parser = AssetParser()
        try:
            parser.feed(text)
        except Exception:
            pass
        base = record.get("final_url") or url
        for src in parser.scripts + parser.links:
            full = urljoin(base, src)
            if full.startswith(("http://", "https://")) and full not in assets:
                assets.append(full)
        print(json.dumps({k: v for k, v in record.items() if k != "headers"}, ensure_ascii=False)[:4000], flush=True)

    # Also discover recursively from HTML assets that redirect to portal entry pages.
    script_assets = [a for a in assets if ".js" in urlparse(a).path.lower()]
    asset_records: list[dict[str, Any]] = []
    global_urls: list[str] = []
    global_paths: list[str] = []
    print(f"Discovered {len(assets)} assets, {len(script_assets)} scripts", flush=True)
    for idx, url in enumerate(script_assets[:120]):
        result = get(url, timeout=30)
        text = result.pop("text", "")
        hits = contexts(text)
        cand = extract_candidates(text)
        record = {
            "url": url,
            "status": result.get("status"),
            "final_url": result.get("final_url"),
            "content_type": result.get("content_type"),
            "length": result.get("length"),
            "elapsed": result.get("elapsed"),
            "error": result.get("error"),
            "contexts": hits,
            "candidates": cand,
        }
        asset_records.append(record)
        for u in cand["urls"]:
            if u not in global_urls:
                global_urls.append(u)
        for p in cand["paths"]:
            if p not in global_paths:
                global_paths.append(p)
        if hits or any(
            x in url.lower() for x in ("app", "main", "index", "chunk", "vendor", "common", "config")
        ):
            (OUT / f"asset_{idx}_{safe_name('js', url)}.txt").write_text(
                text[:12_000_000], encoding="utf-8", errors="replace"
            )
        print(json.dumps({
            "idx": idx, "url": url, "status": record["status"],
            "length": record["length"], "keyword_hits": len(hits),
            "url_candidates": len(cand["urls"]), "path_candidates": len(cand["paths"]),
        }, ensure_ascii=False), flush=True)
        time.sleep(0.1)

    summary = {
        "pages": page_records,
        "assets_discovered": assets,
        "asset_records": asset_records,
        "candidate_absolute_urls": global_urls,
        "candidate_paths": global_paths,
    }
    (OUT / "nhsa_probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "pages": len(page_records),
        "assets": len(assets),
        "scripts": len(script_assets),
        "scripts_with_keyword_hits": sum(bool(x["contexts"]) for x in asset_records),
        "candidate_absolute_urls": len(global_urls),
        "candidate_paths": len(global_paths),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
