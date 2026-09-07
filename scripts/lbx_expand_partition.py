#!/usr/bin/env python3
"""Continue a public LBX nearby-store crawl in deterministic parallel partitions.

Each partition starts from the first-pass artifact, prioritizes offset probes around
all counties in known LBX markets, then revisits a share of discovered store
coordinates and recursively follows newly found store coordinates.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
ADMIN_URL = "https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/xzqh_with_amap_coordinates.json"
TARGET_PROVINCES = {
    "湖南省", "江苏省", "安徽省", "甘肃省", "陕西省", "广西壮族自治区",
    "内蒙古自治区", "天津市", "湖北省", "浙江省", "山西省", "河南省",
    "山东省", "上海市", "宁夏回族自治区", "贵州省", "广东省", "江西省", "北京市",
}
PHARMACY_POSITIVE = ("药房", "药店", "医药", "药业", "药品", "药行", "老百姓", "百姓平安", "百杏堂")
PHARMACY_NEGATIVE = ("诊所", "医院", "门诊部", "体检", "健康管理", "医疗器械公司", "电子商务公司", "物流", "仓库", "配送中心")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
    "X-Requested-With": "XMLHttpRequest",
}
_thread = threading.local()


class RateLimiter:
    def __init__(self, rate: float) -> None:
        self.interval = 1.0 / max(rate, 0.1)
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if delay:
            time.sleep(delay)


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float
    source: str
    province_hint: str = ""
    admin_name: str = ""

    @property
    def key(self) -> str:
        return f"{self.lat:.6f},{self.lng:.6f}"


def session() -> requests.Session:
    value = getattr(_thread, "session", None)
    if value is None:
        value = requests.Session()
        value.headers.update(HEADERS)
        _thread.session = value
    return value


def valid_coord(lat: Any, lng: Any) -> tuple[float, float] | None:
    try:
        a, b = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if 15 <= a <= 55.5 and 72 <= b <= 136:
        return a, b
    return None


def row_coord(row: dict[str, Any]) -> tuple[float, float] | None:
    for a, b in (("latGd", "lngGd"), ("lat", "lng"), ("latitude", "longitude"), ("latBd", "lngBd")):
        value = valid_coord(row.get(a), row.get(b))
        if value:
            return value
    return None


def compact(value: Any) -> str:
    return re.sub(r"[\s\u3000\-—_（）()【】\[\]·,，.。]", "", str(value or "")).lower()


def store_key(row: dict[str, Any]) -> str:
    for field in ("shop_id", "sap_id", "org_code", "_store_key"):
        value = str(row.get(field) or "").strip()
        if value and value not in {"0", "None", "null"}:
            return f"{field}:{value}"
    coord = row_coord(row)
    name = compact(row.get("deptName") or row.get("org_name"))
    address = compact(row.get("deptAddr"))
    if coord:
        return f"fallback:{name}:{coord[0]:.6f}:{coord[1]:.6f}:{address}"
    return f"fallback:{name}:{address}:{compact(row.get('phone'))}"


def is_pharmacy(row: dict[str, Any]) -> bool:
    text = "|".join(str(row.get(k) or "") for k in ("deptName", "org_name", "parentName", "third_org_name", "deptAddr"))
    if any(word in text for word in PHARMACY_NEGATIVE):
        own = str(row.get("deptName") or "") + str(row.get("org_name") or "")
        if not any(word in own for word in ("药房", "药店", "医药", "药业")):
            return False
    if any(word in text for word in PHARMACY_POSITIVE):
        return True
    parent = str(row.get("parentName") or "")
    own = str(row.get("deptName") or "")
    return bool("老百姓大药房" in parent and own and not any(x in own for x in PHARMACY_NEGATIVE))


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    cur = payload
    for _ in range(6):
        if isinstance(cur, list):
            return [x for x in cur if isinstance(x, dict)]
        if not isinstance(cur, dict):
            return []
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


def load_base(base_dir: Path) -> dict[str, dict[str, Any]]:
    path = next(iter(base_dir.rglob("stores_raw.jsonl.gz")))
    stores: dict[str, dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                stores[store_key(row)] = row
    return stores


def fetch_admin() -> list[dict[str, Any]]:
    response = requests.get(ADMIN_URL, headers=HEADERS, timeout=45)
    response.raise_for_status()
    tree = response.json()
    nodes: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], province: str) -> None:
        level = str(node.get("level") or "")
        name = str(node.get("name") or "")
        if level == "province":
            province = name
        center = node.get("center") or {}
        coord = valid_coord(center.get("latitude"), center.get("longitude"))
        if coord and level == "county" and province in TARGET_PROVINCES:
            nodes.append({"province": province, "name": name, "lat": coord[0], "lng": coord[1]})
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, province)

    for root in tree:
        if isinstance(root, dict):
            walk(root, "")
    return nodes


def bucket(key: str, parts: int) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % parts


def initial_points(stores: dict[str, dict[str, Any]], counties: list[dict[str, Any]], part: int, parts: int) -> list[Point]:
    result: dict[str, Point] = {}
    # Roughly 12-20 km offsets around each county center; center points were already used in pass one.
    offsets = ((0.15, 0.0), (-0.15, 0.0), (0.0, 0.18), (0.0, -0.18),
               (0.15, 0.18), (0.15, -0.18), (-0.15, 0.18), (-0.15, -0.18))
    # Offsets are intentionally first because they are more likely than repeated store points to reveal new components.
    for node in counties:
        for dlat, dlng in offsets:
            point = Point(node["lat"] + dlat, node["lng"] + dlng, "county_offset_parallel", node["province"], node["name"])
            if bucket(point.key, parts) == part:
                result[point.key] = point
    for row in stores.values():
        coord = row_coord(row)
        if not coord:
            continue
        point = Point(coord[0], coord[1], "base_store_revisit", str(row.get("_first_seen_province_hint") or ""), str(row.get("deptName") or ""))
        if bucket(point.key, parts) == part:
            result.setdefault(point.key, point)
    return list(result.values())


def write_jsonl_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    preferred = ["shop_id", "sap_id", "org_code", "deptName", "org_name", "parentName", "third_org_name", "city", "deptAddr", "phone", "latGd", "lngGd", "latBd", "lngBd", "shopLabels", "is_m_shop", "is_close", "sales_scan_name", "summer_start_hours", "summer_closing_hours", "winter_start_hours", "winter_closing_hours", "shipStartTime", "shipEndTime", "_first_seen_source", "_first_seen_province_hint", "_first_seen_admin_name", "_first_seen_query_lat", "_first_seen_query_lng"]
    ordered = [x for x in preferred if x in fields] + [x for x in fields if x not in preferred]
    with gzip.open(path, "wt", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default="base_output")
    parser.add_argument("--output", required=True)
    parser.add_argument("--part", type=int, required=True)
    parser.add_argument("--parts", type=int, default=4)
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument("--rps", type=float, default=11.0)
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()

    started = time.monotonic()
    limiter = RateLimiter(args.rps)
    stores = load_base(Path(args.base_dir))
    base_count = len(stores)
    counties = fetch_admin()
    points = initial_points(stores, counties, args.part, args.parts)
    queue: deque[Point] = deque(points)
    scheduled = {p.key for p in points}
    queried: set[str] = set()
    failures: list[dict[str, Any]] = []
    requests_done = 0
    success = 0
    new_records = 0
    source_counts = Counter()

    def query(point: Point) -> tuple[Point, list[dict[str, Any]], str]:
        params = {"Latitude": f"{point.lat:.8f}", "Longitude": f"{point.lng:.8f}"}
        error = ""
        for attempt in range(3):
            try:
                limiter.wait()
                response = session().get(ENDPOINT, params=params, timeout=(7, 18))
                response.raise_for_status()
                payload = response.json()
                rows = extract_rows(payload)
                top_code = payload.get("code") if isinstance(payload, dict) else None
                nested_code = payload.get("data", {}).get("code") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else None
                if rows or top_code == 1 or nested_code in (0, 1):
                    return point, rows, ""
                error = f"api_code={top_code}/{nested_code}"
            except Exception as exc:  # noqa: BLE001
                error = repr(exc)
            time.sleep(0.5 * (2 ** attempt))
        return point, [], error

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        while queue and time.monotonic() - started < args.max_seconds:
            batch: list[Point] = []
            while queue and len(batch) < 120:
                point = queue.popleft()
                if point.key in queried:
                    continue
                queried.add(point.key)
                batch.append(point)
            if not batch:
                continue
            futures = [executor.submit(query, point) for point in batch]
            for future in as_completed(futures):
                point, rows, error = future.result()
                requests_done += 1
                source_counts[point.source] += 1
                if error:
                    failures.append({"lat": point.lat, "lng": point.lng, "source": point.source, "error": error})
                    continue
                success += 1
                for raw in rows:
                    key = store_key(raw)
                    if key in stores:
                        continue
                    row = dict(raw)
                    row["_store_key"] = key
                    row["_first_seen_source"] = point.source
                    row["_first_seen_province_hint"] = point.province_hint
                    row["_first_seen_admin_name"] = point.admin_name
                    row["_first_seen_query_lat"] = point.lat
                    row["_first_seen_query_lng"] = point.lng
                    stores[key] = row
                    new_records += 1
                    coord = row_coord(row)
                    if coord:
                        next_point = Point(coord[0], coord[1], "new_store_graph", point.province_hint, str(row.get("deptName") or ""))
                        if next_point.key not in scheduled:
                            scheduled.add(next_point.key)
                            queue.append(next_point)
            if requests_done % 600 == 0:
                print(json.dumps({"part": args.part, "requests": requests_done, "stores": len(stores), "new": new_records, "queue": len(queue), "elapsed": round(time.monotonic()-started,1)}, ensure_ascii=False), flush=True)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    all_rows = sorted(stores.values(), key=lambda r: (str(r.get("city") or ""), str(r.get("parentName") or ""), str(r.get("deptName") or r.get("org_name") or ""), str(r.get("shop_id") or "")))
    pharmacy = [row for row in all_rows if is_pharmacy(row)]
    non_pharmacy = [row for row in all_rows if not is_pharmacy(row)]
    write_jsonl_gz(output / "stores_raw.jsonl.gz", all_rows)
    write_jsonl_gz(output / "stores_non_pharmacy.jsonl.gz", non_pharmacy)
    write_csv_gz(output / "stores_pharmacy.csv.gz", pharmacy)
    with (output / "failures.jsonl").open("w", encoding="utf-8") as handle:
        for row in failures:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    stats = {
        "part": args.part, "parts": args.parts, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic()-started,1), "base_records": base_count,
        "initial_points": len(points), "scheduled_points": len(scheduled), "queried_points": len(queried),
        "requests_done": requests_done, "successful_queries": success, "failed_queries": len(failures),
        "new_records": new_records, "all_records": len(all_rows), "pharmacy_records": len(pharmacy),
        "non_pharmacy_records": len(non_pharmacy), "remaining_queue": len(queue),
        "source_counts": dict(source_counts), "endpoint": ENDPOINT,
    }
    (output / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
