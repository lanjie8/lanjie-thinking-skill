#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

OUT = Path("lbx_browser_probe_v4")
OUT.mkdir(exist_ok=True)
CAP = OUT / "captured"
CAP.mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:160] or "response"


def decode_qr() -> dict:
    result: dict = {"images": []}
    try:
        r = requests.get("https://www.lbxdrugs.com/about.html", timeout=40, headers={"User-Agent": UA})
        result["page_status"] = r.status_code
        soup = BeautifulSoup(r.text, "html.parser")
        candidates = []
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "") + " " + (img.get("title") or "")
            src = img.get("lazy") or img.get("src")
            if src and any(k in alt for k in ["扫码购药", "服务微信号", "小程序"]):
                candidates.append((alt.strip(), src))
        try:
            import cv2  # type: ignore
        except Exception as exc:
            result["opencv_error"] = repr(exc)
            return result
        detector = cv2.QRCodeDetector()
        for idx, (alt, url) in enumerate(candidates):
            ir = requests.get(url, timeout=40, headers={"User-Agent": UA, "Referer": r.url})
            path = OUT / f"qr_{idx}.jpg"
            path.write_bytes(ir.content)
            img = cv2.imread(str(path))
            decoded = ""
            points = None
            if img is not None:
                try:
                    decoded, points, _ = detector.detectAndDecode(img)
                except Exception:
                    decoded = ""
            result["images"].append({
                "alt": alt,
                "url": url,
                "status": ir.status_code,
                "size": len(ir.content),
                "decoded": decoded,
                "has_points": points is not None,
            })
    except Exception as exc:
        result["error"] = repr(exc)
    return result


def browser_probe() -> dict:
    from playwright.sync_api import sync_playwright

    records: list[dict] = []
    captured_count = 0

    def run_target(page, name: str, url: str, wait_ms: int = 15000) -> dict:
        nonlocal captured_count
        target_dir = OUT / name
        target_dir.mkdir(exist_ok=True)
        local_responses: list[dict] = []

        def on_response(response):
            nonlocal captured_count
            u = response.url
            low = u.lower()
            relevant = any(host in low for host in ["map.baidu.com", "amap.com", "lbxcn.com", "lbxdrugs.com"])
            relevant = relevant and any(key in low for key in ["qt=s", "poi", "search", "store", "shop", "location", "near", "mall", "api", "place"])
            if not relevant or captured_count >= 300:
                return
            item = {
                "url": u,
                "status": response.status,
                "content_type": response.headers.get("content-type"),
                "request_method": response.request.method,
                "resource_type": response.request.resource_type,
            }
            try:
                body = response.body()
                item["body_size"] = len(body)
                if len(body) <= 5_000_000:
                    ext = ".json" if "json" in (item["content_type"] or "") or body[:1] in [b"{", b"["] else ".txt"
                    fn = CAP / f"{captured_count:03d}_{safe_name(name)}_{safe_name(u.split('?')[0].split('/')[-1])}{ext}"
                    fn.write_bytes(body)
                    item["saved"] = str(fn)
                text = body.decode("utf-8", errors="replace")
                item["preview"] = text[:1200]
            except Exception as exc:
                item["body_error"] = repr(exc)
            captured_count += 1
            local_responses.append(item)

        page.on("response", on_response)
        started = time.time()
        rec: dict = {"name": name, "url": url}
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(wait_ms)
            rec.update({
                "status": resp.status if resp else None,
                "final_url": page.url,
                "title": page.title(),
                "elapsed": round(time.time() - started, 2),
                "body_text": page.locator("body").inner_text(timeout=10_000)[:100_000],
                "cookies": page.context.cookies(),
                "local_storage": page.evaluate("Object.fromEntries(Object.entries(localStorage))"),
                "session_storage": page.evaluate("Object.fromEntries(Object.entries(sessionStorage))"),
            })
            (target_dir / "page.html").write_text(page.content(), encoding="utf-8")
            (target_dir / "body.txt").write_text(rec["body_text"], encoding="utf-8")
            page.screenshot(path=str(target_dir / "screenshot.png"), full_page=True)
        except Exception as exc:
            rec["error"] = repr(exc)
            try:
                (target_dir / "page_error.html").write_text(page.content(), encoding="utf-8")
            except Exception:
                pass
        rec["responses"] = local_responses
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
        return rec

    with sync_playwright() as p:
        executable_candidates = [
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]
        executable = next((x for x in executable_candidates if Path(x).exists()), None)
        launch_args = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        }
        if executable:
            launch_args["executable_path"] = executable
        browser = p.chromium.launch(**launch_args)
        context = browser.new_context(
            user_agent=UA,
            locale="zh-CN",
            viewport={"width": 1440, "height": 1000},
            geolocation={"longitude": 112.9389, "latitude": 28.2283},
            permissions=["geolocation"],
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = context.new_page()

        targets = [
            (
                "baidu_mobile_changsha",
                "https://map.baidu.com/mobile/webapp/search/search/qt=s&wd=" + quote("老百姓大药房") + "&c=158",
                18000,
            ),
            (
                "baidu_search_changsha",
                "https://map.baidu.com/search/" + quote("老百姓大药房") + "/@12573000,3235000,12z?querytype=s&c=158&wd=" + quote("老百姓大药房"),
                18000,
            ),
            (
                "amap_search_changsha",
                "https://www.amap.com/search?query=" + quote("老百姓大药房") + "&city=430100&geoobj=112.5%7C27.8%7C113.4%7C28.7",
                18000,
            ),
            ("mall_root", "https://mall.lbxcn.com/", 10000),
            ("mall_path", "https://mall.lbxcn.com/mall/", 10000),
        ]
        for name, url, wait_ms in targets:
            records.append(run_target(page, name, url, wait_ms))

        evals = []
        probes = [
            "https://map.baidu.com/?qt=s&wd=" + quote("老百姓大药房") + "&c=158&pn=0&nn=0",
            "https://www.amap.com/service/poiInfo?query_type=TQUERY&pagesize=50&pagenum=1&qii=true&cluster_state=5&need_utd=true&utd_sceneid=1000&div=PC1000&addr_poi_merge=true&is_classify=true&zoom=10&city=430100&keywords=" + quote("老百姓大药房"),
        ]
        for u in probes:
            try:
                value = page.evaluate(
                    """async (url) => {
                        const r = await fetch(url, {credentials: 'include'});
                        return {status:r.status, url:r.url, headers:Object.fromEntries(r.headers.entries()), text:(await r.text()).slice(0,200000)};
                    }""",
                    u,
                )
                evals.append({"url": u, "result": value})
            except Exception as exc:
                evals.append({"url": u, "error": repr(exc)})
        browser.close()

    return {"records": records, "eval_fetch": evals}


def main() -> None:
    report = {
        "environment": {
            "chrome": next((p for p in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/usr/bin/chromium"] if Path(p).exists()), None),
            "cwd": os.getcwd(),
        },
        "qr": decode_qr(),
    }
    try:
        report["browser"] = browser_probe()
    except Exception as exc:
        report["browser_error"] = repr(exc)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:50_000])


if __name__ == "__main__":
    main()
