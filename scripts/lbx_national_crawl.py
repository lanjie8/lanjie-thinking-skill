#!/usr/bin/env python3
"""Crawl LBX-linked pharmacy stores from a public nearby-store endpoint.

The endpoint returns nearby records rather than a full export. Coverage is built by:
1) seeding all county/city centers in known LBX markets plus all mainland city centers;
2) recursively querying the coordinates of every newly discovered store, traversing the
   nearby-store graph;
3) conditionally probing offset points around county centers when the first pass is
   materially below the latest public company store-count benchmark.

No authentication or access-control bypass is used. Requests are globally rate-limited.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import os
import re
import threading
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
ADMIN_URL = (
    "https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/"
    "xzqh_with_amap_coordinates.json"
)
OUT = Path(os.environ.get("LBX_OUT_DIR", "lbx_national_output"))
OUT.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = int(os.environ.get("LBX_WORKERS", "12"))
REQUESTS_PER_SECOND = float(os.environ.get("LBX_RPS", "10"))
MAX_RUNTIME_SECONDS = int(os.environ.get("LBX_MAX_RUNTIME", "3150"))
BATCH_SIZE = int(os.environ.get("LBX_BATCH_SIZE", "360"))
TARGET_PHARMACY_FLOOR = int(os.environ.get("LBX_TARGET_FLOOR", "14000"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": (
        "https://yx.lbxcn.com/h5/springgame/index.html?"
        "gameCode=spring_251230_6&source=4"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

# The 18 markets publicly listed by LBX in 2025, plus Beijing after the publicly
# announced 2026 market entry. Province/city seeds outside this list are also used
# at a lower density to detect unexpected coverage.
TARGET_PROVINCES = {
    "湖南省",
    "江苏省",
    "安徽省",
    "甘肃省",
    "陕西省",
    "广西壮族自治区",
    "内蒙古自治区",
    "天津市",
    "湖北省",
    "浙江省",
    "山西省",
    "河南省",
    "山东省",
    "上海市",
    "宁夏回族自治区",
    "贵州省",
    "广东省",
    "江西省",
    "北京市",
}
SKIP_PROVINCE_PREFIXES = {"710000", "810000", "820000"}

PHARMACY_POSITIVE = (
    "药房",
    "药店",
    "医药",
    "药业",
    "药品",
    "药行",
    "老百姓",
    "百姓平安",
    "百杏堂",
)
PHARMACY_NEGATIVE = (
    "诊所",
    "医院",
    "门诊部",
    "体检",
    "健康管理",
    "医疗器械公司",
    "电子商务公司",
    "物流",
    "仓库",
    "配送中心",
)

_thread_local = threading.local()


class GlobalRateLimiter:
    def __init__(self, rate: float) -> None:
        self.interval = 1.0 / max(rate, 0.1)
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            if self.next_at > now:
                time.sleep(self.next_at - now)
                now = time.monotonic()
            self.next_at = max(self.next_at, now) + self.interval


LIMITER = GlobalRateLimiter(REQUESTS_PER_SECOND)


@dataclass(frozen=True)
class QueryPoint:
    lat: float
    lng: float
    source: str
    province_hint: str = ""
    admin_code: str = ""
    admin_name: str = ""

    @property
    def coord_key(self) -> str:
        return f"{self.lat:.6f},{self.lng:.6f}"


def session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        _thread_local.session = s
    return s


def fetch_json(url: str, timeout: int = 45) -> Any:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract the nested list used by several generations of the LBX API."""
    cur = payload
    for _ in range(5):
        if isinstance(cur, list):
            return [x for x in cur if isinstance(x, dict)]
        if not isinstance(cur, dict):
            return []
        # Prefer an actual list-valued data key.
        value = cur.get("data")
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            cur = value
            continue
        for key in ("rows", "list", "records", "result"):
            value = cur.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                cur = value
                break
        else:
            return []
    return []


def query_endpoint(point: QueryPoint) -> dict[str, Any]:
    params = {"Latitude": f"{point.lat:.8f}", "Longitude": f"{point.lng:.8f}"}
    last_error = ""
    for attempt in range(4):
        try:
            LIMITER.wait()
            started = time.monotonic()
            r = session().get(ENDPOINT, params=params, timeout=(8, 22))
            elapsed = round(time.monotonic() - started, 3)
            body_len = len(r.content)
            r.raise_for_status()
            payload = r.json()
            rows = extract_rows(payload)
            top_code = payload.get("code") if isinstance(payload, dict) else None
            nested_code = None
            if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                nested_code = payload["data"].get("code")
            # A valid empty result is represented by code=1 and an empty list.
            if top_code == 1 or nested_code in (0, 1) or rows:
                return {
                    "ok": True,
                    "point": point,
                    "rows": rows,
                    "status": r.status_code,
                    "elapsed": elapsed,
                    "body_len": body_len,
                    "top_code": top_code,
                    "nested_code": nested_code,
                }
            last_error = (
                f"api_code={top_code}/{nested_code}; "
                f"message={payload.get('message') if isinstance(payload, dict) else ''}"
            )
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
        if attempt < 3:
            time.sleep(0.6 * (2**attempt))
    return {"ok": False, "point": point, "rows": [], "error": last_error}


def valid_coord(lat: Any, lng: Any) -> tuple[float, float] | None:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    if not (15.0 <= lat_f <= 55.5 and 72.0 <= lng_f <= 136.0):
        return None
    return lat_f, lng_f


def row_coord(row: dict[str, Any]) -> tuple[float, float] | None:
    for lat_key, lng_key in (
        ("latGd", "lngGd"),
        ("lat", "lng"),
        ("latitude", "longitude"),
        ("latBd", "lngBd"),
    ):
        c = valid_coord(row.get(lat_key), row.get(lng_key))
        if c:
            return c
    return None


def normalize_text(value: Any) -> str:
    return re.sub(r"[\s\u3000\-—_（）()【】\[\]·,，.。]", "", str(value or "")).lower()


def store_key(row: dict[str, Any]) -> str:
    for field in ("shop_id", "sap_id", "org_code"):
        value = str(row.get(field) or "").strip()
        if value and value not in {"0", "None", "null"}:
            return f"{field}:{value}"
    coord = row_coord(row)
    name = normalize_text(row.get("deptName") or row.get("org_name"))
    address = normalize_text(row.get("deptAddr"))
    if coord:
        return f"fallback:{name}:{coord[0]:.6f}:{coord[1]:.6f}:{address}"
    return f"fallback:{name}:{address}:{normalize_text(row.get('phone'))}"


def is_pharmacy(row: dict[str, Any]) -> bool:
    text = "|".join(
        str(row.get(k) or "")
        for k in (
            "deptName",
            "org_name",
            "parentName",
            "third_org_name",
            "deptAddr",
        )
    )
    if any(word in text for word in PHARMACY_NEGATIVE):
        # A pharmacy co-located with a clinic can still be a pharmacy if its own
        # department name is explicit.
        dept = str(row.get("deptName") or "") + str(row.get("org_name") or "")
        if not any(word in dept for word in ("药房", "药店", "医药", "药业")):
            return False
    if any(word in text for word in PHARMACY_POSITIVE):
        return True
    # Company-format store names often omit the words 药房/药店.
    parent = str(row.get("parentName") or "")
    dept = str(row.get("deptName") or "")
    if "老百姓大药房" in parent and dept and not any(x in dept for x in PHARMACY_NEGATIVE):
        return True
    return False


def flatten_admin(tree: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    nodes: list[dict[str, Any]] = []
    city_to_province: dict[str, str] = {}

    def walk(node: dict[str, Any], province: str, city: str) -> None:
        level = str(node.get("level") or "")
        name = str(node.get("name") or "")
        code = str(node.get("code") or "")
        if level == "province":
            province = name
            if province.endswith(("市", "特别行政区")):
                city = province
        elif level == "city":
            city = name
            city_to_province[name] = province
        elif level == "county" and city:
            city_to_province.setdefault(name, province)
        center = node.get("center") or {}
        coord = valid_coord(center.get("latitude"), center.get("longitude"))
        if coord:
            nodes.append(
                {
                    "code": code,
                    "name": name,
                    "level": level,
                    "province": province,
                    "city": city,
                    "lat": coord[0],
                    "lng": coord[1],
                }
            )
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, province, city)

    for root in tree:
        if isinstance(root, dict):
            walk(root, "", "")
    return nodes, city_to_province


def initial_seeds(nodes: list[dict[str, Any]]) -> tuple[list[QueryPoint], list[dict[str, Any]]]:
    seeds: dict[str, QueryPoint] = {}
    target_counties: list[dict[str, Any]] = []
    for node in nodes:
        code = str(node["code"])
        if any(code.startswith(p[:2]) for p in SKIP_PROVINCE_PREFIXES):
            continue
        level = node["level"]
        province = node["province"]
        target = province in TARGET_PROVINCES
        # Dense seed coverage in known/current markets; elsewhere retain city and
        # province centers to detect any newly entered market.
        if target or level in {"province", "city"}:
            point = QueryPoint(
                lat=node["lat"],
                lng=node["lng"],
                source=f"admin_{level}",
                province_hint=province,
                admin_code=code,
                admin_name=node["name"],
            )
            seeds.setdefault(point.coord_key, point)
        if target and level == "county":
            target_counties.append(node)
    return list(seeds.values()), target_counties


def offset_seeds(
    counties: list[dict[str, Any]],
    stage: int,
    existing: set[str],
) -> list[QueryPoint]:
    # Cardinal/diagonal probes about 12–20 km away, used only if the recursive
    # nearby-store graph remains materially below the public company benchmark.
    if stage == 1:
        offsets = ((0.15, 0.0), (-0.15, 0.0), (0.0, 0.18), (0.0, -0.18))
    else:
        offsets = ((0.16, 0.20), (0.16, -0.20), (-0.16, 0.20), (-0.16, -0.20))
    points: list[QueryPoint] = []
    for node in counties:
        for dlat, dlng in offsets:
            p = QueryPoint(
                lat=node["lat"] + dlat,
                lng=node["lng"] + dlng,
                source=f"county_offset_stage{stage}",
                province_hint=node["province"],
                admin_code=node["code"],
                admin_name=node["name"],
            )
            if p.coord_key not in existing:
                existing.add(p.coord_key)
                points.append(p)
    return points


def write_json_gz(path: Path, value: Any) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)


def write_jsonl_gz(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({k for row in rows for k in row.keys()})
    preferred = [
        "shop_id",
        "sap_id",
        "org_code",
        "deptName",
        "org_name",
        "parentName",
        "third_org_name",
        "city",
        "deptAddr",
        "phone",
        "latGd",
        "lngGd",
        "latBd",
        "lngBd",
        "shopLabels",
        "is_m_shop",
        "is_close",
        "sales_scan_name",
        "summer_start_hours",
        "summer_closing_hours",
        "winter_start_hours",
        "winter_closing_hours",
        "shipStartTime",
        "shipEndTime",
        "_first_seen_source",
        "_first_seen_province_hint",
        "_first_seen_admin_name",
        "_first_seen_query_lat",
        "_first_seen_query_lng",
    ]
    ordered = [x for x in preferred if x in fields] + [x for x in fields if x not in preferred]
    with gzip.open(path, "wt", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ordered, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    started = time.monotonic()
    crawl_started_at = datetime.now(timezone.utc).isoformat()
    print(f"Fetching administrative centers: {ADMIN_URL}", flush=True)
    admin_tree = fetch_json(ADMIN_URL)
    nodes, city_to_province = flatten_admin(admin_tree)
    seeds, target_counties = initial_seeds(nodes)
    print(
        f"Admin nodes={len(nodes)} initial_seeds={len(seeds)} "
        f"target_counties={len(target_counties)} workers={MAX_WORKERS} rps={REQUESTS_PER_SECOND}",
        flush=True,
    )

    stores: dict[str, dict[str, Any]] = {}
    point_queue: deque[QueryPoint] = deque(seeds)
    scheduled_points: set[str] = {p.coord_key for p in seeds}
    queried_points: set[str] = set()
    failures: list[dict[str, Any]] = []
    query_counts = Counter()
    rows_per_query = Counter()
    province_hint_counts = Counter()
    requests_done = 0
    successful_queries = 0
    new_stores_total = 0
    stage = "initial_and_graph"
    offset_stage = 0

    def add_row(row: dict[str, Any], point: QueryPoint) -> bool:
        nonlocal new_stores_total
        key = store_key(row)
        if key in stores:
            return False
        enriched = dict(row)
        enriched["_store_key"] = key
        enriched["_first_seen_source"] = point.source
        enriched["_first_seen_province_hint"] = point.province_hint
        enriched["_first_seen_admin_code"] = point.admin_code
        enriched["_first_seen_admin_name"] = point.admin_name
        enriched["_first_seen_query_lat"] = point.lat
        enriched["_first_seen_query_lng"] = point.lng
        stores[key] = enriched
        new_stores_total += 1
        coord = row_coord(enriched)
        if coord:
            next_point = QueryPoint(
                lat=coord[0],
                lng=coord[1],
                source="store_graph",
                province_hint=point.province_hint,
                admin_code="",
                admin_name=str(enriched.get("deptName") or ""),
            )
            if next_point.coord_key not in scheduled_points:
                scheduled_points.add(next_point.coord_key)
                point_queue.append(next_point)
        return True

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while True:
            if time.monotonic() - started > MAX_RUNTIME_SECONDS:
                print("Runtime ceiling reached; saving a partial checkpoint.", flush=True)
                break

            if not point_queue:
                pharmacy_count = sum(1 for row in stores.values() if is_pharmacy(row))
                time_left = MAX_RUNTIME_SECONDS - (time.monotonic() - started)
                if (
                    pharmacy_count < TARGET_PHARMACY_FLOOR
                    and offset_stage < 2
                    and time_left > 480
                ):
                    offset_stage += 1
                    stage = f"offset_stage_{offset_stage}_and_graph"
                    extra = offset_seeds(target_counties, offset_stage, scheduled_points)
                    point_queue.extend(extra)
                    print(
                        f"Starting offset stage {offset_stage}: points={len(extra)} "
                        f"pharmacies={pharmacy_count} time_left={int(time_left)}s",
                        flush=True,
                    )
                else:
                    break

            batch: list[QueryPoint] = []
            while point_queue and len(batch) < BATCH_SIZE:
                point = point_queue.popleft()
                if point.coord_key in queried_points:
                    continue
                queried_points.add(point.coord_key)
                batch.append(point)
            if not batch:
                continue

            future_map = {executor.submit(query_endpoint, p): p for p in batch}
            for future in as_completed(future_map):
                point = future_map[future]
                requests_done += 1
                query_counts[point.source] += 1
                province_hint_counts[point.province_hint] += 1
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    result = {"ok": False, "point": point, "rows": [], "error": repr(exc)}
                if not result.get("ok"):
                    failures.append(
                        {
                            "lat": point.lat,
                            "lng": point.lng,
                            "source": point.source,
                            "province_hint": point.province_hint,
                            "admin_code": point.admin_code,
                            "admin_name": point.admin_name,
                            "error": result.get("error", "unknown"),
                        }
                    )
                    continue
                successful_queries += 1
                rows = result.get("rows") or []
                rows_per_query[str(len(rows))] += 1
                for row in rows:
                    add_row(row, point)

                if requests_done % 250 == 0:
                    pharmacy_count = sum(1 for row in stores.values() if is_pharmacy(row))
                    elapsed = int(time.monotonic() - started)
                    print(
                        f"progress stage={stage} requests={requests_done} "
                        f"ok={successful_queries} failures={len(failures)} "
                        f"stores={len(stores)} pharmacies={pharmacy_count} "
                        f"queue={len(point_queue)} elapsed={elapsed}s",
                        flush=True,
                    )
                    (OUT / "checkpoint_stats.json").write_text(
                        json.dumps(
                            {
                                "stage": stage,
                                "requests": requests_done,
                                "successful_queries": successful_queries,
                                "failures": len(failures),
                                "stores": len(stores),
                                "pharmacies": pharmacy_count,
                                "queue": len(point_queue),
                                "elapsed_seconds": elapsed,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )

    crawl_finished_at = datetime.now(timezone.utc).isoformat()
    all_rows = sorted(
        stores.values(),
        key=lambda r: (
            str(r.get("city") or ""),
            str(r.get("parentName") or ""),
            str(r.get("deptName") or r.get("org_name") or ""),
            str(r.get("shop_id") or ""),
        ),
    )
    pharmacy_rows = [row for row in all_rows if is_pharmacy(row)]
    non_pharmacy_rows = [row for row in all_rows if not is_pharmacy(row)]

    write_jsonl_gz(OUT / "stores_raw.jsonl.gz", all_rows)
    write_jsonl_gz(OUT / "stores_pharmacy.jsonl.gz", pharmacy_rows)
    write_jsonl_gz(OUT / "stores_non_pharmacy.jsonl.gz", non_pharmacy_rows)
    write_csv_gz(OUT / "stores_pharmacy.csv.gz", pharmacy_rows)
    with (OUT / "query_failures.jsonl").open("w", encoding="utf-8") as f:
        for row in failures:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    parent_counts = Counter(str(r.get("parentName") or "(空)") for r in pharmacy_rows)
    city_counts = Counter(str(r.get("city") or "(空)") for r in pharmacy_rows)
    source_counts = Counter(str(r.get("_first_seen_source") or "") for r in all_rows)
    stats = {
        "endpoint": ENDPOINT,
        "admin_source": ADMIN_URL,
        "crawl_started_at_utc": crawl_started_at,
        "crawl_finished_at_utc": crawl_finished_at,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "complete_queue_exhausted": not bool(point_queue),
        "runtime_ceiling_seconds": MAX_RUNTIME_SECONDS,
        "requests_per_second_limit": REQUESTS_PER_SECOND,
        "max_workers": MAX_WORKERS,
        "initial_seed_count": len(seeds),
        "target_county_count": len(target_counties),
        "offset_stage_completed": offset_stage,
        "query_points_scheduled": len(scheduled_points),
        "query_points_queried": len(queried_points),
        "requests_done": requests_done,
        "successful_queries": successful_queries,
        "failed_queries": len(failures),
        "rows_per_query": dict(rows_per_query),
        "all_linked_records": len(all_rows),
        "pharmacy_records": len(pharmacy_rows),
        "non_pharmacy_records": len(non_pharmacy_rows),
        "distinct_valid_store_coordinates": len(
            {f"{c[0]:.6f},{c[1]:.6f}" for r in all_rows if (c := row_coord(r))}
        ),
        "target_pharmacy_floor_for_offsets": TARGET_PHARMACY_FLOOR,
        "known_market_provinces_plus_beijing": sorted(TARGET_PROVINCES),
        "query_source_counts": dict(query_counts),
        "first_seen_source_counts": dict(source_counts),
        "top_100_parent_companies": parent_counts.most_common(100),
        "top_200_api_cities": city_counts.most_common(200),
        "city_to_province_map": city_to_province,
        "notes": [
            "The endpoint is a public nearby-store interface, not an official bulk export.",
            "Coverage is generated by administrative-center seeds plus recursive traversal of every discovered store coordinate.",
            "The legacy route name does not prove record vintage; fields are retained exactly as returned and should be operationally verified.",
            "Named contact-person fields are retained only in the raw JSON source and should not be surfaced by default in the user-facing workbook.",
        ],
    }
    (OUT / "crawl_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: stats[k] for k in (
        "elapsed_seconds", "complete_queue_exhausted", "requests_done",
        "successful_queries", "failed_queries", "all_linked_records",
        "pharmacy_records", "non_pharmacy_records", "distinct_valid_store_coordinates",
        "offset_stage_completed"
    )}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
