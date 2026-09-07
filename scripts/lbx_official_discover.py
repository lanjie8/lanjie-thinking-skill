#!/usr/bin/env python3
"""Discover public LBX Pharmacy store-location data sources.

This script is intentionally read-only. It crawls public pages at a low rate,
extracts same-site links / API candidates, parses certificate-transparency
subdomains, and writes compact discovery reports for review.
"""
from __future__ import annotations

import concurrent.futures
import html
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from typing import Any, Iterable

OUT = Path("probe_output/discovery")
OUT.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}
CTX = ssl.create_default_context()

KEYWORDS = (
    "门店", "药店", "药房", "网点", "附近", "地址", "电话", "经纬度",
    "store", "shop", "branch", "location", "poi", "map", "dealer",
    "storelist", "shoplist", "store_list", "shop_list", "latitude",
    "longitude", "lng", "lat", "o2o", "mall", "门店列表", "门店查询",
)
API_WORDS = (
    "api", "store", "shop", "branch", "location", "poi", "map", "nearby",
    "latitude", "longitude", "lng", "lat", "门店", "药店", "药房", "网点",
)


def request(url: str, *, timeout: int = 25, max_bytes: int = 5_000_000,
            headers: dict[str, str] | None = None) -> dict[str, Any]:
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            raw = resp.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            raw = raw[:max_bytes]
            charset = resp.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            return {
                "url": url,
                "status": int(resp.status),
                "final_url": resp.geturl(),
                "content_type": resp.headers.get("Content-Type", ""),
                "length": len(raw),
                "truncated": truncated,
                "elapsed": round(time.time() - start, 3),
                "text": text,
            }
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(max_bytes)
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return {
            "url": url,
            "status": int(exc.code),
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "length": len(text.encode("utf-8", errors="ignore")),
            "elapsed": round(time.time() - start, 3),
            "error": str(exc),
            "text": text,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "url": url,
            "status": None,
            "elapsed": round(time.time() - start, 3),
            "error": repr(exc),
            "text": "",
        }


def normalise_url(base: str, candidate: str) -> str | None:
    candidate = html.unescape(candidate.strip())
    if not candidate or candidate.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
        return None
    try:
        url = urllib.parse.urljoin(base, candidate)
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            return None
        # Remove fragment; retain query because API candidates may use it.
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))
    except Exception:
        return None


def extract_links(base: str, text: str) -> tuple[set[str], set[str], set[str]]:
    hrefs: set[str] = set()
    scripts: set[str] = set()
    absolute: set[str] = set()
    for match in re.finditer(r"(?is)\b(?:href|action)\s*=\s*['\"]([^'\"]+)['\"]", text):
        u = normalise_url(base, match.group(1))
        if u:
            hrefs.add(u)
    for match in re.finditer(r"(?is)\bsrc\s*=\s*['\"]([^'\"]+)['\"]", text):
        u = normalise_url(base, match.group(1))
        if u:
            scripts.add(u)
    for match in re.finditer(r"https?://[^\s'\"<>\\]+", text):
        u = normalise_url(base, match.group(0).rstrip("),.;"))
        if u:
            absolute.add(u)
    return hrefs, scripts, absolute


def text_snippets(text: str, words: Iterable[str], radius: int = 140, limit: int = 80) -> list[str]:
    compact = re.sub(r"\s+", " ", html.unescape(text))
    lower = compact.lower()
    snippets: list[str] = []
    seen: set[str] = set()
    for word in words:
        start = 0
        w = word.lower()
        while len(snippets) < limit:
            idx = lower.find(w, start)
            if idx < 0:
                break
            snippet = compact[max(0, idx - radius): min(len(compact), idx + len(w) + radius)]
            snippet = snippet.strip()
            key = snippet[:220]
            if key not in seen:
                seen.add(key)
                snippets.append(snippet)
            start = idx + max(1, len(w))
    return snippets


def keyword_score(value: str, words: Iterable[str] = KEYWORDS) -> int:
    low = urllib.parse.unquote(value).lower()
    return sum(1 for w in words if w.lower() in low)


def parse_sitemap(text: str, base: str) -> list[str]:
    urls: list[str] = []
    try:
        root = ET.fromstring(text)
        for elem in root.iter():
            if elem.tag.endswith("loc") and elem.text:
                u = normalise_url(base, elem.text)
                if u:
                    urls.append(u)
    except Exception:
        for match in re.finditer(r"(?is)<loc>\s*(.*?)\s*</loc>", text):
            u = normalise_url(base, match.group(1))
            if u:
                urls.append(u)
    return urls


def discover_official() -> dict[str, Any]:
    host = "www.lbxdrugs.com"
    seeds = [
        "https://www.lbxdrugs.com/",
        "https://www.lbxdrugs.com/about.html",
        "https://www.lbxdrugs.com/robots.txt",
        "https://www.lbxdrugs.com/sitemap.xml",
        "https://www.lbxdrugs.com/sitemap_index.xml",
        "https://www.lbxdrugs.com/sitemap.txt",
    ]
    guessed = [
        "stores.html", "store.html", "store-list.html", "storeList.html",
        "shops.html", "shop.html", "branches.html", "branch.html",
        "map.html", "service.html", "contact.html", "join.html",
        "stores", "store", "shop", "branches", "map", "location",
    ]
    seeds.extend(f"https://www.lbxdrugs.com/{x}" for x in guessed)

    fetched: dict[str, dict[str, Any]] = {}
    all_links: set[str] = set()
    all_scripts: set[str] = set()
    absolute_urls: set[str] = set()
    sitemap_urls: set[str] = set()
    page_hits: list[dict[str, Any]] = []

    # Fetch explicit seeds first.
    for url in seeds:
        r = request(url)
        fetched[url] = {k: v for k, v in r.items() if k != "text"}
        text = r.get("text", "")
        if r.get("status") == 200 and text:
            hrefs, scripts, abs_urls = extract_links(r.get("final_url", url), text)
            all_links |= hrefs
            all_scripts |= scripts
            absolute_urls |= abs_urls
            if "xml" in r.get("content_type", "").lower() or "sitemap" in url:
                sitemap_urls |= set(parse_sitemap(text, r.get("final_url", url)))
            score = keyword_score(text)
            if score:
                page_hits.append({
                    "url": url,
                    "status": r.get("status"),
                    "length": r.get("length"),
                    "score": score,
                    "snippets": text_snippets(text, KEYWORDS, limit=25),
                })
        time.sleep(0.15)

    # Robots can point to non-standard sitemap URLs.
    robots_text = request("https://www.lbxdrugs.com/robots.txt").get("text", "")
    for m in re.finditer(r"(?im)^\s*Sitemap:\s*(\S+)", robots_text):
        u = normalise_url("https://www.lbxdrugs.com/robots.txt", m.group(1))
        if u:
            rr = request(u)
            fetched[u] = {k: v for k, v in rr.items() if k != "text"}
            sitemap_urls |= set(parse_sitemap(rr.get("text", ""), u))

    # Follow sitemap indexes once.
    sitemap_children = [u for u in sitemap_urls if "sitemap" in u.lower() or u.lower().endswith(".xml")]
    for u in sitemap_children[:100]:
        rr = request(u)
        fetched[u] = {k: v for k, v in rr.items() if k != "text"}
        if rr.get("status") == 200:
            sitemap_urls |= set(parse_sitemap(rr.get("text", ""), u))
        time.sleep(0.1)

    # Candidate pages: keyword URLs from navigation and sitemap, then a bounded breadth crawl.
    candidates = sorted(
        {u for u in all_links | sitemap_urls if urllib.parse.urlsplit(u).netloc.endswith(host)},
        key=lambda u: (-keyword_score(u), u),
    )
    high_value = [u for u in candidates if keyword_score(u) > 0]
    # Include a bounded selection of all sitemap pages to find pages whose URL is opaque.
    scan_urls = list(dict.fromkeys(high_value + candidates[:350]))[:450]
    for idx, url in enumerate(scan_urls):
        if url in fetched:
            continue
        r = request(url)
        fetched[url] = {k: v for k, v in r.items() if k != "text"}
        text = r.get("text", "")
        if r.get("status") == 200 and text:
            hrefs, scripts, abs_urls = extract_links(r.get("final_url", url), text)
            all_links |= hrefs
            all_scripts |= scripts
            absolute_urls |= abs_urls
            score = keyword_score(text)
            if score:
                page_hits.append({
                    "url": url,
                    "status": r.get("status"),
                    "length": r.get("length"),
                    "score": score,
                    "snippets": text_snippets(text, KEYWORDS, limit=25),
                })
        if idx % 20 == 19:
            time.sleep(0.5)
        else:
            time.sleep(0.08)

    # Fetch site-owned JS plus highly relevant external JS; grep endpoints and store terms.
    js_candidates = [
        u for u in all_scripts
        if u.lower().split("?", 1)[0].endswith((".js", ".mjs"))
        and ("lbxdrugs.com" in u or keyword_score(u, API_WORDS) > 0)
    ]
    js_candidates = sorted(js_candidates, key=lambda u: (-keyword_score(u, API_WORDS), u))[:80]
    js_hits: list[dict[str, Any]] = []
    endpoint_candidates: set[str] = set()
    path_re = re.compile(
        r"(?i)(?:https?://[^\s'\"<>\\]+|/(?:[A-Za-z0-9_.~!$&()*+,;=:@%?-]+/){0,8}[A-Za-z0-9_.~!$&()*+,;=:@%?/-]*)"
    )
    for idx, url in enumerate(js_candidates):
        r = request(url, max_bytes=8_000_000)
        text = r.get("text", "")
        if r.get("status") == 200 and text:
            snippets = text_snippets(text, API_WORDS, radius=180, limit=80)
            if snippets:
                js_hits.append({
                    "url": url,
                    "length": r.get("length"),
                    "score": keyword_score(text, API_WORDS),
                    "snippets": snippets,
                })
            for m in path_re.finditer(text):
                value = m.group(0).rstrip("),.;}")
                if keyword_score(value, API_WORDS) > 0:
                    u = normalise_url(url, value)
                    if u:
                        endpoint_candidates.add(u)
        time.sleep(0.1)

    relevant_links = sorted(
        (all_links | absolute_urls | endpoint_candidates),
        key=lambda u: (-keyword_score(u), u),
    )
    return {
        "summary": {
            "fetched_count": len(fetched),
            "sitemap_url_count": len(sitemap_urls),
            "link_count": len(all_links),
            "script_count": len(all_scripts),
            "page_hit_count": len(page_hits),
            "js_hit_count": len(js_hits),
            "endpoint_candidate_count": len(endpoint_candidates),
        },
        "fetched": fetched,
        "sitemap_urls": sorted(sitemap_urls),
        "relevant_links": [u for u in relevant_links if keyword_score(u) > 0][:1000],
        "scripts": sorted(all_scripts),
        "page_hits": sorted(page_hits, key=lambda x: (-x["score"], x["url"])),
        "js_hits": sorted(js_hits, key=lambda x: (-x["score"], x["url"])),
        "endpoint_candidates": sorted(endpoint_candidates),
    }


def discover_lbxcn_subdomains() -> dict[str, Any]:
    crt = request("https://crt.sh/?q=%25.lbxcn.com&output=json", max_bytes=20_000_000)
    names: set[str] = set()
    try:
        entries = json.loads(crt.get("text", "[]"))
        for item in entries:
            for field in ("name_value", "common_name"):
                for name in str(item.get(field, "")).splitlines():
                    name = name.strip().lower().lstrip("*.")
                    if name == "lbxcn.com" or name.endswith(".lbxcn.com"):
                        if re.fullmatch(r"[a-z0-9.-]+", name):
                            names.add(name)
    except Exception as exc:  # noqa: BLE001
        entries = []
        parse_error = repr(exc)
    else:
        parse_error = None

    # Add known / likely public hosts found from prior official references.
    names.update({
        "lbxcn.com", "www.lbxcn.com", "mall.lbxcn.com", "mall-photo.lbxcn.com",
        "o2o.lbxcn.com", "www.o2o.lbxcn.com", "jfsc.lbxcn.com",
        "api.lbxcn.com", "m.lbxcn.com", "wap.lbxcn.com", "map.lbxcn.com",
    })

    priority = sorted(names, key=lambda n: (-keyword_score(n, API_WORDS), n))
    # Probe every CT host, but cap to prevent excessive traffic.
    priority = priority[:350]

    def probe_host(host: str) -> dict[str, Any]:
        paths = ["/"]
        if host in {"mall.lbxcn.com", "www.lbxcn.com", "lbxcn.com"}:
            paths += ["/mall", "/robots.txt", "/sitemap.xml"]
        if "o2o" in host:
            paths += ["/robots.txt", "/sitemap.xml", "/api", "/swagger-ui.html", "/v3/api-docs"]
        attempts: list[dict[str, Any]] = []
        for scheme in ("https", "http"):
            for path in paths:
                url = f"{scheme}://{host}{path}"
                r = request(url, timeout=12, max_bytes=1_500_000)
                meta = {k: v for k, v in r.items() if k != "text"}
                text = r.get("text", "")
                meta["title"] = ""
                mt = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
                if mt:
                    meta["title"] = re.sub(r"\s+", " ", html.unescape(mt.group(1))).strip()[:300]
                meta["keyword_score"] = keyword_score(text, API_WORDS)
                meta["snippets"] = text_snippets(text, API_WORDS, radius=120, limit=15)
                hrefs, scripts, absolute = extract_links(r.get("final_url", url), text)
                meta["relevant_links"] = sorted(
                    [u for u in hrefs | scripts | absolute if keyword_score(u, API_WORDS) > 0]
                )[:100]
                attempts.append(meta)
                if r.get("status") and r.get("status") < 500 and text:
                    break
            if any(a.get("status") and a.get("status") < 500 for a in attempts):
                break
        return {"host": host, "attempts": attempts}

    host_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(probe_host, host): host for host in priority}
        for fut in concurrent.futures.as_completed(futs):
            try:
                host_results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                host_results.append({"host": futs[fut], "error": repr(exc), "attempts": []})

    active = []
    for item in host_results:
        if any(a.get("status") is not None for a in item.get("attempts", [])):
            active.append(item)
    active.sort(key=lambda x: (-max((a.get("keyword_score", 0) for a in x.get("attempts", [])), default=0), x["host"]))
    return {
        "summary": {
            "crt_entry_count": len(entries),
            "subdomain_count": len(names),
            "probed_count": len(priority),
            "active_or_http_response_count": len(active),
            "parse_error": parse_error,
        },
        "subdomains": priority,
        "active_hosts": active,
    }


def write_compact_text(official: dict[str, Any], subdomains: dict[str, Any]) -> None:
    lines = ["# LBX Official Data Source Discovery", "", "## Official site summary", json.dumps(official["summary"], ensure_ascii=False)]
    lines += ["", "## Relevant official URLs"] + official.get("relevant_links", [])
    lines += ["", "## Endpoint candidates"] + official.get("endpoint_candidates", [])
    lines += ["", "## Active lbxcn.com hosts"]
    for item in subdomains.get("active_hosts", []):
        for a in item.get("attempts", []):
            lines.append(
                f"{item['host']}\t{a.get('status')}\t{a.get('final_url', a.get('url'))}\t{a.get('title','')}\tscore={a.get('keyword_score',0)}"
            )
    (OUT / "discovery_summary.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    print("Discovering official lbxdrugs.com pages and scripts...", flush=True)
    official = discover_official()
    (OUT / "official_discovery.json").write_text(
        json.dumps(official, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(official["summary"], ensure_ascii=False), flush=True)

    print("Discovering lbxcn.com subdomains...", flush=True)
    subdomains = discover_lbxcn_subdomains()
    (OUT / "lbxcn_subdomains.json").write_text(
        json.dumps(subdomains, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(subdomains["summary"], ensure_ascii=False), flush=True)
    write_compact_text(official, subdomains)


if __name__ == "__main__":
    main()
