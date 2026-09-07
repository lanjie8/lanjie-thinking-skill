#!/usr/bin/env python3
"""Discover public LBX Pharmacy store/POI data sources from a GitHub-hosted runner."""
from __future__ import annotations

import html
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

OUT = Path("probe_output")
OUT.mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}
CTX = ssl.create_default_context()


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.forms: list[dict[str, str]] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): v or "" for k, v in attrs}
        if tag.lower() == "a" and data.get("href"):
            self.links.append(data["href"])
        elif tag.lower() == "script" and data.get("src"):
            self.scripts.append(data["src"])
        elif tag.lower() == "form":
            self.forms.append(data)
        elif tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(x.strip() for x in self.title_parts if x.strip())


def decode_bytes(raw: bytes, headers: Any) -> str:
    # urllib may already have decoded transfer encoding; only decompress true gzip bytes.
    if raw.startswith(b"\x1f\x8b"):
        import gzip
        raw = gzip.decompress(raw)
    charset = None
    try:
        charset = headers.get_content_charset()
    except Exception:
        pass
    for enc in [charset, "utf-8", "gb18030", "latin-1"]:
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def request(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict[str, Any]:
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            raw = resp.read()
            text = decode_bytes(raw, resp.headers)
            return {
                "url": url,
                "status": resp.status,
                "final_url": resp.geturl(),
                "content_type": resp.headers.get("Content-Type"),
                "headers": dict(resp.headers.items()),
                "elapsed": round(time.time() - started, 3),
                "length": len(raw),
                "text": text,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return {
            "url": url,
            "status": exc.code,
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type") if exc.headers else None,
            "headers": dict(exc.headers.items()) if exc.headers else {},
            "elapsed": round(time.time() - started, 3),
            "length": len(raw),
            "text": decode_bytes(raw, exc.headers),
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "url": url,
            "status": None,
            "elapsed": round(time.time() - started, 3),
            "error": repr(exc),
            "text": "",
        }


def save_text(name: str, text: str) -> None:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:160]
    (OUT / safe).write_text(text, encoding="utf-8")


def strip_html(source: str) -> str:
    source = re.sub(r"(?is)<script\b.*?</script>", " ", source)
    source = re.sub(r"(?is)<style\b.*?</style>", " ", source)
    source = re.sub(r"(?s)<[^>]+>", " ", source)
    source = html.unescape(source)
    return re.sub(r"\s+", " ", source).strip()


def keyword_contexts(source: str, keywords: list[str], radius: int = 180) -> list[str]:
    text = strip_html(source) if "<" in source and ">" in source else source
    out: list[str] = []
    lower = text.lower()
    for keyword in keywords:
        start = 0
        needle = keyword.lower()
        while len(out) < 120:
            idx = lower.find(needle, start)
            if idx < 0:
                break
            context = text[max(0, idx - radius): min(len(text), idx + len(keyword) + radius)]
            context = re.sub(r"\s+", " ", context).strip()
            if context not in out:
                out.append(context)
            start = idx + len(needle)
    return out


def normalize_url(base: str, href: str) -> str | None:
    href = html.unescape(href.strip())
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    url = urllib.parse.urljoin(base, href)
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        return None
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def crawl_official() -> dict[str, Any]:
    seeds = [
        "https://www.lbxdrugs.com/",
        "https://www.lbxdrugs.com/about.html",
        "https://www.lbxdrugs.com/robots.txt",
        "https://www.lbxdrugs.com/sitemap.xml",
        "https://www.lbxdrugs.com/sitemap.txt",
    ]
    allowed_hosts = {"www.lbxdrugs.com", "lbxdrugs.com"}
    queue: deque[str] = deque(seeds)
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    scripts: set[str] = set()
    interesting_links: set[str] = set()
    keywords = ["门店", "药店", "药房", "网点", "store", "shop", "poi", "map", "api", "经纬度"]

    while queue and len(seen) < 160:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        result = request(url, {"Referer": "https://www.lbxdrugs.com/"})
        text = result.get("text", "")
        ctype = (result.get("content_type") or "").lower()
        record: dict[str, Any] = {
            "url": url,
            "status": result.get("status"),
            "final_url": result.get("final_url"),
            "content_type": result.get("content_type"),
            "length": result.get("length"),
            "error": result.get("error"),
            "contexts": keyword_contexts(text, keywords),
        }
        if result.get("status") == 200 and ("html" in ctype or "<html" in text[:1000].lower()):
            parser = LinkParser()
            try:
                parser.feed(text)
            except Exception:
                pass
            record["title"] = parser.title
            record["links_count"] = len(parser.links)
            record["scripts_count"] = len(parser.scripts)
            record["forms"] = parser.forms
            for href in parser.links:
                target = normalize_url(result.get("final_url") or url, href)
                if not target:
                    continue
                target_parts = urllib.parse.urlsplit(target)
                if any(k in target.lower() for k in keywords):
                    interesting_links.add(target)
                if target_parts.hostname in allowed_hosts:
                    ext = Path(target_parts.path).suffix.lower()
                    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx", ".mp4", ".mp3", ".woff", ".woff2", ".ttf", ".ico", ".css", ".js"}:
                        if target not in seen and len(queue) < 500:
                            queue.append(target)
            for src in parser.scripts:
                target = normalize_url(result.get("final_url") or url, src)
                if target:
                    scripts.add(target)
        pages.append(record)
        time.sleep(0.15)

    script_records: list[dict[str, Any]] = []
    endpoint_pattern = re.compile(r"(?:(?:https?:)?//[^\s\"'<>]+|/[A-Za-z0-9_./?=&%-]{4,})")
    for idx, url in enumerate(sorted(scripts)):
        if idx >= 100:
            break
        result = request(url, {"Referer": "https://www.lbxdrugs.com/"})
        text = result.get("text", "")
        contexts = keyword_contexts(text, keywords, radius=260)
        endpoints: list[str] = []
        if contexts:
            for match in endpoint_pattern.findall(text):
                low = match.lower()
                if any(k in low for k in ["store", "shop", "poi", "map", "api", "branch", "location"]):
                    if match not in endpoints:
                        endpoints.append(match)
                        if len(endpoints) >= 100:
                            break
        script_records.append({
            "url": url,
            "status": result.get("status"),
            "content_type": result.get("content_type"),
            "length": result.get("length"),
            "contexts": contexts,
            "candidate_endpoints": endpoints,
            "error": result.get("error"),
        })
        if contexts:
            save_text(f"official_js_{idx}.txt", text[:3_000_000])
        time.sleep(0.1)

    report = {
        "pages": pages,
        "scripts": script_records,
        "interesting_links": sorted(interesting_links),
        "seen_count": len(seen),
    }
    save_text("official_discovery.json", json.dumps(report, ensure_ascii=False, indent=2))
    return report


def crt_domains(domain: str) -> list[str]:
    url = f"https://crt.sh/?q=%25.{urllib.parse.quote(domain)}&output=json"
    result = request(url, {"Referer": "https://crt.sh/"}, timeout=60)
    names: set[str] = set()
    if result.get("status") == 200:
        try:
            data = json.loads(result.get("text", "[]"))
            for row in data:
                for name in str(row.get("name_value", "")).splitlines():
                    name = name.strip().lower().lstrip("*.")
                    if name == domain or name.endswith("." + domain):
                        names.add(name)
        except Exception as exc:  # noqa: BLE001
            save_text(f"crt_{domain}_error.txt", repr(exc) + "\n\n" + result.get("text", "")[:10000])
    return sorted(names)


def probe_domains(domains: list[str]) -> list[dict[str, Any]]:
    priority = sorted(domains, key=lambda d: (0 if any(k in d for k in ["api", "mall", "shop", "store", "map", "app", "wx", "mini", "h5", "m."]) else 1, d))
    records: list[dict[str, Any]] = []
    for domain in priority[:160]:
        for scheme in ["https", "http"]:
            url = f"{scheme}://{domain}/"
            result = request(url, {"Referer": url}, timeout=15)
            record = {
                "domain": domain,
                "url": url,
                "status": result.get("status"),
                "final_url": result.get("final_url"),
                "content_type": result.get("content_type"),
                "length": result.get("length"),
                "title": "",
                "contexts": keyword_contexts(result.get("text", ""), ["门店", "药店", "药房", "store", "shop", "api"]),
                "error": result.get("error"),
            }
            text = result.get("text", "")
            if "<html" in text[:2000].lower():
                parser = LinkParser()
                try:
                    parser.feed(text)
                    record["title"] = parser.title
                    record["scripts"] = [normalize_url(result.get("final_url") or url, s) for s in parser.scripts]
                    record["links"] = [normalize_url(result.get("final_url") or url, h) for h in parser.links[:100]]
                except Exception:
                    pass
            records.append(record)
            if result.get("status") and int(result["status"]) < 500:
                break
        time.sleep(0.1)
    return records


def baidu_url(city_code: str, keyword: str, page: int = 0) -> str:
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
        "pn": str(page),
        "nn": str(page * 10),
        "db": "0",
        "sug": "0",
        "addr": "0",
        "on_gel": "1",
        "src": "7",
        "gr": "3",
        "l": "12",
        "tn": "B_NORMAL_MAP",
        "ie": "utf-8",
    }
    return "https://map.baidu.com/?" + urllib.parse.urlencode(params)


def probe_map_endpoints() -> list[dict[str, Any]]:
    probes: list[tuple[str, str, dict[str, str]]] = []
    for code, city in [("158", "长沙"), ("131", "北京"), ("233", "西安"), ("75", "深圳")]:
        probes.append((f"baidu_{city}", baidu_url(code, "老百姓大药房", 0), {
            "Referer": "https://map.baidu.com/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json,text/plain,*/*",
        }))
    probes.extend([
        ("baidu_simple_changsha", "https://map.baidu.com/?qt=s&wd=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF&c=158&pn=0&nn=0", {"Referer": "https://map.baidu.com/"}),
        ("baidu_suggestion", "https://map.baidu.com/su?wd=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF&cid=158&type=0&pc_ver=2", {"Referer": "https://map.baidu.com/"}),
        ("amap_changsha", "https://www.amap.com/service/poiInfo?query_type=TQUERY&pagesize=20&pagenum=1&qii=true&cluster_state=5&need_utd=true&utd_sceneid=1000&div=PC1000&addr_poi_merge=true&is_classify=true&zoom=10&city=430100&keywords=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF", {"Referer": "https://www.amap.com/", "Origin": "https://www.amap.com"}),
    ])
    records: list[dict[str, Any]] = []
    for name, url, headers in probes:
        result = request(url, headers)
        text = result.get("text", "")
        save_text(f"{name}.txt", text[:5_000_000])
        records.append({
            "name": name,
            "url": url,
            "status": result.get("status"),
            "final_url": result.get("final_url"),
            "content_type": result.get("content_type"),
            "length": result.get("length"),
            "body_preview": text[:3000],
            "error": result.get("error"),
        })
        time.sleep(0.3)
    save_text("map_probe_report.json", json.dumps(records, ensure_ascii=False, indent=2))
    return records


def main() -> None:
    print("Discovering official site...", flush=True)
    official = crawl_official()
    print(f"Official pages={len(official['pages'])}, scripts={len(official['scripts'])}", flush=True)

    print("Enumerating certificate subdomains...", flush=True)
    all_domains: set[str] = set()
    crt_report: dict[str, list[str]] = {}
    for domain in ["lbxdrugs.com", "lbxcn.com"]:
        names = crt_domains(domain)
        crt_report[domain] = names
        all_domains.update(names)
        print(domain, len(names), flush=True)
    save_text("crt_domains.json", json.dumps(crt_report, ensure_ascii=False, indent=2))

    print("Probing discovered domains...", flush=True)
    domain_records = probe_domains(sorted(all_domains))
    save_text("domain_probe_report.json", json.dumps(domain_records, ensure_ascii=False, indent=2))

    print("Probing map endpoints...", flush=True)
    map_records = probe_map_endpoints()

    summary = {
        "official_seen_count": official["seen_count"],
        "official_interesting_links": official["interesting_links"],
        "official_pages_with_contexts": [x for x in official["pages"] if x.get("contexts")],
        "official_scripts_with_contexts": [x for x in official["scripts"] if x.get("contexts")],
        "crt_domains": crt_report,
        "domain_hits": [x for x in domain_records if x.get("status") or x.get("contexts")],
        "map_probes": map_records,
    }
    save_text("discovery_summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:20000], flush=True)


if __name__ == "__main__":
    main()
