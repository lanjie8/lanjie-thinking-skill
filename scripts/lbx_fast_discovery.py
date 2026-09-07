#!/usr/bin/env python3
"""Fast discovery of public LBX Pharmacy store data sources and official attachments."""
from __future__ import annotations

import concurrent.futures as cf
import io
import json
import os
import re
import threading
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook

OUT = Path("fast_output")
OUT.mkdir(exist_ok=True)
ATTACH_DIR = OUT / "candidate_attachments"
ATTACH_DIR.mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}
LOCAL = threading.local()


def session() -> requests.Session:
    s = getattr(LOCAL, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update(BASE_HEADERS)
        LOCAL.session = s
    return s


def get(url: str, *, timeout: int = 20, headers: dict[str, str] | None = None) -> requests.Response | None:
    try:
        r = session().get(url, timeout=timeout, headers=headers or {}, allow_redirects=True)
        return r
    except requests.RequestException:
        return None


def write_json(name: str, data: Any) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_name(text: str) -> str:
    text = urllib.parse.unquote(text)
    text = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", text).strip(" ._")
    return text[:180] or "attachment"


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    if soup.title:
        return soup.title.get_text(" ", strip=True)
    return ""


def extract_context(text: str, keywords: list[str], radius: int = 180, max_items: int = 80) -> list[str]:
    clean = re.sub(r"\s+", " ", BeautifulSoup(text, "html.parser").get_text(" ", strip=True) if "<" in text else text)
    low = clean.lower()
    out: list[str] = []
    for kw in keywords:
        start = 0
        needle = kw.lower()
        while len(out) < max_items:
            idx = low.find(needle, start)
            if idx < 0:
                break
            ctx = clean[max(0, idx-radius): min(len(clean), idx+len(kw)+radius)]
            if ctx not in out:
                out.append(ctx)
            start = idx + len(needle)
    return out


def discover_web_apps() -> dict[str, Any]:
    seeds = [
        "https://www.lbxdrugs.com/",
        "https://www.lbxdrugs.com/about.html",
        "https://scep.lbxcn.com/",
        "https://mall.lbxcn.com/",
        "https://mall.lbxcn.com/mall/",
        "https://mall.lbxcn.com/mall/index.html",
        "https://jfsc.lbxcn.com/",
    ]
    common_docs = [
        "swagger-ui.html", "doc.html", "swagger-resources", "v2/api-docs", "v3/api-docs",
        "openapi.json", "api-docs", "actuator", "actuator/gateway/routes",
    ]
    for base in ["https://mall.lbxcn.com/", "https://mall.lbxcn.com/mall/"]:
        seeds.extend(urllib.parse.urljoin(base, x) for x in common_docs)
    for service in [
        "scc-store", "scc-shop", "scc-member", "scc-point-member", "scc-product",
        "scc-goods", "scc-order", "scc-search", "scc-front", "scc-common", "scc-base",
    ]:
        for suffix in ["v3/api-docs", "v2/api-docs", "swagger-ui.html", "doc.html"]:
            seeds.append(f"https://mall.lbxcn.com/mall/{service}/{suffix}")

    records: list[dict[str, Any]] = []
    script_urls: set[str] = set()
    keyword_list = ["门店", "附近门店", "药房", "store", "shop", "location", "longitude", "latitude", "poi", "api"]
    for url in dict.fromkeys(seeds):
        r = get(url, headers={"Referer": urllib.parse.urljoin(url, "/")})
        if r is None:
            records.append({"url": url, "status": None, "error": "request_failed"})
            continue
        text = r.text
        rec: dict[str, Any] = {
            "url": url,
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("content-type"),
            "server": r.headers.get("server"),
            "length": len(r.content),
            "title": extract_title(text) if "html" in (r.headers.get("content-type") or "") or "<html" in text[:500].lower() else "",
            "contexts": extract_context(text[:5_000_000], keyword_list),
            "preview": text[:1500],
        }
        if "<html" in text[:2000].lower():
            soup = BeautifulSoup(text, "html.parser")
            for tag in soup.find_all("script", src=True):
                script_urls.add(urllib.parse.urljoin(r.url, tag.get("src")))
            rec["scripts"] = sorted({urllib.parse.urljoin(r.url, tag.get("src")) for tag in soup.find_all("script", src=True)})
            rec["links"] = sorted({urllib.parse.urljoin(r.url, a.get("href")) for a in soup.find_all("a", href=True)})[:300]
        records.append(rec)

    js_records: list[dict[str, Any]] = []
    endpoint_re = re.compile(r"(?:(?:https?:)?//[^\s\"'<>]+|/[A-Za-z0-9_./?=&%:-]{5,})")
    for url in sorted(script_urls)[:120]:
        r = get(url, timeout=30, headers={"Referer": "https://mall.lbxcn.com/"})
        if r is None:
            continue
        text = r.text
        contexts = extract_context(text[:8_000_000], keyword_list, radius=300)
        endpoints: list[str] = []
        for m in endpoint_re.findall(text[:8_000_000]):
            low = m.lower()
            if any(k in low for k in ["store", "shop", "location", "longitude", "latitude", "poi", "nearby", "distance"]):
                if m not in endpoints:
                    endpoints.append(m)
                    if len(endpoints) >= 300:
                        break
        js_records.append({
            "url": url,
            "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "length": len(r.content),
            "contexts": contexts,
            "candidate_endpoints": endpoints,
        })
        if contexts or endpoints:
            (OUT / ("js_" + safe_name(Path(urllib.parse.urlsplit(url).path).name) + ".txt")).write_text(text[:8_000_000], encoding="utf-8")

    report = {"pages": records, "scripts": js_records}
    write_json("web_app_discovery.json", report)
    return report


def map_probes() -> list[dict[str, Any]]:
    probes: list[tuple[str, str, dict[str, str]]] = []
    def baidu(code: str, page: int = 0) -> str:
        p = {
            "newmap": "1", "reqflag": "pcmap", "biz": "1", "from": "webmap", "qt": "s",
            "wd": "老百姓大药房", "c": code, "pn": str(page), "nn": str(page*10), "db": "0",
            "sug": "0", "addr": "0", "on_gel": "1", "src": "7", "gr": "3", "l": "12",
            "tn": "B_NORMAL_MAP", "ie": "utf-8",
        }
        return "https://map.baidu.com/?" + urllib.parse.urlencode(p)
    for code, city in [("158", "changsha"), ("131", "beijing"), ("233", "xian"), ("75", "shenzhen")]:
        probes.append((f"baidu_{city}", baidu(code), {"Referer": "https://map.baidu.com/", "X-Requested-With": "XMLHttpRequest"}))
    probes.extend([
        ("baidu_simple", "https://map.baidu.com/?qt=s&wd=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF&c=158&pn=0&nn=0", {"Referer": "https://map.baidu.com/"}),
        ("baidu_mobile", "https://map.baidu.com/mobile/webapp/search/search/qt=s&wd=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF&c=158", {"Referer": "https://map.baidu.com/"}),
        ("baidu_su", "https://map.baidu.com/su?wd=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF&cid=158&type=0&pc_ver=2", {"Referer": "https://map.baidu.com/"}),
        ("amap", "https://www.amap.com/service/poiInfo?query_type=TQUERY&pagesize=20&pagenum=1&qii=true&cluster_state=5&need_utd=true&utd_sceneid=1000&div=PC1000&addr_poi_merge=true&is_classify=true&zoom=10&city=430100&keywords=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF", {"Referer": "https://www.amap.com/", "Origin": "https://www.amap.com"}),
    ])
    out: list[dict[str, Any]] = []
    for name, url, headers in probes:
        r = get(url, headers=headers)
        if r is None:
            out.append({"name": name, "url": url, "status": None})
            continue
        body = r.text
        (OUT / f"map_{name}.txt").write_text(body[:10_000_000], encoding="utf-8")
        parsed = None
        try:
            parsed = r.json()
        except Exception:
            pass
        out.append({
            "name": name, "url": url, "status": r.status_code, "final_url": r.url,
            "content_type": r.headers.get("content-type"), "length": len(r.content),
            "json_type": type(parsed).__name__ if parsed is not None else None,
            "json_keys": list(parsed.keys())[:50] if isinstance(parsed, dict) else None,
            "preview": body[:2000],
        })
    write_json("map_probes.json", out)
    return out


ATTACH_EXTS = {".xlsx", ".xls", ".csv", ".zip", ".pdf", ".doc", ".docx"}
STORE_TERMS = ["门店", "药房", "药店", "网点", "地址", "配送", "暗访", "空调", "神秘顾客"]


def scan_notice(url: str) -> dict[str, Any] | None:
    r = get(url, timeout=12, headers={"Referer": "https://bidding.lbxdrugs.com/"})
    if r is None or r.status_code != 200 or len(r.content) < 500:
        return None
    text = r.text
    if "老百姓大药房连锁股份有限公司-非经营性招标采购管理系统" not in text and "采购公告" not in text and "变更公告" not in text:
        return None
    soup = BeautifulSoup(text, "html.parser")
    title = extract_title(text)
    full_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    attachments: list[dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(r.url, a.get("href"))
        path = urllib.parse.urlsplit(href).path
        ext = Path(path).suffix.lower()
        label = a.get_text(" ", strip=True)
        if ext in ATTACH_EXTS or "/u/cms/" in href:
            attachments.append({"url": href, "label": label, "ext": ext})
    if not attachments and not any(t in title + full_text for t in STORE_TERMS):
        return None
    return {
        "url": url, "title": title, "text_preview": full_text[:2500],
        "store_relevant": any(t in title + full_text for t in STORE_TERMS),
        "attachments": attachments,
    }


def inspect_xlsx(data: bytes, filename: str) -> dict[str, Any]:
    info: dict[str, Any] = {"filename": filename, "size": len(data), "sheets": []}
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        for ws in wb.worksheets:
            max_row = ws.max_row or 0
            max_col = ws.max_column or 0
            samples: list[list[str]] = []
            keyword_hits: set[str] = set()
            nonempty_rows = 0
            address_like_rows = 0
            for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                vals = ["" if v is None else str(v).strip() for v in row]
                if any(vals):
                    nonempty_rows += 1
                    if len(samples) < 20:
                        samples.append(vals[:30])
                    joined = " | ".join(vals)
                    for term in ["门店", "店名", "地址", "省", "市", "区", "电话", "经度", "纬度", "配送"]:
                        if term in joined:
                            keyword_hits.add(term)
                    if re.search(r"(省|市|区|县|街|路|号|镇|村)", joined) and len(joined) > 12:
                        address_like_rows += 1
                if idx >= 20000:
                    break
            info["sheets"].append({
                "name": ws.title, "max_row": max_row, "max_col": max_col,
                "nonempty_rows_scanned": nonempty_rows, "address_like_rows": address_like_rows,
                "keyword_hits": sorted(keyword_hits), "samples": samples,
            })
        wb.close()
    except Exception as exc:
        info["error"] = repr(exc)
    return info


def inspect_zip(data: bytes, filename: str) -> dict[str, Any]:
    info: dict[str, Any] = {"filename": filename, "size": len(data), "members": []}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.infolist()[:500]:
                info["members"].append({"name": member.filename, "size": member.file_size})
    except Exception as exc:
        info["error"] = repr(exc)
    return info


def download_and_inspect(item: dict[str, Any]) -> dict[str, Any]:
    url = item["url"]
    label = item.get("label") or Path(urllib.parse.urlsplit(url).path).name
    r = get(url, timeout=45, headers={"Referer": item.get("notice_url", "https://bidding.lbxdrugs.com/")})
    rec = dict(item)
    if r is None:
        rec["status"] = None
        return rec
    rec.update({"status": r.status_code, "content_type": r.headers.get("content-type"), "size": len(r.content)})
    if r.status_code != 200 or len(r.content) < 10:
        return rec
    ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    filename = safe_name(label)
    if not Path(filename).suffix:
        filename += ext
    if ext == ".xlsx" or r.content[:2] == b"PK" and "sheet" in label.lower():
        rec["inspection"] = inspect_xlsx(r.content, filename)
    elif ext == ".zip":
        rec["inspection"] = inspect_zip(r.content, filename)
    # Save spreadsheets/zips and any highly relevant attachment for later retrieval.
    relevance_text = (label + " " + item.get("notice_title", "")).lower()
    inspection_json = json.dumps(rec.get("inspection", {}), ensure_ascii=False)
    highly_relevant = any(t in relevance_text for t in ["门店", "地址", "网点", "配送", "暗访", "神秘顾客"]) or (
        '"max_row":' in inspection_json and any(k in inspection_json for k in ["门店", "地址", "店名"])
    )
    if ext in {".xlsx", ".xls", ".csv", ".zip"} and highly_relevant and len(r.content) <= 30_000_000:
        target = ATTACH_DIR / filename
        suffix = 1
        while target.exists():
            target = ATTACH_DIR / f"{Path(filename).stem}_{suffix}{Path(filename).suffix}"
            suffix += 1
        target.write_bytes(r.content)
        rec["saved_path"] = str(target)
    return rec


def scan_bidding_site() -> dict[str, Any]:
    urls: list[str] = []
    # Public notice ids observed in this range; scan three likely content channels.
    for notice_id in range(10000, 11380):
        for channel in ["cggg", "yushen", "jggg", "liubiao"]:
            urls.append(f"https://bidding.lbxdrugs.com/{channel}/{notice_id}.jhtml")
    notices: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        for result in ex.map(scan_notice, urls, chunksize=8):
            if result:
                notices.append(result)
    notices.sort(key=lambda x: x["url"])
    write_json("bidding_notices.json", notices)

    attachments: dict[str, dict[str, Any]] = {}
    for notice in notices:
        for a in notice["attachments"]:
            if a["url"] not in attachments:
                attachments[a["url"]] = {
                    **a,
                    "notice_url": notice["url"],
                    "notice_title": notice["title"],
                    "notice_store_relevant": notice["store_relevant"],
                }
    # Prioritize spreadsheets and store-relevant documents, but inspect all public spreadsheets.
    items = sorted(attachments.values(), key=lambda x: (
        0 if x.get("ext") in {".xlsx", ".xls", ".csv", ".zip"} else 1,
        0 if x.get("notice_store_relevant") else 1,
        x["url"],
    ))
    results: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for rec in ex.map(download_and_inspect, items, chunksize=2):
            results.append(rec)
    write_json("bidding_attachments.json", results)

    candidates = []
    for rec in results:
        inspection = rec.get("inspection") or {}
        score = 0
        text = (rec.get("label", "") + " " + rec.get("notice_title", "") + " " + json.dumps(inspection, ensure_ascii=False)).lower()
        for term, weight in [("门店", 5), ("店名", 5), ("地址", 4), ("配送", 2), ("网点", 3), ("电话", 2), ("经度", 3), ("纬度", 3)]:
            if term in text:
                score += weight
        max_rows = max([s.get("max_row", 0) or 0 for s in inspection.get("sheets", [])] or [0])
        if max_rows >= 100:
            score += 3
        if max_rows >= 1000:
            score += 5
        if score >= 5:
            candidates.append({**rec, "candidate_score": score, "max_rows": max_rows})
    candidates.sort(key=lambda x: (-x["candidate_score"], -x["max_rows"], x.get("label", "")))
    write_json("bidding_candidates.json", candidates)
    return {"notice_count": len(notices), "attachment_count": len(results), "candidates": candidates}


def main() -> None:
    started = time.time()
    print("Discovering official web apps", flush=True)
    web_apps = discover_web_apps()
    print("Probing map endpoints", flush=True)
    maps = map_probes()
    print("Scanning public bidding notices and attachments", flush=True)
    bidding = scan_bidding_site()
    summary = {
        "elapsed_seconds": round(time.time() - started, 2),
        "web_pages": len(web_apps["pages"]),
        "web_scripts": len(web_apps["scripts"]),
        "map_probes": maps,
        "bidding_notice_count": bidding["notice_count"],
        "bidding_attachment_count": bidding["attachment_count"],
        "top_bidding_candidates": bidding["candidates"][:50],
    }
    write_json("fast_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:30000], flush=True)


if __name__ == "__main__":
    main()
