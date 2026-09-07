#!/usr/bin/env python3
"""Probe public LBX Pharmacy POI data sources from a GitHub-hosted runner."""
from __future__ import annotations

import gzip
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

OUT = Path("probe_output")
OUT.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.amap.com/",
    "Origin": "https://www.amap.com",
}


def fetch(name: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req_headers = dict(HEADERS)
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    ctx = ssl.create_default_context()
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            text = raw.decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
            result = {
                "name": name,
                "url": url,
                "status": resp.status,
                "final_url": resp.geturl(),
                "content_type": resp.headers.get("Content-Type"),
                "elapsed": round(time.time() - started, 3),
                "length": len(raw),
                "body_preview": text[:5000],
            }
            (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
            return result
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        return {
            "name": name,
            "url": url,
            "status": exc.code,
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type") if exc.headers else None,
            "elapsed": round(time.time() - started, 3),
            "length": len(raw),
            "body_preview": text[:5000],
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "url": url,
            "status": None,
            "elapsed": round(time.time() - started, 3),
            "error": repr(exc),
        }


def amap_url(host: str, city: str, keyword: str, page: int = 1) -> str:
    params = {
        "query_type": "TQUERY",
        "pagesize": "20",
        "pagenum": str(page),
        "qii": "true",
        "cluster_state": "5",
        "need_utd": "true",
        "utd_sceneid": "1000",
        "div": "PC1000",
        "addr_poi_merge": "true",
        "is_classify": "true",
        "zoom": "10",
        "city": city,
        "keywords": keyword,
    }
    return f"https://{host}/service/poiInfo?{urllib.parse.urlencode(params)}"


def main() -> None:
    probes = [
        ("amap_www_changsha_p1", amap_url("www.amap.com", "430100", "老百姓大药房", 1), None),
        ("amap_ditu_changsha_p1", amap_url("ditu.amap.com", "430100", "老百姓大药房", 1), None),
        ("amap_www_xian_p1", amap_url("www.amap.com", "610100", "老百姓大药房", 1), None),
        ("amap_city_list", "https://www.amap.com/service/cityList?version=1", None),
        ("poi86_home", "https://www.poi86.com/", {"Referer": "https://www.poi86.com/", "Origin": "https://www.poi86.com"}),
        ("poi86_known", "https://www.poi86.com/poi/amap/1426957.html", {"Referer": "https://www.poi86.com/", "Origin": "https://www.poi86.com"}),
        ("crt_lbxcn", "https://crt.sh/?q=%25.lbxcn.com&output=json", {"Referer": "https://crt.sh/", "Origin": "https://crt.sh"}),
        ("lbx_official", "https://www.lbxdrugs.com/about.html", {"Referer": "https://www.lbxdrugs.com/", "Origin": "https://www.lbxdrugs.com"}),
    ]
    results = []
    for name, url, headers in probes:
        print(f"PROBE {name}: {url}", flush=True)
        result = fetch(name, url, headers)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000], flush=True)
        time.sleep(1)
    (OUT / "probe_report.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
