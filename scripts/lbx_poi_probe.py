#!/usr/bin/env python3
"""Discover public LBX Pharmacy store-data sources.

This script only performs ordinary public GET requests and a normal headless-browser
page load. It does not solve or bypass CAPTCHAs, authenticate, or access internal
systems. Results are written to probe_output for review.
"""
from __future__ import annotations

import gzip
import html
import json
import re
import shutil
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

OUT = Path("probe_output")
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    "Accept-Encoding": "gzip",
    "Cache-Control": "no-cache",
}
CTX = ssl.create_default_context()


def slug(value: str) -> str:
    value = re.sub(r"^https?://", "", value)
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("_")[:140]


def get(url: str, *, headers: dict[str, str] | None = None, timeout: int = 30) -> dict[str, Any]:
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            charset = resp.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            return {
                "ok": True,
                "status": resp.status,
                "url": url,
                "final_url": resp.geturl(),
                "content_type": resp.headers.get("Content-Type", ""),
                "length": len(raw),
                "elapsed": round(time.time() - started, 3),
                "text": text,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        if exc.headers and exc.headers.get("Content-Encoding", "").lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        text = raw.decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "length": len(raw),
            "elapsed": round(time.time() - started, 3),
            "text": text,
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": None,
            "url": url,
            "elapsed": round(time.time() - started, 3),
            "text": "",
            "error": repr(exc),
        }


def compact(result: dict[str, Any], preview: int = 500) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "text"} | {
        "preview": result.get("text", "")[:preview]
    }


def save_text(name: str, text: str) -> None:
    (OUT / name).write_text(text, encoding="utf-8")


def save_json(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_assets(base_url: str, page: str) -> tuple[list[str], list[str]]:
    scripts: list[str] = []
    links: list[str] = []
    for match in re.finditer(r"<(?:script|link)\b[^>]+?(?:src|href)\s*=\s*(['\"])(.*?)\1", page, re.I | re.S):
        value = html.unescape(match.group(2).strip())
        if value.startswith(("javascript:", "data:", "#")):
            continue
        absolute = urllib.parse.urljoin(base_url, value)
        if re.search(r"\.js(?:\?|$)", absolute, re.I):
            scripts.append(absolute)
        else:
            links.append(absolute)
    for match in re.finditer(r"<a\b[^>]+?href\s*=\s*(['\"])(.*?)\1", page, re.I | re.S):
        value = html.unescape(match.group(2).strip())
        if value.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
            continue
        links.append(urllib.parse.urljoin(base_url, value))
    return sorted(set(scripts)), sorted(set(links))


def extract_url_strings(text: str) -> list[str]:
    values = set()
    for match in re.finditer(r"https?://[^\s'\"<>\\)]+", text, re.I):
        values.add(html.unescape(match.group(0)).rstrip(".,;"))
    return sorted(values)


def keyword_snippets(text: str, terms: Iterable[str], radius: int = 180, limit: int = 120) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    lower = text.lower()
    seen: set[str] = set()
    for term in terms:
        needle = term.lower()
        start = 0
        while len(hits) < limit:
            pos = lower.find(needle, start)
            if pos < 0:
                break
            snippet = re.sub(r"\s+", " ", text[max(0, pos - radius): pos + len(term) + radius]).strip()
            signature = snippet[:100]
            if signature not in seen:
                hits.append({"term": term, "offset": pos, "snippet": snippet})
                seen.add(signature)
            start = pos + len(needle)
    return hits


def parse_possible_pois(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    name_keys = ("name", "wd", "title", "poi_name", "shop_name", "storeName", "store_name")
    address_keys = ("addr", "address", "address_norm", "poi_addr", "storeAddress", "store_address")

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            name = next((node.get(k) for k in name_keys if isinstance(node.get(k), str)), None)
            address = next((node.get(k) for k in address_keys if isinstance(node.get(k), str)), None)
            if name and ("药房" in name or "药店" in name or "老百姓" in name):
                record: dict[str, Any] = {"name": name}
                if address:
                    record["address"] = address
                for k in (
                    "uid", "id", "tel", "phone", "telephone", "x", "y", "lng", "lat",
                    "longitude", "latitude", "area", "district", "city", "province", "tag",
                    "type", "std_tag", "status", "business_time", "poiType",
                ):
                    if k in node and isinstance(node[k], (str, int, float, bool)):
                        record[k] = node[k]
                records.append(record)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = json.dumps(record, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


def discover_official_sites() -> dict[str, Any]:
    urls = [
        "https://www.lbxdrugs.com/",
        "https://www.lbxdrugs.com/about.html",
        "https://www.lbxdrugs.com/robots.txt",
        "https://www.lbxdrugs.com/sitemap.xml",
        "https://www.lbxdrugs.com/sitemap.txt",
        "https://mall.lbxcn.com/",
        "https://mall.lbxcn.com/mall",
        "https://www.lbxcn.com/",
        "https://m.lbxcn.com/",
        "https://h5.lbxcn.com/",
        "https://shop.lbxcn.com/",
        "https://store.lbxcn.com/",
        "https://api.lbxcn.com/",
        "https://mall-photo.lbxcn.com/",
        "https://jfsc.lbxcn.com/",
    ]
    report: list[dict[str, Any]] = []
    pages: list[tuple[str, str]] = []
    for url in urls:
        print(f"GET {url}", flush=True)
        split = urllib.parse.urlsplit(url)
        result = get(url, headers={"Referer": url, "Origin": f"{split.scheme}://{split.netloc}"})
        report.append(compact(result, 800))
        text = result.get("text", "")
        if result.get("ok") and text:
            save_text(f"site_{slug(url)}.txt", text[:1_500_000])
            if "html" in result.get("content_type", "").lower() or "<html" in text[:1000].lower():
                pages.append((result.get("final_url", url), text))
        time.sleep(0.35)

    scripts: list[str] = []
    links: list[str] = []
    for base, page in pages:
        page_scripts, page_links = extract_assets(base, page)
        scripts.extend(page_scripts)
        links.extend(page_links)

    scripts = sorted(set(scripts))
    links = sorted(set(links))
    js_report: list[dict[str, Any]] = []
    js_hits: list[dict[str, Any]] = []
    extracted_urls: set[str] = set()
    terms = [
        "门店", "附近门店", "store", "shop", "poi", "longitude", "latitude", "location",
        "storeList", "shopList", "nearby", "distance", "经度", "纬度", "address", "branch",
        "/api/", "graphql", "baseURL", "baseUrl", "requestUrl",
    ]
    for index, script_url in enumerate(scripts[:70], start=1):
        print(f"JS {index}/{min(len(scripts), 70)} {script_url}", flush=True)
        result = get(script_url, headers={"Referer": pages[0][0] if pages else "https://www.lbxdrugs.com/"})
        js_report.append(compact(result, 200))
        text = result.get("text", "")
        if result.get("ok") and text:
            extracted_urls.update(extract_url_strings(text))
            hits = keyword_snippets(text, terms, radius=220, limit=35)
            if hits:
                js_hits.append({"script": script_url, "hits": hits})
                save_text(f"js_hit_{index:02d}_{slug(script_url)}.txt", text[:2_000_000])
        time.sleep(0.2)

    interesting_links = [
        link for link in links
        if re.search(r"门店|药房|store|shop|map|location|near|contact|branch", urllib.parse.unquote(link), re.I)
    ]
    return {
        "pages": report,
        "script_count": len(scripts),
        "scripts": scripts,
        "links_count": len(links),
        "interesting_links": interesting_links,
        "js_requests": js_report,
        "js_hits": js_hits,
        "extracted_urls": sorted(extracted_urls),
    }


def discover_certificates() -> dict[str, Any]:
    result = get(
        "https://crt.sh/?q=%25.lbxcn.com&output=json",
        headers={"Referer": "https://crt.sh/", "Origin": "https://crt.sh"},
        timeout=45,
    )
    names: set[str] = set()
    parse_error = None
    if result.get("ok"):
        try:
            entries = json.loads(result["text"])
            for entry in entries:
                for raw in str(entry.get("name_value", "")).splitlines():
                    host = raw.strip().lower().removeprefix("*.")
                    if host.endswith(".lbxcn.com") or host == "lbxcn.com":
                        names.add(host)
        except Exception as exc:  # noqa: BLE001
            parse_error = repr(exc)
    consumer_pattern = re.compile(r"^(?:www|m|h5|mall|mall-photo|shop|store|api|open|mini|wx|member|jfsc|scep|static|cdn)(?:[.-]|\.)", re.I)
    blocked = re.compile(r"(?:^|[.-])(?:dev|test|uat|erp|scrm|admin|oa|vpn|intra|internal)(?:[.-]|$)", re.I)
    consumers = sorted(name for name in names if consumer_pattern.search(name) and not blocked.search(name))
    save_text("lbxcn_certificate_names.txt", "\n".join(sorted(names)))
    return {
        "request": compact(result, 300),
        "parse_error": parse_error,
        "count": len(names),
        "consumer_candidates": consumers,
    }


def probe_baidu() -> dict[str, Any]:
    keyword = "老百姓大药房"
    encoded = urllib.parse.quote(keyword)
    endpoints = [
        f"https://map.baidu.com/?qt=s&wd={encoded}&c=158&pn=0&nn=0",
        f"https://map.baidu.com/?newmap=1&qt=s&wd={encoded}&c=158&pn=0&nn=0",
        (
            "https://map.baidu.com/?newmap=1&reqflag=pcmap&biz=1&from=webmap"
            "&da_par=direct&pcevaname=pc4.1&qt=s&da_src=searchBox.button"
            f"&wd={encoded}&c=158&src=0&wd2=%E9%95%BF%E6%B2%99%E5%B8%82&pn=0&sug=0&l=12"
        ),
        f"https://map.baidu.com/search/{encoded}/@12573880.00,3267616.00,12z",
    ]
    report: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    for idx, url in enumerate(endpoints, start=1):
        print(f"BAIDU {idx} {url}", flush=True)
        result = get(
            url,
            headers={
                "Referer": "https://map.baidu.com/",
                "Origin": "https://map.baidu.com",
                "Accept": "application/json,text/plain,*/*",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        item = compact(result, 1200)
        text = result.get("text", "")
        parsed: Any = None
        if text:
            save_text(f"baidu_{idx}.txt", text[:2_000_000])
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r"^[^(]*\((.*)\)\s*;?\s*$", text, re.S)
                if match:
                    try:
                        parsed = json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass
        records = parse_possible_pois(parsed) if parsed is not None else []
        item["record_count"] = len(records)
        item["records_preview"] = records[:20]
        all_records.extend(records)
        report.append(item)
        time.sleep(0.5)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in all_records:
        key = str(record.get("uid") or "") + "|" + record.get("name", "") + "|" + record.get("address", "")
        if key not in seen:
            seen.add(key)
            unique.append(record)
    save_json("baidu_records.json", unique)
    return {"requests": report, "unique_records": unique}


def probe_amap_with_browser() -> dict[str, Any]:
    result: dict[str, Any] = {"attempted": True}
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except Exception as exc:  # noqa: BLE001
        return {"attempted": False, "error": f"selenium import failed: {exc!r}"}

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1200")
    options.add_argument(f"--user-agent={UA}")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(60)
        search_url = "https://www.amap.com/search?query=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF&city=430100"
        print(f"BROWSER {search_url}", flush=True)
        driver.get(search_url)
        time.sleep(12)
        result["title"] = driver.title
        result["current_url"] = driver.current_url
        result["body_preview"] = driver.find_element("tag name", "body").text[:8000]
        save_text("amap_browser_page.html", driver.page_source[:3_000_000])
        driver.save_screenshot(str(OUT / "amap_browser.png"))

        params = {
            "query_type": "TQUERY",
            "pagesize": "20",
            "pagenum": "1",
            "qii": "true",
            "cluster_state": "5",
            "need_utd": "true",
            "utd_sceneid": "1000",
            "div": "PC1000",
            "addr_poi_merge": "true",
            "is_classify": "true",
            "zoom": "10",
            "city": "430100",
            "keywords": "老百姓大药房",
        }
        endpoint = "https://www.amap.com/service/poiInfo?" + urllib.parse.urlencode(params)
        script = """
            const done = arguments[arguments.length - 1];
            fetch(arguments[0], {credentials: 'include', headers: {'Accept': 'application/json,text/plain,*/*'}})
              .then(async r => done({status: r.status, url: r.url, text: (await r.text()).slice(0, 200000)}))
              .catch(e => done({error: String(e)}));
        """
        browser_fetch = driver.execute_async_script(script, endpoint)
        result["browser_fetch"] = browser_fetch
        if isinstance(browser_fetch, dict):
            text = str(browser_fetch.get("text", ""))
            save_text("amap_browser_fetch.txt", text)
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            records = parse_possible_pois(parsed) if parsed is not None else []
            result["browser_fetch_records"] = records[:50]

        network_urls: list[dict[str, Any]] = []
        for entry in driver.get_log("performance"):
            try:
                message = json.loads(entry["message"])["message"]
            except Exception:  # noqa: BLE001
                continue
            if message.get("method") == "Network.responseReceived":
                response = message.get("params", {}).get("response", {})
                url = response.get("url", "")
                if any(token in url for token in ("poiInfo", "place", "search", "store", "shop")):
                    network_urls.append({
                        "url": url,
                        "status": response.get("status"),
                        "mimeType": response.get("mimeType"),
                    })
        result["network_matches"] = network_urls[:200]
        try:
            result["browser_console"] = driver.get_log("browser")[:100]
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        result["error"] = repr(exc)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass
    return result


def main() -> None:
    started = time.time()
    summary: dict[str, Any] = {}
    summary["certificates"] = discover_certificates()
    summary["official_sites"] = discover_official_sites()
    summary["baidu"] = probe_baidu()
    summary["amap_browser"] = probe_amap_with_browser()
    summary["elapsed_seconds"] = round(time.time() - started, 2)
    save_json("discovery_summary.json", summary)

    concise = {
        "elapsed_seconds": summary["elapsed_seconds"],
        "certificate_count": summary["certificates"].get("count"),
        "consumer_candidates": summary["certificates"].get("consumer_candidates", []),
        "official_pages": [
            {k: row.get(k) for k in ("status", "final_url", "content_type", "length", "error") if row.get(k) is not None}
            for row in summary["official_sites"].get("pages", [])
        ],
        "interesting_links": summary["official_sites"].get("interesting_links", [])[:50],
        "js_hit_files": [row.get("script") for row in summary["official_sites"].get("js_hits", [])],
        "baidu": [
            {
                "status": row.get("status"),
                "final_url": row.get("final_url"),
                "content_type": row.get("content_type"),
                "length": row.get("length"),
                "record_count": row.get("record_count"),
                "preview": row.get("preview", "")[:300],
            }
            for row in summary["baidu"].get("requests", [])
        ],
        "baidu_unique_records": len(summary["baidu"].get("unique_records", [])),
        "amap_browser": {
            "title": summary["amap_browser"].get("title"),
            "current_url": summary["amap_browser"].get("current_url"),
            "body_preview": summary["amap_browser"].get("body_preview", "")[:800],
            "browser_fetch": {
                k: summary["amap_browser"].get("browser_fetch", {}).get(k)
                for k in ("status", "url", "error")
            } if isinstance(summary["amap_browser"].get("browser_fetch"), dict) else None,
            "browser_fetch_text": str(summary["amap_browser"].get("browser_fetch", {}).get("text", ""))[:500]
            if isinstance(summary["amap_browser"].get("browser_fetch"), dict) else "",
            "network_matches": summary["amap_browser"].get("network_matches", [])[:20],
            "error": summary["amap_browser"].get("error"),
        },
    }
    save_json("discovery_concise.json", concise)
    print(json.dumps(concise, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
