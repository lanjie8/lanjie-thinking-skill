#!/usr/bin/env python3
"""Inspect only public LBX storefront pages and same-origin JS for store-list hints."""
from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

OUT = Path("storefront_output")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36 MicroMessenger/8.0.53"
TARGETS = [
    "https://h5.mall.lbxcn.com/",
    "https://mall.lbxcn.com/",
    "https://mall.lbxcn.com/mall/",
]
KEYWORDS = ("store", "shop", "outlet", "nearby", "location", "longitude", "latitude", "门店", "附近门店", "药房")
URL_RE = re.compile(r"(?:(?:https?:)?//[^\s\"'<>]{5,}|/[A-Za-z0-9_./?=&%:@{}-]{5,})")


def fetch(url: str) -> dict:
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*"}, timeout=20, allow_redirects=True)
        return {"url": url, "status": r.status_code, "final_url": r.url, "content_type": r.headers.get("content-type", ""), "text": r.text, "length": len(r.content)}
    except Exception as exc:
        return {"url": url, "error": repr(exc), "text": "", "length": 0}


def same_origin(url: str, base: str) -> bool:
    a, b = urllib.parse.urlparse(url), urllib.parse.urlparse(base)
    return a.netloc == b.netloc or a.netloc.endswith(".lbxcn.com")


def static_scan() -> dict:
    pages, scripts, hits = [], {}, []
    for target in TARGETS:
        page = fetch(target)
        text = page.pop("text")
        pages.append(page)
        (OUT / (urllib.parse.urlparse(target).netloc.replace(".", "_") + "_" + str(len(pages)) + ".html")).write_text(text, encoding="utf-8", errors="ignore")
        if not text:
            continue
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.find_all("script", src=True):
            src = urllib.parse.urljoin(page.get("final_url", target), tag.get("src"))
            if same_origin(src, target):
                scripts[src] = None
    for idx, src in enumerate(sorted(scripts)):
        data = fetch(src)
        text = data.pop("text")
        scripts[src] = data
        (OUT / f"script_{idx:04d}.js").write_text(text, encoding="utf-8", errors="ignore")
        for match in URL_RE.findall(text):
            low = match.lower()
            if any(k.lower() in low for k in KEYWORDS):
                pos = text.find(match)
                hits.append({"script": src, "candidate": match[:1000], "context": text[max(0, pos-220):pos+len(match)+220]})
        for keyword in KEYWORDS:
            for m in re.finditer(re.escape(keyword), text, flags=re.I):
                context = text[max(0, m.start()-250):m.end()+350]
                if "/" in context or "http" in context.lower():
                    hits.append({"script": src, "candidate": keyword, "context": context})
                    if len(hits) > 10000:
                        break
    return {"pages": pages, "scripts": scripts, "hits": hits[:10000]}


async def browser_scan() -> list[dict]:
    reports = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 390, "height": 844})
        for target in TARGETS:
            page = await context.new_page()
            requests_seen, responses_seen = [], []
            page.on("request", lambda req, arr=requests_seen: arr.append({"method": req.method, "url": req.url, "resource_type": req.resource_type, "post_data": req.post_data}))
            page.on("response", lambda resp, arr=responses_seen: arr.append({"status": resp.status, "url": resp.url}))
            rec = {"url": target}
            try:
                resp = await page.goto(target, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(8000)
                rec.update({
                    "status": resp.status if resp else None,
                    "final_url": page.url,
                    "title": await page.title(),
                    "html_length": len(await page.content()),
                    "requests": requests_seen,
                    "responses": responses_seen,
                    "keyword_requests": [r for r in requests_seen if any(k.lower() in r["url"].lower() for k in KEYWORDS)],
                })
                await page.screenshot(path=str(OUT / (urllib.parse.urlparse(target).netloc.replace(".", "_") + "_browser.png")), full_page=True)
            except Exception as exc:
                rec.update({"error": repr(exc), "final_url": page.url, "requests": requests_seen, "responses": responses_seen})
            reports.append(rec)
            await page.close()
        await browser.close()
    return reports


def main() -> None:
    static = static_scan()
    browser = asyncio.run(browser_scan())
    report = {"static": static, "browser": browser}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "page_count": len(static["pages"]),
        "script_count": len(static["scripts"]),
        "static_hit_count": len(static["hits"]),
        "browser": [{"url": x.get("url"), "status": x.get("status"), "final_url": x.get("final_url"), "requests": len(x.get("requests", [])), "keyword_requests": len(x.get("keyword_requests", [])), "error": x.get("error", "")} for x in browser],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
