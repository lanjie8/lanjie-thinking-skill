#!/usr/bin/env python3
"""Probe public LBX Pharmacy POI endpoints from a GitHub-hosted runner."""
from __future__ import annotations

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

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch(name: str, url: str, *, referer: str | None = None, timeout: int = 8) -> dict[str, Any]:
    headers = dict(BASE_HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            raw = resp.read()
            text = raw.decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
            (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
            parsed: Any = None
            try:
                parsed = json.loads(text)
            except Exception:
                pass
            return {
                "name": name,
                "url": url,
                "status": resp.status,
                "final_url": resp.geturl(),
                "content_type": resp.headers.get("Content-Type"),
                "elapsed": round(time.time() - started, 3),
                "length": len(raw),
                "json_top_keys": list(parsed)[:30] if isinstance(parsed, dict) else None,
                "body_preview": text[:3000],
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        return {
            "name": name,
            "url": url,
            "status": exc.code,
            "final_url": exc.geturl(),
            "elapsed": round(time.time() - started, 3),
            "length": len(raw),
            "body_preview": text[:3000],
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "status": None,
            "elapsed": round(time.time() - started, 3),
            "error": repr(exc),
        }


def amap_url(host: str, city: str, keyword: str, page: int = 1, pagesize: int = 100, scheme: str = "https") -> str:
    params = {
        "query_type": "TQUERY",
        "pagesize": str(pagesize),
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
    return f"{scheme}://{host}/service/poiInfo?{urllib.parse.urlencode(params)}"


def main() -> None:
    probes = [
        ("amap_www_https", amap_url("www.amap.com", "430100", "老百姓大药房"), "https://www.amap.com/"),
        ("amap_ditu_https", amap_url("ditu.amap.com", "430100", "老百姓大药房"), "https://ditu.amap.com/"),
        ("amap_ditu_http", amap_url("ditu.amap.com", "430100", "老百姓大药房", scheme="http"), "http://ditu.amap.com/"),
        ("amap_city_list", "https://www.amap.com/service/cityList?version=1", "https://www.amap.com/"),
        ("amap_home", "https://www.amap.com/", "https://www.amap.com/"),
        ("lbx_home", "https://www.lbxdrugs.com/", "https://www.lbxdrugs.com/"),
        ("lbx_about", "https://www.lbxdrugs.com/about.html", "https://www.lbxdrugs.com/"),
        ("lbx_mall", "https://mall.lbxcn.com/", "https://mall.lbxcn.com/"),
        ("baidu_map_search", "https://map.baidu.com/?qt=s&wd=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF&c=158&pn=0&nn=0", "https://map.baidu.com/"),
    ]
    results = []
    for name, url, referer in probes:
        print(f"PROBE {name}: {url}", flush=True)
        result = fetch(name, url, referer=referer)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    (OUT / "probe_report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
