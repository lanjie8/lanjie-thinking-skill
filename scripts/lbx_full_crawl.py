#!/usr/bin/env python3
"""Crawl the public LBX nearby-store endpoint across its 18 operating markets.

The endpoint returns at most 10 nearby active locations. The crawler combines:
1) two shifted geographic grids over the 18 published provincial markets;
2) adaptive subdivision wherever a query is saturated at 10 results; and
3) breadth-first traversal of every discovered store's own coordinates.

Only store/business fields are retained; personal contact-person names are omitted.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
OUT = Path("lbx_full_crawl_output")
OUT.mkdir(exist_ok=True)

# Published operating markets. Rectangles intentionally extend slightly beyond
# borders so boundary stores are not missed.
MARKETS = {
    "湖南": (24.4, 30.3, 108.6, 114.5),
    "江苏": (30.5, 35.3, 116.0, 122.1),
    "安徽": (29.2, 34.8, 114.7, 119.9),
    "甘肃": (32.4, 42.9, 92.0, 109.0),
    "陕西": (31.5, 39.7, 105.3, 111.5),
    "广西": (20.6, 26.6, 104.2, 112.3),
    "内蒙古": (37.2, 53.5, 97.0, 126.4),
    "天津": (38.4, 40.4, 116.5, 118.3),
    "湖北": (28.8, 33.4, 108.1, 116.4),
    "浙江": (26.8, 31.5, 117.8, 123.2),
    "山西": (34.3, 40.9, 110.0, 114.8),
    "河南": (31.2, 36.6, 110.1, 116.9),
    "山东": (34.1, 38.6, 114.6, 123.0),
    "上海": (30.5, 32.0, 120.7, 122.1),
    "宁夏": (35.0, 39.6, 104.1, 107.9),
    "贵州": (24.3, 29.5, 103.3, 109.8),
    "广东": (19.9, 25.8, 109.3, 117.6),
    "江西": (24.2, 30.3, 113.3, 118.8),
}

BASE_STEP = float(os.getenv("LBX_GRID_STEP", "0.60"))
MIN_ADAPTIVE_STEP = float(os.getenv("LBX_MIN_STEP", "0.075"))
WORKERS = int(os.getenv("LBX_WORKERS", "12"))
MAX_REQUESTS = int(os.getenv("LBX_MAX_REQUESTS", "50000"))
MAX_SECONDS = int(os.getenv("LBX_MAX_SECONDS", str(80 * 60)))
BATCH_SIZE = int(os.getenv("LBX_BATCH_SIZE", "600"))

KEEP_FIELDS = [
    "org_code", "shop_id", "sap_id", "deptName", "org_name", "parentName",
    "third_org_name", "third_org_code", "city", "deptAddr", "phone",
    "latGd", "lngGd", "latBd", "lngBd", "lat", "lng", "shopLabels",
    "winter_start_hours", "winter_closing_hours", "summer_start_hours",
    "summer_closing_hours", "shipStartTime", "shipEndTime", "is_m_shop",
    "is_close", "deptType", "sales_scan_name", "sales_scan_id",
    "companyCode", "pdeptId",
]

_tls = threading.local()
_started = time.monotonic()
_counter_lock = threading.Lock()
_request_count = 0
_error_count = 0


def session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
        })
        _tls.session = s
    return s


def extract_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    d = data.get("data")
    if isinstance(d, dict):
        rows = d.get("data")
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    return []


def query(lat: float, lon: float) -> tuple[list[dict[str, Any]], str | None]:
    global _request_count, _error_count
    with _counter_lock:
        if _request_count >= MAX_REQUESTS or time.monotonic() - _started >= MAX_SECONDS:
            return [], "limit"
        _request_count += 1
    params = {"Latitude": round(lat, 7), "Longitude": round(lon, 7)}
    last_error = None
    for attempt in range(4):
        try:
            r = session().get(ENDPOINT, params=params, timeout=(8, 30))
            if r.status_code == 200:
                data = r.json()
                rows = extract_rows(data)
                # A valid empty response has data.data null and message 没有找到数据.
                if rows or isinstance(data, dict):
                    return rows, None
            last_error = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
        time.sleep((0.5 * (2 ** attempt)) + random.random() * 0.25)
    with _counter_lock:
        _error_count += 1
    return [], last_error


def qkey(lat: float, lon: float) -> tuple[float, float]:
    return round(float(lat), 5), round(float(lon), 5)


def store_key(row: dict[str, Any]) -> str:
    for field in ("org_code", "shop_id"):
        value = str(row.get(field) or "").strip()
        if value and value not in {"0", "None", "null"}:
            return f"{field}:{value}"
    parts = [str(row.get(x) or "").strip() for x in ("companyCode", "sap_id", "deptName", "deptAddr")]
    return "fallback:" + "|".join(parts)


def store_coord(row: dict[str, Any]) -> tuple[float, float] | None:
    for lat_key, lon_key in (("latGd", "lngGd"), ("lat", "lng"), ("latBd", "lngBd")):
        try:
            lat = float(row.get(lat_key) or 0)
            lon = float(row.get(lon_key) or 0)
            if 15 <= lat <= 55 and 70 <= lon <= 140:
                return lat, lon
        except (TypeError, ValueError):
            pass
    return None


def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {field: row.get(field, "") for field in KEEP_FIELDS}
    out["source_endpoint"] = ENDPOINT
    return out


def merge_store(stores: dict[str, dict[str, Any]], row: dict[str, Any]) -> bool:
    key = store_key(row)
    cleaned = clean_row(row)
    old = stores.get(key)
    if old is None:
        stores[key] = cleaned
        return True
    for k, v in cleaned.items():
        if (old.get(k) in (None, "")) and v not in (None, ""):
            old[k] = v
    return False


def frange(start: float, stop: float, step: float, offset: float = 0.0) -> Iterable[float]:
    x = start + offset
    while x <= stop + 1e-9:
        yield round(x, 7)
        x += step


def initial_points() -> dict[tuple[float, float], float]:
    points: dict[tuple[float, float], float] = {}
    # Two shifted grids reduce the chance that a separate local component is
    # always hidden behind the same ten nearer locations.
    for bounds in MARKETS.values():
        lat0, lat1, lon0, lon1 = bounds
        for shift in (0.0, BASE_STEP / 2):
            for lat in frange(lat0, lat1, BASE_STEP, shift):
                for lon in frange(lon0, lon1, BASE_STEP, shift):
                    points[qkey(lat, lon)] = BASE_STEP
    return points


def run_batch(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], list[dict[str, Any]], str | None]]:
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(query, lat, lon): (lat, lon) for lat, lon in points}
        for fut in as_completed(futures):
            point = futures[fut]
            try:
                rows, err = fut.result()
            except Exception as exc:  # noqa: BLE001
                rows, err = [], repr(exc)
            results.append((point, rows, err))
    return results


def write_checkpoint(stores: dict[str, dict[str, Any]], queried: set[tuple[float, float]], phase: str) -> None:
    payload = {
        "phase": phase,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "store_count": len(stores),
        "query_count": _request_count,
        "error_count": _error_count,
        "queried_point_count": len(queried),
        "elapsed_seconds": round(time.monotonic() - _started, 1),
        "stores": list(stores.values()),
    }
    tmp = OUT / "checkpoint.tmp.json"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT / "checkpoint.json")


def main() -> None:
    stores: dict[str, dict[str, Any]] = {}
    queried: set[tuple[float, float]] = set()
    store_queue: deque[tuple[float, float]] = deque()
    queued_store_points: set[tuple[float, float]] = set()

    # Geographic discovery with adaptive subdivision.
    pending = initial_points()
    level = 0
    while pending and _request_count < MAX_REQUESTS and time.monotonic() - _started < MAX_SECONDS:
        level += 1
        items = list(pending.items())
        pending = {}
        print(f"GRID level={level} points={len(items)} stores={len(stores)} requests={_request_count}", flush=True)
        for batch_start in range(0, len(items), BATCH_SIZE):
            batch_items = items[batch_start:batch_start + BATCH_SIZE]
            batch_points = [p for p, _ in batch_items if p not in queried]
            step_by_point = {p: step for p, step in batch_items}
            for point, rows, err in run_batch(batch_points):
                queried.add(point)
                for row in rows:
                    if str(row.get("is_close", "0")) not in ("", "0"):
                        continue
                    if merge_store(stores, row):
                        coord = store_coord(row)
                        if coord:
                            qp = qkey(*coord)
                            if qp not in queried and qp not in queued_store_points:
                                store_queue.append(qp)
                                queued_store_points.add(qp)
                step = step_by_point.get(point, BASE_STEP)
                if len(rows) >= 10 and step / 2 >= MIN_ADAPTIVE_STEP:
                    half = step / 2
                    quarter = step / 4
                    for dlat in (-quarter, quarter):
                        for dlon in (-quarter, quarter):
                            child = qkey(point[0] + dlat, point[1] + dlon)
                            if child not in queried:
                                pending[child] = half
            if batch_start % (BATCH_SIZE * 4) == 0:
                write_checkpoint(stores, queried, f"grid-{level}")
                print(f"  progress batch={batch_start}/{len(items)} stores={len(stores)} requests={_request_count} errors={_error_count}", flush=True)

    # Traverse the 10-nearest-neighbour graph from each discovered store.
    wave = 0
    while store_queue and _request_count < MAX_REQUESTS and time.monotonic() - _started < MAX_SECONDS:
        wave += 1
        batch_points = []
        while store_queue and len(batch_points) < BATCH_SIZE:
            point = store_queue.popleft()
            if point not in queried:
                batch_points.append(point)
        if not batch_points:
            continue
        before = len(stores)
        for point, rows, err in run_batch(batch_points):
            queried.add(point)
            for row in rows:
                if str(row.get("is_close", "0")) not in ("", "0"):
                    continue
                if merge_store(stores, row):
                    coord = store_coord(row)
                    if coord:
                        qp = qkey(*coord)
                        if qp not in queried and qp not in queued_store_points:
                            store_queue.append(qp)
                            queued_store_points.add(qp)
        added = len(stores) - before
        print(f"BFS wave={wave} queried={len(batch_points)} added={added} stores={len(stores)} queue={len(store_queue)} requests={_request_count}", flush=True)
        if wave % 5 == 0:
            write_checkpoint(stores, queried, f"bfs-{wave}")

    rows = sorted(stores.values(), key=lambda x: (
        str(x.get("third_org_name") or ""), str(x.get("city") or ""),
        str(x.get("parentName") or ""), str(x.get("deptName") or ""),
        str(x.get("org_code") or ""),
    ))
    crawl_time = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row["crawl_time_utc"] = crawl_time

    (OUT / "stores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = KEEP_FIELDS + ["source_endpoint", "crawl_time_utc"]
    with (OUT / "stores.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "source": ENDPOINT,
        "crawl_time_utc": crawl_time,
        "published_markets": list(MARKETS.keys()),
        "market_count": len(MARKETS),
        "active_unique_store_count": len(rows),
        "request_count": _request_count,
        "error_count": _error_count,
        "queried_point_count": len(queried),
        "remaining_store_queue": len(store_queue),
        "max_requests": MAX_REQUESTS,
        "max_seconds": MAX_SECONDS,
        "elapsed_seconds": round(time.monotonic() - _started, 1),
        "grid_step_degrees": BASE_STEP,
        "minimum_adaptive_step_degrees": MIN_ADAPTIVE_STEP,
        "workers": WORKERS,
        "stopped_by_limit": bool(_request_count >= MAX_REQUESTS or time.monotonic() - _started >= MAX_SECONDS),
    }
    (OUT / "crawl_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
