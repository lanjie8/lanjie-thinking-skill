#!/usr/bin/env python3
"""Probe public map and LBX web endpoints from a browser-capable runner.

This is a temporary research script. It only sends ordinary public GET/search
requests and does not attempt authentication or CAPTCHA bypass.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import requests
from playwright.async_api import async_playwright

OUT = Path("browser_probe_output")
OUT.mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def save_text(name: str, text: str) -> None:
    (OUT / name).write_text(text, encoding="utf-8", errors="replace")


def direct_get(name: str, url: str, *, headers: dict[str, str] | None = None, timeout: int = 40) -> dict[str, Any]:
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    started = time.time()
    try:
        r = requests.get(url, headers=h, timeout=timeout, allow_redirects=True)
        text = r.text
        save_text(f"{name}.txt", text)
        return {
            "name": name,
            "url": url,
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("content-type"),
            "length": len(r.content),
            "elapsed": round(time.time() - started, 3),
            "preview": text[:2500],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "url": url,
            "status": None,
            "elapsed": round(time.time() - started, 3),
            "error": repr(exc),
        }


def baidu_url(city_code: str, page: int, keyword: str = "老百姓大药房") -> str:
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
        "sug": "0",
        "l": "12",
        "ie": "utf-8",
        "oue": "1",
    }
    return "https://map.baidu.com/?" + urlencode(params)


def amap_url(city: str, page: int, keyword: str = "老百姓大药房") -> str:
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
    return "https://www.amap.com/service/poiInfo?" + urlencode(params)


def overpass_query_url() -> str:
    query = '''[out:json][timeout:90];
area["ISO3166-1"="CN"][admin_level=2]->.cn;
nwr(area.cn)["name"~"老百姓(大|健康)?药房"];
out center tags;'''
    return "https://overpass-api.de/api/interpreter?" + urlencode({"data": query})


def probe_lbx_domains() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    candidates = {
        "www.lbxdrugs.com",
        "lbxcn.com",
        "www.lbxcn.com",
        "mall.lbxcn.com",
        "mall-photo.lbxcn.com",
        "o2o.lbxcn.com",
        "api.o2o.lbxcn.com",
        "admin.o2o.lbxcn.com",
        "jfsc.lbxcn.com",
    }
    try:
        crt = requests.get("https://crt.sh/?q=%25.lbxcn.com&output=json", headers=HEADERS, timeout=45)
        crt.raise_for_status()
        for row in crt.json():
            for name in str(row.get("name_value", "")).splitlines():
                name = name.strip().lower().lstrip("*.")
                if name and name.endswith(".lbxcn.com"):
                    candidates.add(name)
    except Exception as exc:  # noqa: BLE001
        results.append({"name": "crt_parse", "error": repr(exc)})

    likely = []
    for host in sorted(candidates):
        low = host.lower()
        if any(x in low for x in ("dev", "test", "uat", "pre", "admin", "erp", "scrm")):
            continue
        if any(x in low for x in ("mall", "o2o", "api", "wx", "mini", "h5", "shop", "store", "jfsc")) or low in {
            "lbxcn.com", "www.lbxcn.com"
        }:
            likely.append(host)
    likely = likely[:40]
    for host in likely:
        results.append(
            direct_get(
                "host_" + re.sub(r"[^a-z0-9]+", "_", host),
                f"https://{host}/",
                headers={"Referer": f"https://{host}/"},
                timeout=20,
            )
        )
    return results


async def browser_probe() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent=UA,
            locale="zh-CN",
            viewport={"width": 1440, "height": 1000},
        )

        # Baidu: establish first-party cookies, then issue the ordinary search request.
        page = await context.new_page()
        captured: list[dict[str, Any]] = []

        async def capture_response(resp):
            u = resp.url
            if "map.baidu.com" in u and ("qt=s" in u or "search" in u):
                try:
                    body = await resp.text()
                except Exception:
                    body = ""
                captured.append({"url": u, "status": resp.status, "body": body[:200000]})
            if "amap.com" in u and "poiInfo" in u:
                try:
                    body = await resp.text()
                except Exception:
                    body = ""
                captured.append({"url": u, "status": resp.status, "body": body[:200000]})

        page.on("response", capture_response)
        try:
            await page.goto("https://map.baidu.com/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            text = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url, {credentials: 'include'});
                    return JSON.stringify({status:r.status, url:r.url, body:await r.text()});
                }""",
                baidu_url("158", 0),
            )
            save_text("baidu_browser_fetch.json", text)
            results.append({"name": "baidu_browser_fetch", "length": len(text), "preview": text[:2500]})
            await page.screenshot(path=str(OUT / "baidu_home.png"), full_page=False)
        except Exception as exc:  # noqa: BLE001
            results.append({"name": "baidu_browser_fetch", "error": repr(exc)})

        # AMap: establish first-party browser state, then request the same public POI search endpoint.
        try:
            await page.goto("https://www.amap.com/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(7000)
            text = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url, {credentials: 'include'});
                    return JSON.stringify({status:r.status, url:r.url, body:await r.text()});
                }""",
                amap_url("430100", 1),
            )
            save_text("amap_browser_fetch.json", text)
            results.append({"name": "amap_browser_fetch", "length": len(text), "preview": text[:2500]})
            await page.screenshot(path=str(OUT / "amap_home.png"), full_page=False)
        except Exception as exc:  # noqa: BLE001
            results.append({"name": "amap_browser_fetch", "error": repr(exc)})

        save_text("captured_network.json", json.dumps(captured, ensure_ascii=False, indent=2))
        results.append({"name": "captured_network", "count": len(captured), "items": [
            {"url": x["url"], "status": x["status"], "preview": x["body"][:800]} for x in captured[:20]
        ]})
        await context.close()
        await browser.close()
    return results


def main() -> None:
    report: list[dict[str, Any]] = []
    direct = [
        ("baidu_changsha_p0", baidu_url("158", 0), {"Referer": "https://map.baidu.com/"}),
        ("baidu_national_p0", baidu_url("1", 0), {"Referer": "https://map.baidu.com/"}),
        ("baidu_health_changsha_p0", baidu_url("158", 0, "老百姓健康药房"), {"Referer": "https://map.baidu.com/"}),
        ("amap_mobile_changsha", amap_url("430100", 1).replace("www.amap.com", "m.amap.com"), {"Referer": "https://m.amap.com/"}),
        ("overpass_lbx", overpass_query_url(), {"Referer": "https://overpass-turbo.eu/"}),
        ("mall_root", "https://mall.lbxcn.com/", {"Referer": "https://mall.lbxcn.com/"}),
        ("mall_path", "https://mall.lbxcn.com/mall/", {"Referer": "https://mall.lbxcn.com/mall/"}),
        ("o2o_root", "https://o2o.lbxcn.com/", {"Referer": "https://o2o.lbxcn.com/"}),
    ]
    for name, url, headers in direct:
        print(f"DIRECT {name}: {url}", flush=True)
        item = direct_get(name, url, headers=headers)
        report.append(item)
        print(json.dumps(item, ensure_ascii=False, indent=2)[:3000], flush=True)
        time.sleep(1)

    domains = probe_lbx_domains()
    report.extend(domains)
    print(f"Probed {len(domains)} likely LBX hosts", flush=True)

    browser = asyncio.run(browser_probe())
    report.extend(browser)
    print(json.dumps(browser, ensure_ascii=False, indent=2)[:10000], flush=True)

    save_text("report.json", json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
