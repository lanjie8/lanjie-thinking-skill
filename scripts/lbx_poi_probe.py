#!/usr/bin/env python3
"""Probe public map and LBX Pharmacy endpoints from GitHub Actions.

This temporary script uses ordinary HTTP requests only. It records response
status, headers, and bodies so a usable public source can be selected before a
rate-limited nationwide collection.
"""
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

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def fetch(name: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    ctx = ssl.create_default_context()
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            charset = resp.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            suffix = ".json" if "json" in (resp.headers.get("Content-Type") or "") else ".txt"
            (OUT / f"{name}{suffix}").write_text(text, encoding="utf-8")
            return {
                "name": name,
                "url": url,
                "status": resp.status,
                "final_url": resp.geturl(),
                "content_type": resp.headers.get("Content-Type"),
                "set_cookie": resp.headers.get_all("Set-Cookie") or [],
                "elapsed": round(time.time() - started, 3),
                "length": len(raw),
                "body_preview": text[:6000],
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        (OUT / f"{name}_error.txt").write_text(text, encoding="utf-8")
        return {
            "name": name,
            "url": url,
            "status": exc.code,
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type") if exc.headers else None,
            "set_cookie": exc.headers.get_all("Set-Cookie") if exc.headers else [],
            "elapsed": round(time.time() - started, 3),
            "length": len(raw),
            "body_preview": text[:6000],
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


def q(params: dict[str, str | int]) -> str:
    return urllib.parse.urlencode(params)


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
    return f"https://{host}/service/poiInfo?{q(params)}"


def baidu_simple(host: str, city_code: str, keyword: str, *, page: int = 0) -> str:
    params = {
        "qt": "s",
        "wd": keyword,
        "c": city_code,
        "rn": "50",
        "pn": str(page),
        "nn": str(page * 50),
        "ie": "utf-8",
        "oue": "1",
        "fromproduct": "jsapi",
        "res": "api",
        "from": "webmap",
    }
    return f"https://{host}/?{q(params)}"


def baidu_pc(city_code: str, keyword: str, *, page: int = 0) -> str:
    params = {
        "newmap": "1",
        "reqflag": "pcmap",
        "biz": "1",
        "from": "webmap",
        "da_par": "direct",
        "pcevaname": "pc4.1",
        "qt": "s",
        "da_src": "searchBox.button",
        "wd": keyword,
        "c": city_code,
        "src": "0",
        "pn": str(page),
        "nn": str(page * 10),
        "rn": "50",
        "sug": "0",
        "l": "12",
        "b": "(12400000,3200000;12600000,3400000)",
        "biz_forward": json.dumps({"scaler": 1, "styles": "pl"}, ensure_ascii=False),
    }
    return f"https://map.baidu.com/?{q(params)}"


def main() -> None:
    baidu_headers = {
        "Referer": "https://map.baidu.com/",
        "Origin": "https://map.baidu.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    amap_headers = {"Referer": "https://www.amap.com/", "Origin": "https://www.amap.com"}
    lbx_headers = {"Referer": "https://www.lbxdrugs.com/", "Origin": "https://www.lbxdrugs.com"}
    probes: list[tuple[str, str, dict[str, str] | None]] = [
        ("baidu_map_city_lookup", "https://map.baidu.com/?" + q({"qt": "s", "wd": "长沙", "from": "webmap"}), baidu_headers),
        ("baidu_api_city_lookup", "https://api.map.baidu.com/?" + q({"qt": "s", "wd": "长沙", "rn": 10, "ie": "utf-8", "oue": 1, "fromproduct": "jsapi", "res": "api"}), baidu_headers),
        ("baidu_map_changsha_simple", baidu_simple("map.baidu.com", "158", "老百姓大药房", page=0), baidu_headers),
        ("baidu_api_changsha_simple", baidu_simple("api.map.baidu.com", "158", "老百姓大药房", page=0), baidu_headers),
        ("baidu_map_changsha_pc", baidu_pc("158", "老百姓大药房", page=0), baidu_headers),
        ("baidu_map_changsha_name_city", "https://map.baidu.com/?" + q({"qt": "s", "wd": "长沙 老百姓大药房", "rn": 50, "ie": "utf-8", "oue": 1, "from": "webmap"}), baidu_headers),
        ("baidu_search_page", "https://map.baidu.com/search/" + urllib.parse.quote("老百姓大药房") + "/@12590000,3240000,12z", {"Referer": "https://map.baidu.com/", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}),
        ("amap_www_changsha_p1", amap_url("www.amap.com", "430100", "老百姓大药房", 1), amap_headers),
        ("amap_city_list", "https://www.amap.com/service/cityList?version=1", amap_headers),
        ("lbx_official", "https://www.lbxdrugs.com/about.html", lbx_headers),
        ("lbx_qr_purchase", "https://omo-oss-image.thefastimg.com/portal-saas/pg2024101217574431839/cms/image/68ec6b77-7b58-4aca-9a76-1bdb3531b2c7.jpg", {"Referer": "https://www.lbxdrugs.com/about.html", "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"}),
        ("lbx_qr_wechat", "https://omo-oss-image.thefastimg.com/portal-saas/pg2024101217574431839/cms/image/b26fce50-3b1f-41d6-b621-5292ce6cedf2.jpg", {"Referer": "https://www.lbxdrugs.com/about.html", "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"}),
        ("certspotter_lbxcn", "https://api.certspotter.com/v1/issuances?" + q({"domain": "lbxcn.com", "include_subdomains": "true", "expand": "dns_names"}), {"Referer": "https://api.certspotter.com/"}),
        ("certspotter_lbxdrugs", "https://api.certspotter.com/v1/issuances?" + q({"domain": "lbxdrugs.com", "include_subdomains": "true", "expand": "dns_names"}), {"Referer": "https://api.certspotter.com/"}),
    ]

    results = []
    for name, url, headers in probes:
        print(f"PROBE {name}: {url}", flush=True)
        result = fetch(name, url, headers)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:3500], flush=True)
        time.sleep(1.2)

    (OUT / "probe_report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
