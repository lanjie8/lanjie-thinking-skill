#!/usr/bin/env python3
"""Crawl public Mapbar city pharmacy directories for LBX-branded stores.

The crawler is intentionally conservative:
- reads robots.txt and stops if category/detail URLs are disallowed;
- uses a single global rate limiter and retries;
- first enumerates city/category index pages, then fetches only matched details;
- keeps strict LBX-name matches separate from broad "百姓" pharmacy candidates.
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
import threading
import time
import urllib.parse
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://poi.mapbar.com"
OUT = Path("mapbar_output")
OUT.mkdir(exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

STRICT_TERMS = (
    "老百姓大药房",
    "老百姓健康药房",
    "老百姓健康大药房",
    "老百姓药房",
)
PHARMACY_WORDS = ("大药房", "药房", "药店", "医药")


class RateLimiter:
    def __init__(self, interval: float = 0.14) -> None:
        self.interval = interval
        self.lock = threading.Lock()
        self.next_time = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_time - now)
            self.next_time = max(now, self.next_time) + self.interval
        if delay:
            time.sleep(delay)
        time.sleep(random.uniform(0.005, 0.025))


RATE = RateLimiter(0.14)
_tls = threading.local()


def get_session() -> requests.Session:
    session = getattr(_tls, "session", None)
    if session is None:
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=12, pool_maxsize=12)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(HEADERS)
        _tls.session = session
    return session


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fetch(url: str, referer: str | None = None, timeout: int = 35) -> requests.Response:
    RATE.wait()
    headers = {"Referer": referer} if referer else None
    response = get_session().get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    return response


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def check_robots() -> dict[str, Any]:
    url = f"{BASE}/robots.txt"
    result: dict[str, Any] = {"url": url, "fetched": False, "category_allowed": None, "detail_allowed": None}
    try:
        response = get_session().get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        result.update({"fetched": True, "status": response.status_code, "text": response.text[:20000]})
        response.raise_for_status()
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(url)
        parser.parse(response.text.splitlines())
        result["category_allowed"] = parser.can_fetch(USER_AGENT, f"{BASE}/changsha/D30/")
        result["detail_allowed"] = parser.can_fetch(USER_AGENT, f"{BASE}/changsha/MAPIJPTPJEQOFWSRTPTRC")
    except Exception as exc:  # noqa: BLE001
        result["error"] = repr(exc)
    (OUT / "robots_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if result.get("category_allowed") is False or result.get("detail_allowed") is False:
        raise RuntimeError(f"Mapbar robots.txt disallows requested crawl paths: {result}")
    return result


def enumerate_cities() -> list[dict[str, str]]:
    response = fetch(f"{BASE}/", f"{BASE}/")
    soup = BeautifulSoup(response.text, "html.parser")
    cities: dict[str, dict[str, str]] = {}
    for anchor in soup.find_all("a", href=True):
        name = norm_text(anchor.get_text(" ", strip=True))
        absolute = urllib.parse.urljoin(response.url, anchor.get("href"))
        parsed = urllib.parse.urlparse(absolute)
        match = re.fullmatch(r"/([A-Za-z0-9_-]+)/", parsed.path)
        if parsed.netloc != "poi.mapbar.com" or not match:
            continue
        slug = match.group(1)
        if slug.lower() in {"search", "index", "map"}:
            continue
        if not name or name in {"中国", "中华人民共和国", "图吧", "首页"}:
            continue
        cities[slug] = {"city_name": name, "city_slug": slug, "city_url": absolute}
    result = sorted(cities.values(), key=lambda item: item["city_slug"])
    write_csv(OUT / "cities.csv", result, ["city_name", "city_slug", "city_url"])
    return result


def classify_name(name: str) -> str:
    compact = re.sub(r"\s+", "", name)
    if any(term in compact for term in STRICT_TERMS):
        return "严格匹配"
    if "百姓" in compact and any(word in compact for word in PHARMACY_WORDS):
        return "宽口径候选"
    return ""


def crawl_city_directory(city: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    category_url = urllib.parse.urljoin(city["city_url"], "D30/")
    started = time.time()
    strict: list[dict[str, str]] = []
    broad: list[dict[str, str]] = []
    try:
        response = fetch(category_url, city["city_url"])
        soup = BeautifulSoup(response.text, "html.parser")
        seen: set[str] = set()
        all_poi_links = 0
        for anchor in soup.find_all("a", href=True):
            name = norm_text(anchor.get_text(" ", strip=True))
            absolute = urllib.parse.urljoin(response.url, anchor.get("href"))
            parsed = urllib.parse.urlparse(absolute)
            if parsed.netloc != "poi.mapbar.com":
                continue
            if not re.fullmatch(rf"/{re.escape(city['city_slug'])}/MAP[A-Za-z0-9]+", parsed.path):
                continue
            all_poi_links += 1
            clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            if clean_url in seen:
                continue
            seen.add(clean_url)
            match_type = classify_name(name)
            if not match_type:
                continue
            item = {
                **city,
                "category_url": category_url,
                "directory_name": name,
                "detail_url": clean_url,
                "match_type": match_type,
                "source_id": parsed.path.rsplit("/", 1)[-1],
            }
            (strict if match_type == "严格匹配" else broad).append(item)
        stat = {
            **city,
            "category_url": category_url,
            "http_status": response.status_code,
            "html_bytes": len(response.content),
            "poi_link_count": all_poi_links,
            "unique_poi_link_count": len(seen),
            "strict_match_count": len(strict),
            "broad_match_count": len(broad),
            "elapsed_seconds": round(time.time() - started, 3),
            "error": "",
        }
        return stat, strict, broad
    except Exception as exc:  # noqa: BLE001
        stat = {
            **city,
            "category_url": category_url,
            "http_status": "",
            "html_bytes": "",
            "poi_link_count": 0,
            "unique_poi_link_count": 0,
            "strict_match_count": 0,
            "broad_match_count": 0,
            "elapsed_seconds": round(time.time() - started, 3),
            "error": repr(exc),
        }
        return stat, strict, broad


def parse_labeled_li(soup: BeautifulSoup, label: str) -> tuple[str, list[str]]:
    for li in soup.find_all("li"):
        text = norm_text(li.get_text(" ", strip=True))
        compact = text.replace(" ", "")
        if compact.startswith(label.replace(" ", "")):
            value = re.sub(rf"^{re.escape(label)}\s*", "", text, flags=re.I)
            links = [norm_text(a.get_text(" ", strip=True)) for a in li.find_all("a")]
            return value, [x for x in links if x]
    return "", []


def valid_lon_lat(lon: float, lat: float) -> bool:
    return 70.0 <= lon <= 140.0 and 0.0 <= lat <= 60.0


def mercator_to_lonlat(x: float, y: float) -> tuple[float, float] | None:
    try:
        lon = x / 20037508.34 * 180.0
        lat = y / 20037508.34 * 180.0
        lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        return (lon, lat) if valid_lon_lat(lon, lat) else None
    except Exception:
        return None


def extract_coordinates(html: str, soup: BeautifulSoup) -> tuple[str, str, str, str]:
    """Return longitude, latitude, method, diagnostic context."""
    # 1. Standard geo meta tags.
    meta_pos = soup.find("meta", attrs={"name": re.compile(r"geo\.position", re.I)})
    if meta_pos and meta_pos.get("content"):
        nums = re.findall(r"-?\d+(?:\.\d+)?", str(meta_pos.get("content")))
        if len(nums) >= 2:
            lat, lon = float(nums[0]), float(nums[1])
            if valid_lon_lat(lon, lat):
                return f"{lon:.7f}", f"{lat:.7f}", "geo.position", str(meta_pos)[:500]

    # 2. Named longitude/latitude pairs within a limited window.
    key_patterns = [
        re.compile(
            r"(?is)(?:lng|lon|longitude|pointx|mapx|x)\s*['\"]?\s*[:=]\s*['\"]?(-?\d+(?:\.\d+)?)['\"]?"
            r".{0,500}?"
            r"(?:lat|latitude|pointy|mapy|y)\s*['\"]?\s*[:=]\s*['\"]?(-?\d+(?:\.\d+)?)"
        ),
        re.compile(
            r"(?is)(?:lat|latitude|pointy|mapy|y)\s*['\"]?\s*[:=]\s*['\"]?(-?\d+(?:\.\d+)?)['\"]?"
            r".{0,500}?"
            r"(?:lng|lon|longitude|pointx|mapx|x)\s*['\"]?\s*[:=]\s*['\"]?(-?\d+(?:\.\d+)?)"
        ),
    ]
    for idx, pattern in enumerate(key_patterns):
        for match in pattern.finditer(html):
            a, b = float(match.group(1)), float(match.group(2))
            lon, lat = (a, b) if idx == 0 else (b, a)
            if valid_lon_lat(lon, lat):
                return f"{lon:.7f}", f"{lat:.7f}", "named_html", norm_text(match.group(0))[:500]
            if abs(lon) > 1_000_000 and abs(lat) > 1_000_000:
                converted = mercator_to_lonlat(lon, lat)
                if converted:
                    return f"{converted[0]:.7f}", f"{converted[1]:.7f}", "named_mercator", norm_text(match.group(0))[:500]

    # 3. Query parameters or data attributes in links/elements.
    lon_keys = ("lng", "lon", "longitude", "x", "pointx", "mapx")
    lat_keys = ("lat", "latitude", "y", "pointy", "mapy")
    for element in soup.find_all(True):
        candidates = []
        for attr in ("href", "src", "data-url", "data-href", "data-lng", "data-lat", "data-x", "data-y"):
            if element.has_attr(attr):
                candidates.append(str(element.get(attr)))
        for value in candidates:
            parsed = urllib.parse.urlparse(value)
            query = urllib.parse.parse_qs(parsed.query)
            attrs = {str(k).lower(): v for k, v in element.attrs.items()}
            values: dict[str, str] = {}
            for key, vals in query.items():
                if vals:
                    values[key.lower()] = str(vals[0])
            for key, val in attrs.items():
                if key.startswith("data-"):
                    values[key[5:]] = str(val)
            lon_val = next((values[k] for k in lon_keys if k in values), None)
            lat_val = next((values[k] for k in lat_keys if k in values), None)
            if lon_val and lat_val:
                try:
                    lon, lat = float(re.findall(r"-?\d+(?:\.\d+)?", lon_val)[0]), float(re.findall(r"-?\d+(?:\.\d+)?", lat_val)[0])
                    if valid_lon_lat(lon, lat):
                        return f"{lon:.7f}", f"{lat:.7f}", "url_or_data_attr", value[:500]
                    converted = mercator_to_lonlat(lon, lat)
                    if converted:
                        return f"{converted[0]:.7f}", f"{converted[1]:.7f}", "url_or_data_mercator", value[:500]
                except Exception:
                    pass
    return "", "", "", ""


def parse_detail(candidate: dict[str, str]) -> dict[str, Any]:
    started = time.time()
    result: dict[str, Any] = dict(candidate)
    result.update({
        "detail_name": "", "province": "", "city": candidate.get("city_name", ""), "district": "",
        "address_raw": "", "full_address": "", "phone": "", "category": "", "info_updated": "",
        "longitude": "", "latitude": "", "coordinate_method": "", "coordinate_context": "",
        "http_status": "", "html_bytes": "", "elapsed_seconds": "", "error": "",
    })
    try:
        response = fetch(candidate["detail_url"], candidate.get("category_url"))
        soup = BeautifulSoup(response.text, "html.parser")
        h1 = soup.find("h1")
        result["detail_name"] = norm_text(h1.get_text(" ", strip=True)) if h1 else candidate.get("directory_name", "")

        address_value, address_links = parse_labeled_li(soup, "地址：")
        phone_value, _ = parse_labeled_li(soup, "电话")
        category_value, _ = parse_labeled_li(soup, "所属分类：")
        if phone_value:
            phone_value = re.sub(r"^[：:]\s*", "", phone_value)
            phone_value = re.sub(r"\s*我要删除.*$", "", phone_value).strip()
        text = norm_text(soup.get_text(" ", strip=True))
        update_match = re.search(r"信息更新时间[：:]\s*([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2})", text)
        result["info_updated"] = update_match.group(1) if update_match else ""
        result["address_raw"] = address_value
        if address_links:
            result["district"] = address_links[1] if len(address_links) >= 2 else ""
        city_name = candidate.get("city_name", "")
        address_compact = address_value.replace(" ", "")
        result["full_address"] = address_value if city_name.replace("市", "") in address_compact else f"{city_name}{address_value}"
        result["phone"] = phone_value or ("无" if "电话无" in text[:2000].replace(" ", "") else "")
        result["category"] = re.sub(r"^[：:]\s*", "", category_value).strip()
        lon, lat, method, context = extract_coordinates(response.text, soup)
        result["longitude"], result["latitude"] = lon, lat
        result["coordinate_method"], result["coordinate_context"] = method, context
        result["http_status"] = response.status_code
        result["html_bytes"] = len(response.content)
    except Exception as exc:  # noqa: BLE001
        result["error"] = repr(exc)
    result["elapsed_seconds"] = round(time.time() - started, 3)
    return result


def enrich_admin_divisions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {"attempted": False, "success": False}
    try:
        import cpca  # type: ignore

        report["attempted"] = True
        addresses = [f"{row.get('city_name', '')}{row.get('full_address', '')}" for row in rows]
        frame = cpca.transform(addresses, cut=False, open_warning=False)
        for row, (_, parsed) in zip(rows, frame.iterrows()):
            province = norm_text(parsed.get("省"))
            city = norm_text(parsed.get("市"))
            district = norm_text(parsed.get("区"))
            if province:
                row["province"] = province
            if city:
                row["city"] = city
            if district and not row.get("district"):
                row["district"] = district
        report["success"] = True
    except Exception as exc:  # noqa: BLE001
        report["error"] = repr(exc)
    for row in rows:
        city = str(row.get("city_name", "")).replace("市", "")
        if not row.get("province") and city in {"北京", "上海", "天津", "重庆"}:
            row["province"] = f"{city}市"
            row["city"] = f"{city}市"
    return report


def canonical(value: str) -> str:
    value = norm_text(value).lower()
    value = re.sub(r"[（）()【】\[\]·•,，。.;；:：'\"“”‘’\-—_\s]", "", value)
    return value


def add_duplicate_groups(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        name = canonical(str(row.get("detail_name") or row.get("directory_name") or ""))
        address = canonical(str(row.get("full_address") or row.get("address_raw") or ""))
        phone = canonical(str(row.get("phone") or ""))
        key = "|".join([canonical(str(row.get("city") or row.get("city_name") or "")), name, address, phone])
        by_key.setdefault(key, []).append(idx)
    duplicate_groups = 0
    duplicate_rows = 0
    group_no = 0
    for indexes in by_key.values():
        if len(indexes) <= 1:
            continue
        group_no += 1
        duplicate_groups += 1
        duplicate_rows += len(indexes)
        for idx in indexes:
            rows[idx]["exact_duplicate_group"] = f"D{group_no:05d}"
            rows[idx]["exact_duplicate_count"] = len(indexes)
    for row in rows:
        row.setdefault("exact_duplicate_group", "")
        row.setdefault("exact_duplicate_count", 1)
    return {"duplicate_groups": duplicate_groups, "duplicate_rows": duplicate_rows}


def main() -> None:
    started = time.time()
    robots = check_robots()
    cities = enumerate_cities()
    print(f"Enumerated {len(cities)} city pages", flush=True)

    stats: list[dict[str, Any]] = []
    strict_candidates: list[dict[str, str]] = []
    broad_candidates: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(crawl_city_directory, city): city for city in cities}
        done = 0
        for future in as_completed(futures):
            stat, strict, broad = future.result()
            stats.append(stat)
            strict_candidates.extend(strict)
            broad_candidates.extend(broad)
            done += 1
            if done % 25 == 0 or strict:
                print(
                    f"cities={done}/{len(cities)} strict={len(strict_candidates)} broad={len(broad_candidates)} "
                    f"latest={stat.get('city_name')}:{stat.get('strict_match_count')}",
                    flush=True,
                )

    stats.sort(key=lambda row: str(row.get("city_slug", "")))
    strict_candidates = list({row["detail_url"]: row for row in strict_candidates}.values())
    broad_candidates = list({row["detail_url"]: row for row in broad_candidates if row["detail_url"] not in {x["detail_url"] for x in strict_candidates}}.values())
    strict_candidates.sort(key=lambda row: (row["city_name"], row["directory_name"], row["detail_url"]))
    broad_candidates.sort(key=lambda row: (row["city_name"], row["directory_name"], row["detail_url"]))

    candidate_fields = ["city_name", "city_slug", "directory_name", "match_type", "source_id", "detail_url", "category_url", "city_url"]
    write_csv(OUT / "strict_candidates.csv", strict_candidates, candidate_fields)
    write_csv(OUT / "broad_candidates.csv", broad_candidates, candidate_fields)
    write_csv(
        OUT / "city_stats.csv",
        stats,
        [
            "city_name", "city_slug", "city_url", "category_url", "http_status", "html_bytes",
            "poi_link_count", "unique_poi_link_count", "strict_match_count", "broad_match_count",
            "elapsed_seconds", "error",
        ],
    )
    print(f"Directory pass complete: strict={len(strict_candidates)} broad={len(broad_candidates)}", flush=True)

    details: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(parse_detail, item): item for item in strict_candidates}
        done = 0
        for future in as_completed(futures):
            details.append(future.result())
            done += 1
            if done % 100 == 0:
                errors = sum(bool(row.get("error")) for row in details)
                coords = sum(bool(row.get("longitude")) for row in details)
                print(f"details={done}/{len(strict_candidates)} errors={errors} coords={coords}", flush=True)

    admin_report = enrich_admin_divisions(details)
    duplicate_report = add_duplicate_groups(details)
    details.sort(key=lambda row: (str(row.get("province", "")), str(row.get("city", "")), str(row.get("district", "")), str(row.get("detail_name", "")), str(row.get("detail_url", ""))))
    detail_fields = [
        "province", "city", "district", "detail_name", "directory_name", "address_raw", "full_address",
        "phone", "longitude", "latitude", "coordinate_method", "category", "info_updated", "match_type",
        "exact_duplicate_group", "exact_duplicate_count", "source_id", "detail_url", "category_url", "city_url",
        "city_name", "city_slug", "http_status", "html_bytes", "elapsed_seconds", "error", "coordinate_context",
    ]
    write_csv(OUT / "strict_details.csv", details, detail_fields)
    write_csv(OUT / "detail_errors.csv", [row for row in details if row.get("error")], detail_fields)

    # A compact unique view removes only exact normalized duplicates; no fuzzy/address-only merging.
    unique_rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in details:
        key = "|".join([
            canonical(str(row.get("city") or row.get("city_name") or "")),
            canonical(str(row.get("detail_name") or row.get("directory_name") or "")),
            canonical(str(row.get("full_address") or row.get("address_raw") or "")),
            canonical(str(row.get("phone") or "")),
        ])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_rows.append(row)
    write_csv(OUT / "strict_details_exact_dedup.csv", unique_rows, detail_fields)

    diagnostic_rows = [
        {
            "detail_url": row.get("detail_url"),
            "name": row.get("detail_name"),
            "longitude": row.get("longitude"),
            "latitude": row.get("latitude"),
            "coordinate_method": row.get("coordinate_method"),
            "coordinate_context": row.get("coordinate_context"),
        }
        for row in details[:200]
    ]
    (OUT / "coordinate_diagnostics.json").write_text(json.dumps(diagnostic_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "crawl_started_epoch": started,
        "crawl_finished_epoch": time.time(),
        "elapsed_seconds": round(time.time() - started, 3),
        "robots": robots,
        "city_count": len(cities),
        "city_success_count": sum(not bool(row.get("error")) for row in stats),
        "city_error_count": sum(bool(row.get("error")) for row in stats),
        "total_directory_poi_links": sum(int(row.get("unique_poi_link_count") or 0) for row in stats),
        "strict_candidate_count": len(strict_candidates),
        "broad_candidate_count": len(broad_candidates),
        "strict_detail_count": len(details),
        "strict_detail_success_count": sum(not bool(row.get("error")) for row in details),
        "strict_detail_error_count": sum(bool(row.get("error")) for row in details),
        "exact_dedup_count": len(unique_rows),
        "phone_present_count": sum(bool(row.get("phone") and row.get("phone") != "无") for row in details),
        "address_present_count": sum(bool(row.get("full_address")) for row in details),
        "coordinate_present_count": sum(bool(row.get("longitude") and row.get("latitude")) for row in details),
        "admin_division_report": admin_report,
        "duplicate_report": duplicate_report,
        "top_cities": sorted(
            [
                {"city": row.get("city_name"), "strict": row.get("strict_match_count"), "broad": row.get("broad_match_count")}
                for row in stats
            ],
            key=lambda row: (-int(row.get("strict") or 0), str(row.get("city") or "")),
        )[:50],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
