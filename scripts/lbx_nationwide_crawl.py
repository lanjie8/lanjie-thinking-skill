#!/usr/bin/env python3
"""Nationwide crawl of the public LBX nearby-store endpoint.

The legacy public H5 endpoint returns at most ten nearby records per request and
ignores ordinary pagination/radius parameters.  This crawler combines:
1. all prefecture-level city centres from AMap's public city-list snapshot;
2. a coarse nationwide grid; and
3. recursive expansion from every newly discovered store coordinate.

Outputs are UTF-8 CSV/JSON files for downstream workbook generation.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import html
import json
import math
import os
import random
import re
import threading
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
OFFICIAL_ABOUT = "https://www.lbxdrugs.com/about.html"
CITY_LIST_PATH = Path("probe_output/amap_city_list.txt")
OUT = Path("nationwide_crawl_output")
OUT.mkdir(exist_ok=True)

WORKERS = int(os.getenv("LBX_WORKERS", "12"))
GRID_STEP = float(os.getenv("LBX_GRID_STEP", "1.0"))
MAX_QUERIES = int(os.getenv("LBX_MAX_QUERIES", "32000"))
TIMEOUT_SECONDS = float(os.getenv("LBX_TIMEOUT", "12"))
MAX_RETRIES = int(os.getenv("LBX_RETRIES", "3"))
OFFICIAL_STORE_BENCHMARK = 15001

_tls = threading.local()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html",
}

API_FIELDS = [
    "third_org_name", "deptName", "latGd", "distance", "city", "lngGd",
    "winter_start_hours", "contactPerson", "shopLabels", "distanceGd",
    "shipStartTime", "sap_id", "pdeptId", "third_org_code", "org_name",
    "winter_closing_hours", "lat", "latBd", "companyCode",
    "summer_closing_hours", "lngBd", "lng", "is_m_shop", "distanceBd",
    "is_close", "deptType", "summer_start_hours", "shop_id", "parentName",
    "phone", "sales_scan_name", "deptAddr", "org_code", "sales_scan_id",
    "shipEndTime",
]

EXPORT_FIELDS = [
    "province", "city", "deptName", "classification", "is_pharmacy",
    "business_status", "deptAddr", "phone", "parentName", "org_name",
    "third_org_name", "contactPerson", "shopLabels", "sales_scan_name",
    "summer_hours", "winter_hours", "delivery_hours", "lngGd", "latGd",
    "lngBd", "latBd", "lng", "lat", "sap_id", "shop_id", "org_code",
    "third_org_code", "companyCode", "pdeptId", "deptType", "is_m_shop",
    "sales_scan_id", "api_entity_count", "all_shop_ids", "all_sap_ids",
    "all_org_codes", "alternate_names", "source_url", "crawled_at_utc",
]

NON_PHARMACY_RE = re.compile(
    r"诊所|医院|医馆|门诊|门诊部|卫生所|卫生室|体检|医疗美容|护理院|养老院|康复中心|口腔|眼科"
)
PHARMACY_RE = re.compile(r"药房|药店|大药房|健康药房|医药|药业|药局|药品|药馆")
MAIN_BRAND_RE = re.compile(r"老百姓")


def clean(value: Any) -> str:
    if value is None:
        return ""
    return html.unescape(str(value)).strip()


def norm_text(value: Any) -> str:
    return re.sub(r"[\s\-—_·（）()【】\[\]，,。./\\]+", "", clean(value)).lower()


def safe_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return None


def get_session() -> requests.Session:
    session = getattr(_tls, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=WORKERS * 2, pool_maxsize=WORKERS * 2)
        session.mount("https://", adapter)
        _tls.session = session
    return session


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    inner = payload.get("data")
    if isinstance(inner, dict):
        rows = inner.get("data")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    rows = payload.get("data")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def fetch_point(point: tuple[float, float, str]) -> dict[str, Any]:
    lat, lon, seed_type = point
    params = {"Latitude": f"{lat:.7f}", "Longitude": f"{lon:.7f}"}
    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(random.uniform(0.01, 0.05))
            response = get_session().get(ENDPOINT, params=params, timeout=TIMEOUT_SECONDS)
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = f"HTTP {response.status_code}"
                time.sleep(0.4 * (2**attempt) + random.random() * 0.2)
                continue
            response.raise_for_status()
            payload = response.json()
            rows = extract_rows(payload)
            return {
                "ok": True,
                "point": point,
                "rows": rows,
                "status": response.status_code,
                "elapsed": response.elapsed.total_seconds(),
            }
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
            time.sleep(0.4 * (2**attempt) + random.random() * 0.2)
    return {"ok": False, "point": point, "rows": [], "error": last_error, "seed_type": seed_type}


def point_key(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 5), round(lon, 5)


def store_coords(row: dict[str, Any]) -> tuple[float, float] | None:
    for lat_field, lon_field in (("latGd", "lngGd"), ("lat", "lng"), ("latBd", "lngBd")):
        lat = safe_float(row.get(lat_field))
        lon = safe_float(row.get(lon_field))
        if lat is None or lon is None:
            continue
        if 3.0 <= lat <= 60.0 and 70.0 <= lon <= 140.0:
            return lat, lon
    return None


def raw_entity_key(row: dict[str, Any]) -> str:
    for field in ("shop_id", "sap_id", "org_code"):
        value = clean(row.get(field))
        if value and value not in {"0", "null", "None"}:
            return f"{field}:{value}"
    coords = store_coords(row)
    basis = {
        "name": norm_text(row.get("deptName") or row.get("org_name")),
        "address": norm_text(row.get("deptAddr")),
        "phone": re.sub(r"\D", "", clean(row.get("phone"))),
        "coords": point_key(*coords) if coords else None,
    }
    return "hash:" + hashlib.sha1(
        json.dumps(basis, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def canonical_key(row: dict[str, Any]) -> str:
    org_code = clean(row.get("org_code"))
    if org_code and org_code not in {"0", "null", "None"}:
        return f"org:{org_code}"
    sap_id = clean(row.get("sap_id"))
    if sap_id and sap_id not in {"0", "null", "None"}:
        return f"sap:{sap_id}"
    shop_id = clean(row.get("shop_id"))
    if shop_id and shop_id not in {"0", "null", "None"}:
        return f"shop:{shop_id}"
    return raw_entity_key(row)


def record_score(row: dict[str, Any]) -> int:
    important = [
        "deptName", "deptAddr", "phone", "latGd", "lngGd", "org_name",
        "parentName", "shopLabels", "sales_scan_name", "org_code", "sap_id",
    ]
    return sum(2 if clean(row.get(field)) else 0 for field in important) + len(clean(row.get("deptAddr"))) // 20


def load_city_metadata() -> tuple[list[tuple[float, float, str]], dict[str, str], list[tuple[str, str]]]:
    payload = json.loads(CITY_LIST_PATH.read_text(encoding="utf-8"))
    city_data = payload.get("data", {}).get("cityData", {})
    provinces = city_data.get("provinces", {})
    centres: list[tuple[float, float, str]] = []
    city_to_province: dict[str, str] = {}
    province_aliases: list[tuple[str, str]] = []

    for province in provinces.values():
        province_name = clean(province.get("label") or province.get("name"))
        province_short = clean(province.get("name"))
        if province_name:
            province_aliases.append((province_name, province_name))
        if province_short and province_short != province_name:
            province_aliases.append((province_short, province_name))

        province_lat = safe_float(province.get("y"))
        province_lon = safe_float(province.get("x"))
        province_cities = province.get("cities") or []
        if not province_cities and province_lat is not None and province_lon is not None:
            centres.append((province_lat, province_lon, f"province:{province_name}"))
            for alias in {province_name, province_short}:
                if alias:
                    city_to_province[norm_city(alias)] = province_name

        for city in province_cities:
            city_name = clean(city.get("name"))
            city_label = clean(city.get("label"))
            lat = safe_float(city.get("y"))
            lon = safe_float(city.get("x"))
            if lat is not None and lon is not None:
                centres.append((lat, lon, f"city:{city_label or city_name}"))
            for alias in {city_name, city_label}:
                if alias:
                    city_to_province[norm_city(alias)] = province_name

    for city in city_data.get("hotCitys", []) or []:
        lat = safe_float(city.get("y"))
        lon = safe_float(city.get("x"))
        name = clean(city.get("label") or city.get("name"))
        if lat is not None and lon is not None and clean(city.get("adcode")) != "100000":
            centres.append((lat, lon, f"hotcity:{name}"))

    # Longest aliases first, avoiding a short province name matching too early.
    province_aliases.sort(key=lambda item: len(item[0]), reverse=True)
    return centres, city_to_province, province_aliases


def norm_city(value: Any) -> str:
    text = clean(value)
    text = re.sub(r"(特别行政区|自治州|自治县|地区|盟|市|县|区)$", "", text)
    return norm_text(text)


def infer_province(row: dict[str, Any], city_to_province: dict[str, str], aliases: list[tuple[str, str]]) -> str:
    city_key = norm_city(row.get("city"))
    if city_key and city_key in city_to_province:
        return city_to_province[city_key]
    combined = " ".join(clean(row.get(field)) for field in ("deptAddr", "deptName", "org_name", "parentName"))
    for alias, province_name in aliases:
        if alias and alias in combined:
            return province_name
    return ""


def rough_china_grid(step: float) -> Iterable[tuple[float, float, str]]:
    """A coarse rectangle with a few obvious ocean/foreign corners removed."""
    lat = 18.0
    while lat <= 54.0 + 1e-9:
        lon = 73.5
        while lon <= 135.5 + 1e-9:
            keep = True
            if lon < 80 and lat < 30:
                keep = False
            if lon < 88 and lat < 25:
                keep = False
            if lon > 126 and lat < 22:
                keep = False
            if lon > 132 and lat < 42:
                keep = False
            if keep:
                yield (round(lat, 6), round(lon, 6), "grid")
            lon += step
        lat += step


def classify(row: dict[str, Any]) -> tuple[str, bool]:
    display_text = " ".join(
        clean(row.get(field)) for field in ("deptName", "org_name", "deptAddr")
    )
    all_text = display_text + " " + clean(row.get("parentName"))
    explicit_non_pharmacy = bool(NON_PHARMACY_RE.search(display_text))
    has_pharmacy_term = bool(PHARMACY_RE.search(all_text))
    group_parent = "老百姓大药房" in clean(row.get("parentName"))
    main_brand_named = bool(MAIN_BRAND_RE.search(display_text))

    if explicit_non_pharmacy and not PHARMACY_RE.search(display_text):
        return "非药房业态", False
    if main_brand_named:
        return "老百姓主品牌命名", True
    if group_parent:
        return "老百姓集团药房网点", True
    if has_pharmacy_term:
        return "其他关联药房", True
    return "待核验网点", False


def hours(start: Any, end: Any) -> str:
    start_text, end_text = clean(start), clean(end)
    if start_text and end_text:
        return f"{start_text}-{end_text}"
    return start_text or end_text


def merge_canonical(records: list[dict[str, Any]], city_to_province: dict[str, str], aliases: list[tuple[str, str]], crawled_at: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[canonical_key(row)].append(row)

    merged: list[dict[str, Any]] = []
    for key, group in grouped.items():
        ordered = sorted(group, key=record_score, reverse=True)
        best = dict(ordered[0])
        for row in ordered[1:]:
            for field in API_FIELDS:
                if not clean(best.get(field)) and clean(row.get(field)):
                    best[field] = row.get(field)

        names = sorted({clean(row.get("deptName")) for row in group if clean(row.get("deptName"))})
        shop_ids = sorted({clean(row.get("shop_id")) for row in group if clean(row.get("shop_id"))})
        sap_ids = sorted({clean(row.get("sap_id")) for row in group if clean(row.get("sap_id"))})
        org_codes = sorted({clean(row.get("org_code")) for row in group if clean(row.get("org_code"))})
        classification, is_pharmacy = classify(best)

        best["province"] = infer_province(best, city_to_province, aliases)
        best["classification"] = classification
        best["is_pharmacy"] = "是" if is_pharmacy else "否"
        best["business_status"] = "闭店/停用" if clean(best.get("is_close")) in {"1", "true", "True"} else "营业/未标记关闭"
        best["summer_hours"] = hours(best.get("summer_start_hours"), best.get("summer_closing_hours"))
        best["winter_hours"] = hours(best.get("winter_start_hours"), best.get("winter_closing_hours"))
        best["delivery_hours"] = hours(best.get("shipStartTime"), best.get("shipEndTime"))
        best["api_entity_count"] = len(group)
        best["all_shop_ids"] = ",".join(shop_ids)
        best["all_sap_ids"] = ",".join(sap_ids)
        best["all_org_codes"] = ",".join(org_codes)
        best["alternate_names"] = " | ".join(name for name in names if name != clean(best.get("deptName")))
        best["source_url"] = ENDPOINT
        best["crawled_at_utc"] = crawled_at
        best["canonical_key"] = key
        merged.append(best)

    merged.sort(key=lambda row: (
        clean(row.get("province")), clean(row.get("city")), clean(row.get("deptName")), clean(row.get("org_code"))
    ))
    return merged


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field)) for field in fields})


def main() -> None:
    started = time.time()
    crawled_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    city_centres, city_to_province, province_aliases = load_city_metadata()

    queue: deque[tuple[float, float, str]] = deque()
    queued: set[tuple[float, float]] = set()
    queried: set[tuple[float, float]] = set()

    def enqueue(point: tuple[float, float, str]) -> None:
        lat, lon, seed_type = point
        key = point_key(lat, lon)
        if key not in queued and key not in queried:
            queued.add(key)
            queue.append((lat, lon, seed_type))

    for point in city_centres:
        enqueue(point)
    for point in rough_china_grid(GRID_STEP):
        enqueue(point)

    initial_seed_count = len(queue)
    raw_records: dict[str, dict[str, Any]] = {}
    errors: Counter[str] = Counter()
    seed_type_stats: Counter[str] = Counter()
    query_count = 0
    successful_queries = 0
    empty_queries = 0
    total_rows_seen = 0
    response_times: list[float] = []

    print(
        f"Starting LBX crawl: seeds={initial_seed_count}, workers={WORKERS}, "
        f"grid_step={GRID_STEP}, max_queries={MAX_QUERIES}",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        while queue and query_count < MAX_QUERIES:
            batch: list[tuple[float, float, str]] = []
            while queue and len(batch) < WORKERS * 3 and query_count + len(batch) < MAX_QUERIES:
                point = queue.popleft()
                key = point_key(point[0], point[1])
                queued.discard(key)
                if key in queried:
                    continue
                queried.add(key)
                batch.append(point)

            if not batch:
                continue

            futures = {executor.submit(fetch_point, point): point for point in batch}
            for future in as_completed(futures):
                point = futures[future]
                query_count += 1
                seed_type_stats[point[2].split(":", 1)[0]] += 1
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    result = {"ok": False, "error": repr(exc), "rows": []}

                if not result.get("ok"):
                    errors[clean(result.get("error"))[:180] or "unknown"] += 1
                    continue

                successful_queries += 1
                response_times.append(float(result.get("elapsed") or 0.0))
                rows = result.get("rows") or []
                total_rows_seen += len(rows)
                if not rows:
                    empty_queries += 1

                for raw in rows:
                    row = {field: raw.get(field, "") for field in set(API_FIELDS) | set(raw.keys())}
                    entity_key = raw_entity_key(row)
                    is_new = entity_key not in raw_records
                    if is_new or record_score(row) > record_score(raw_records[entity_key]):
                        row["_first_seen_seed_type"] = point[2]
                        row["_first_seen_lat"] = point[0]
                        row["_first_seen_lon"] = point[1]
                        raw_records[entity_key] = row
                    if is_new:
                        coords = store_coords(row)
                        if coords:
                            enqueue((coords[0], coords[1], "store"))

            if query_count % 500 < len(batch):
                print(
                    f"progress queries={query_count} success={successful_queries} "
                    f"unique_entities={len(raw_records)} queued={len(queue)} errors={sum(errors.values())}",
                    flush=True,
                )

    raw_list = list(raw_records.values())
    canonical = merge_canonical(raw_list, city_to_province, province_aliases, crawled_at)
    pharmacies = [row for row in canonical if row.get("is_pharmacy") == "是"]
    exclusions = [row for row in canonical if row.get("is_pharmacy") != "是"]

    # Append crawl metadata to raw records for traceability.
    raw_export_fields = API_FIELDS + [
        "_first_seen_seed_type", "_first_seen_lat", "_first_seen_lon", "source_url", "crawled_at_utc"
    ]
    for row in raw_list:
        row["source_url"] = ENDPOINT
        row["crawled_at_utc"] = crawled_at

    write_csv(OUT / "lbx_pharmacy_stores.csv", pharmacies, EXPORT_FIELDS)
    write_csv(OUT / "lbx_all_canonical_locations.csv", canonical, EXPORT_FIELDS)
    write_csv(OUT / "lbx_excluded_non_pharmacy.csv", exclusions, EXPORT_FIELDS)
    write_csv(OUT / "lbx_raw_api_entities.csv", raw_list, raw_export_fields)

    with gzip.open(OUT / "lbx_raw_api_entities.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in raw_list:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    province_counts = Counter(clean(row.get("province")) or "未识别省份" for row in pharmacies)
    city_counts = Counter(clean(row.get("city")) or "未识别城市" for row in pharmacies)
    category_counts = Counter(clean(row.get("classification")) or "未分类" for row in canonical)
    parent_counts = Counter(clean(row.get("parentName")) or "未填写" for row in pharmacies)
    elapsed = time.time() - started

    summary = {
        "crawl_started_utc": crawled_at,
        "elapsed_seconds": round(elapsed, 2),
        "endpoint": ENDPOINT,
        "official_about_page": OFFICIAL_ABOUT,
        "official_store_benchmark": OFFICIAL_STORE_BENCHMARK,
        "method": "prefecture city centres + 1-degree nationwide grid + recursive store-coordinate expansion",
        "parameters": {
            "workers": WORKERS,
            "grid_step_degrees": GRID_STEP,
            "max_queries": MAX_QUERIES,
            "timeout_seconds": TIMEOUT_SECONDS,
            "retries": MAX_RETRIES,
        },
        "initial_seed_count": initial_seed_count,
        "query_count": query_count,
        "successful_queries": successful_queries,
        "failed_queries": query_count - successful_queries,
        "empty_queries": empty_queries,
        "total_rows_seen_including_duplicates": total_rows_seen,
        "unique_api_entities": len(raw_list),
        "canonical_locations": len(canonical),
        "pharmacy_locations": len(pharmacies),
        "excluded_or_unverified_locations": len(exclusions),
        "province_count": len([name for name in province_counts if name != "未识别省份"]),
        "city_count": len([name for name in city_counts if name != "未识别城市"]),
        "coverage_ratio_vs_official_benchmark": round(len(pharmacies) / OFFICIAL_STORE_BENCHMARK, 4),
        "queue_remaining_when_stopped": len(queue),
        "max_query_limit_hit": query_count >= MAX_QUERIES and bool(queue),
        "average_response_seconds": round(sum(response_times) / len(response_times), 4) if response_times else None,
        "p95_response_seconds": round(sorted(response_times)[int(len(response_times) * 0.95) - 1], 4) if response_times else None,
        "seed_query_counts": dict(seed_type_stats),
        "classification_counts": dict(category_counts),
        "province_counts": dict(province_counts.most_common()),
        "top_city_counts": dict(city_counts.most_common(100)),
        "top_parent_counts": dict(parent_counts.most_common(100)),
        "top_errors": dict(errors.most_common(20)),
        "limitations": [
            "The endpoint is a public nearby-store endpoint, not an official bulk export API.",
            "It returns at most ten nearby records and ignores common pagination/radius parameters.",
            "The crawl uses graph expansion and a nationwide grid; isolated or inactive stores not exposed by the endpoint can still be missed.",
            "The endpoint can contain clinics or other group formats, which are separated by rule-based classification.",
            "The official 15,001-store figure includes franchises and may use a broader reporting scope than this endpoint.",
        ],
    }
    (OUT / "crawl_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
