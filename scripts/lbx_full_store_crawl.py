#!/usr/bin/env python3
"""Collect LBX Group store records from its public nearby-store endpoint.

Method:
1. Build a mainland-China hexagonal seed grid with a covering radius below the
   public endpoint's observed search radius.
2. Query the public endpoint at every seed point.
3. Query once at every newly discovered store coordinate, expanding through the
   store-neighbour graph until no new records are found.
4. Add a denser second-pass grid in saturated cells.
5. Deduplicate by the official ``shop_id`` and export raw + normalized files.

The script uses ordinary public GET requests, moderate concurrency, retries and
no authentication/CAPTCHA bypass.
"""
from __future__ import annotations

import asyncio
import csv
import json
import math
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
import requests
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
PAGE_REFERER = "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4"
OUT = Path(os.getenv("LBX_OUT", "lbx_crawl_output"))
OUT.mkdir(parents=True, exist_ok=True)

CONCURRENCY = int(os.getenv("LBX_CONCURRENCY", "18"))
MAX_REQUESTS = int(os.getenv("LBX_MAX_REQUESTS", "55000"))
REQUEST_TIMEOUT = float(os.getenv("LBX_REQUEST_TIMEOUT", "22"))
MAX_RETRIES = int(os.getenv("LBX_MAX_RETRIES", "3"))
POLITE_DELAY = float(os.getenv("LBX_POLITE_DELAY", "0.035"))

# A triangular/hexagonal lattice. With 31 km horizontal spacing and 26.8 km
# row spacing, every point is within about 18 km of a seed point.
GRID_X_KM = float(os.getenv("LBX_GRID_X_KM", "31"))
GRID_Y_KM = float(os.getenv("LBX_GRID_Y_KM", "26.8"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": PAGE_REFERER,
}

RAW_COLUMNS = [
    "shop_id", "sap_id", "deptName", "org_name", "parentName", "companyCode",
    "pdeptId", "third_org_name", "third_org_code", "org_code", "city", "deptAddr",
    "phone", "contactPerson", "latGd", "lngGd", "latBd", "lngBd", "lat", "lng",
    "distance", "distanceGd", "distanceBd", "shopLabels", "is_close", "is_m_shop",
    "deptType", "sales_scan_name", "sales_scan_id", "winter_start_hours",
    "winter_closing_hours", "summer_start_hours", "summer_closing_hours",
    "shipStartTime", "shipEndTime",
]
META_COLUMNS = [
    "_first_seen_source", "_first_seen_query_lat", "_first_seen_query_lng",
    "_first_seen_distance", "_first_seen_at", "_last_seen_at", "_seen_count",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def download_china_geometry():
    """Return a union of mainland province polygons; fall back to a rough mask."""
    urls = [
        "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json",
        "https://geo.datav.aliyun.com/areas_v3/bound/geojson?code=100000_full",
    ]
    session = requests.Session()
    session.headers.update({
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json,*/*",
    })
    errors = []
    for url in urls:
        try:
            r = session.get(url, timeout=45)
            r.raise_for_status()
            obj = r.json()
            geoms = []
            for feat in obj.get("features", []):
                props = feat.get("properties") or {}
                adcode = str(props.get("adcode") or "")
                name = str(props.get("name") or "")
                # The listed company reports mainland operations. Exclude HK,
                # Macau and Taiwan from the seed grid while retaining Hainan.
                if adcode in {"710000", "810000", "820000"} or name in {"台湾省", "香港特别行政区", "澳门特别行政区"}:
                    continue
                try:
                    g = shape(feat.get("geometry"))
                    if not g.is_valid:
                        g = g.buffer(0)
                    if not g.is_empty:
                        geoms.append(g)
                except Exception:
                    continue
            if geoms:
                merged = unary_union(geoms)
                (OUT / "china_boundary_source.json").write_text(
                    json.dumps({"source": url, "feature_count": len(geoms)}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return merged
        except Exception as exc:  # noqa: BLE001
            errors.append({"url": url, "error": repr(exc)})
    # Rough mainland mask made from broad latitude bands. It is intentionally
    # over-inclusive, so failure to fetch DataV does not create geographic gaps.
    from shapely.geometry import box
    bands = [
        box(108, 18, 122, 22.5),
        box(99, 22, 123, 26.5),
        box(92, 26, 123.5, 30.5),
        box(83, 30, 123.5, 34.5),
        box(74, 34, 125, 39),
        box(74, 39, 128, 43),
        box(79, 43, 135, 47.5),
        box(82, 47.5, 135, 50.5),
        box(118, 50.5, 135, 54),
    ]
    (OUT / "china_boundary_source.json").write_text(
        json.dumps({"source": "fallback_latitude_bands", "errors": errors}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return unary_union(bands)


def hex_seed_points(geom) -> list[tuple[float, float, str]]:
    """Generate GCJ-compatible longitude/latitude seed points inside China."""
    # Buffer slightly to include border stores and coordinate-system offsets.
    mask = geom.buffer(0.18)
    prepared = prep(mask)
    minx, miny, maxx, maxy = mask.bounds
    miny = max(17.5, miny)
    maxy = min(54.5, maxy)
    minx = max(72.0, minx)
    maxx = min(136.0, maxx)
    lat_step = GRID_Y_KM / 111.32
    points: list[tuple[float, float, str]] = []
    row = 0
    lat = miny
    while lat <= maxy + 1e-9:
        cos_lat = max(0.35, math.cos(math.radians(lat)))
        lon_step = GRID_X_KM / (111.32 * cos_lat)
        lon = minx + (0.5 * lon_step if row % 2 else 0.0)
        while lon <= maxx + 1e-9:
            p = Point(lon, lat)
            if prepared.contains(p) or prepared.intersects(p):
                points.append((round(lat, 6), round(lon, 6), "national_hex_grid"))
            lon += lon_step
        lat += lat_step
        row += 1
    return points


def point_key(lat: float, lng: float) -> tuple[int, int]:
    # About one metre. This collapses exact/shared store coordinates while not
    # merging adjacent pharmacies.
    return (round(lat * 100000), round(lng * 100000))


def valid_coord(lat: Any, lng: Any) -> tuple[float, float] | None:
    try:
        la = float(lat)
        lo = float(lng)
    except (TypeError, ValueError):
        return None
    if not (15.0 <= la <= 56.0 and 70.0 <= lo <= 138.0):
        return None
    return la, lo


def store_coord(row: dict[str, Any]) -> tuple[float, float] | None:
    for lat_key, lng_key in (("latGd", "lngGd"), ("lat", "lng"), ("latBd", "lngBd")):
        coord = valid_coord(row.get(lat_key), row.get(lng_key))
        if coord:
            return coord
    return None


def store_key(row: dict[str, Any]) -> str:
    for key in ("shop_id", "sap_id", "org_code"):
        value = str(row.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    coord = store_coord(row)
    return "fallback:" + "|".join([
        str(row.get("deptName") or "").strip(),
        str(row.get("deptAddr") or "").strip(),
        f"{coord[0]:.6f},{coord[1]:.6f}" if coord else "",
    ])


def merge_store(old: dict[str, Any], new: dict[str, Any], source: str, qlat: float, qlng: float) -> None:
    for k, v in new.items():
        if (old.get(k) is None or old.get(k) == "") and v not in (None, ""):
            old[k] = v
    old["_last_seen_at"] = utc_now()
    old["_seen_count"] = int(old.get("_seen_count") or 1) + 1
    if not old.get("_first_seen_distance") and new.get("distance") not in (None, ""):
        old["_first_seen_distance"] = new.get("distance")


class CrawlState:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[float, float, str] | None] = asyncio.Queue()
        self.seen_points: set[tuple[int, int]] = set()
        self.stores: dict[str, dict[str, Any]] = {}
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.empty_count = 0
        self.status_counts: Counter[str] = Counter()
        self.row_count_hist: Counter[int] = Counter()
        self.query_cells: dict[tuple[int, int], dict[str, Any]] = {}
        self.failures: list[dict[str, Any]] = []
        self.started_at = utc_now()
        self.start_monotonic = time.monotonic()
        self.stop_requested = False

    def enqueue(self, lat: float, lng: float, source: str) -> bool:
        if self.stop_requested or self.request_count + self.queue.qsize() >= MAX_REQUESTS:
            return False
        coord = valid_coord(lat, lng)
        if not coord:
            return False
        key = point_key(*coord)
        if key in self.seen_points:
            return False
        self.seen_points.add(key)
        self.queue.put_nowait((coord[0], coord[1], source))
        return True

    def add_rows(self, rows: list[dict[str, Any]], source: str, qlat: float, qlng: float) -> int:
        new_count = 0
        now = utc_now()
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            key = store_key(raw)
            if key in self.stores:
                merge_store(self.stores[key], raw, source, qlat, qlng)
                continue
            row = dict(raw)
            row["_first_seen_source"] = source
            row["_first_seen_query_lat"] = qlat
            row["_first_seen_query_lng"] = qlng
            row["_first_seen_distance"] = raw.get("distance") or raw.get("distanceGd")
            row["_first_seen_at"] = now
            row["_last_seen_at"] = now
            row["_seen_count"] = 1
            self.stores[key] = row
            new_count += 1
            coord = store_coord(row)
            if coord:
                self.enqueue(coord[0], coord[1], "discovered_store")
        return new_count


async def fetch_rows(session: aiohttp.ClientSession, lat: float, lng: float) -> tuple[list[dict[str, Any]], int | None, str | None]:
    params = {"Latitude": f"{lat:.7f}", "Longitude": f"{lng:.7f}"}
    last_error: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(ENDPOINT, params=params, timeout=timeout) as resp:
                status = resp.status
                text = await resp.text(encoding="utf-8", errors="replace")
                if status == 200:
                    try:
                        obj = json.loads(text.lstrip("\ufeff"))
                    except json.JSONDecodeError:
                        last_error = f"json_decode:{text[:180]}"
                    else:
                        data = obj.get("data") if isinstance(obj, dict) else None
                        rows = data.get("data") if isinstance(data, dict) else None
                        if isinstance(rows, list):
                            return [x for x in rows if isinstance(x, dict)], status, None
                        last_error = f"unexpected_schema:{text[:280]}"
                elif status in {429, 500, 502, 503, 504}:
                    last_error = f"http_{status}:{text[:180]}"
                else:
                    return [], status, f"http_{status}:{text[:280]}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = repr(exc)
        if attempt < MAX_RETRIES:
            await asyncio.sleep((0.45 * (2 ** (attempt - 1))) + random.random() * 0.25)
    return [], None, last_error or "unknown_error"


async def worker(worker_id: int, state: CrawlState, session: aiohttp.ClientSession) -> None:
    while True:
        item = await state.queue.get()
        if item is None:
            state.queue.task_done()
            return
        lat, lng, source = item
        if state.request_count >= MAX_REQUESTS:
            state.stop_requested = True
            state.queue.task_done()
            continue
        state.request_count += 1
        rows, status, error = await fetch_rows(session, lat, lng)
        if status is not None:
            state.status_counts[str(status)] += 1
        if error:
            state.error_count += 1
            if len(state.failures) < 5000:
                state.failures.append({
                    "lat": lat, "lng": lng, "source": source, "status": status,
                    "error": error, "at": utc_now(),
                })
        else:
            state.success_count += 1
            if not rows:
                state.empty_count += 1
            state.row_count_hist[len(rows)] += 1
            new_count = state.add_rows(rows, source, lat, lng)
            cell = (math.floor(lat / 0.12), math.floor(lng / 0.12))
            rec = state.query_cells.setdefault(cell, {
                "max_rows": 0, "queries": 0, "new_stores": 0,
                "sample_lat": lat, "sample_lng": lng,
            })
            rec["max_rows"] = max(int(rec["max_rows"]), len(rows))
            rec["queries"] = int(rec["queries"]) + 1
            rec["new_stores"] = int(rec["new_stores"]) + new_count
        if state.request_count % 500 == 0:
            elapsed = time.monotonic() - state.start_monotonic
            print(json.dumps({
                "progress": state.request_count,
                "stores": len(state.stores),
                "queue": state.queue.qsize(),
                "success": state.success_count,
                "errors": state.error_count,
                "empty": state.empty_count,
                "requests_per_sec": round(state.request_count / max(1.0, elapsed), 2),
                "row_count_hist": dict(state.row_count_hist),
            }, ensure_ascii=False), flush=True)
        state.queue.task_done()
        if POLITE_DELAY:
            await asyncio.sleep(POLITE_DELAY)


def enqueue_dense_second_pass(state: CrawlState) -> int:
    """Add local points in cells that repeatedly hit the endpoint result cap."""
    if not state.row_count_hist:
        return 0
    observed_cap = max(state.row_count_hist)
    threshold = max(5, observed_cap)
    added = 0
    # A 0.12-degree cell is roughly 10-13 km. Five deterministic points per
    # saturated cell help expose secondary dense clusters hidden by a top-N cap.
    offsets = [(0.0, 0.0), (-0.035, -0.035), (-0.035, 0.035), (0.035, -0.035), (0.035, 0.035)]
    for (ilat, ilng), rec in state.query_cells.items():
        if int(rec.get("max_rows") or 0) < threshold:
            continue
        center_lat = (ilat + 0.5) * 0.12
        center_lng = (ilng + 0.5) * 0.12
        for dlat, dlng in offsets:
            if state.enqueue(center_lat + dlat, center_lng + dlng, "dense_cell_second_pass"):
                added += 1
    print(json.dumps({
        "second_pass": True,
        "observed_cap": observed_cap,
        "threshold": threshold,
        "points_added": added,
        "saturated_cells": sum(1 for rec in state.query_cells.values() if int(rec.get("max_rows") or 0) >= threshold),
    }, ensure_ascii=False), flush=True)
    return added


def export_outputs(state: CrawlState, seed_count: int, second_pass_added: int) -> None:
    rows = list(state.stores.values())
    def sort_key(r: dict[str, Any]):
        return (
            str(r.get("parentName") or ""),
            str(r.get("city") or ""),
            str(r.get("deptName") or ""),
            str(r.get("shop_id") or ""),
        )
    rows.sort(key=sort_key)
    (OUT / "stores_raw.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    all_columns = RAW_COLUMNS + META_COLUMNS
    extras = sorted({k for r in rows for k in r.keys()} - set(all_columns))
    columns = all_columns + extras
    with (OUT / "stores_raw.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in columns})
    with (OUT / "failed_queries.csv").open("w", encoding="utf-8-sig", newline="") as f:
        columns_f = ["lat", "lng", "source", "status", "error", "at"]
        w = csv.DictWriter(f, fieldnames=columns_f, extrasaction="ignore")
        w.writeheader()
        w.writerows(state.failures)
    parent_counts = Counter(str(r.get("parentName") or "(空)") for r in rows)
    city_counts = Counter(str(r.get("city") or "(空)") for r in rows)
    company_counts = Counter(str(r.get("companyCode") or "(空)") for r in rows)
    meta = {
        "method": "official_public_nearby_endpoint_hex_grid_plus_store_graph",
        "endpoint": ENDPOINT,
        "started_at": state.started_at,
        "completed_at": utc_now(),
        "elapsed_seconds": round(time.monotonic() - state.start_monotonic, 2),
        "grid_x_km": GRID_X_KM,
        "grid_y_km": GRID_Y_KM,
        "seed_count": seed_count,
        "second_pass_points_added": second_pass_added,
        "unique_query_points": len(state.seen_points),
        "requests_made": state.request_count,
        "successful_requests": state.success_count,
        "error_requests": state.error_count,
        "empty_requests": state.empty_count,
        "http_status_counts": dict(state.status_counts),
        "row_count_histogram": dict(state.row_count_hist),
        "unique_store_records": len(rows),
        "records_with_coordinates": sum(1 for r in rows if store_coord(r)),
        "records_is_close_0": sum(1 for r in rows if str(r.get("is_close")) == "0"),
        "records_is_close_1": sum(1 for r in rows if str(r.get("is_close")) == "1"),
        "top_parent_names": parent_counts.most_common(100),
        "top_city_values": city_counts.most_common(100),
        "company_code_counts": company_counts.most_common(),
        "max_requests": MAX_REQUESTS,
        "concurrency": CONCURRENCY,
        "notes": [
            "The source is a public LBX campaign nearby-store endpoint, not an official master-data export.",
            "Deduplication uses shop_id, then sap_id/org_code, then name+address+coordinates.",
            "A result may include clinics, convenience stores or stale internal records; downstream classification is required.",
        ],
    }
    (OUT / "crawl_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2), flush=True)


async def async_main() -> None:
    state = CrawlState()
    geom = download_china_geometry()
    seeds = hex_seed_points(geom)
    for lat, lng, source in seeds:
        state.enqueue(lat, lng, source)
    seed_count = state.queue.qsize()
    print(json.dumps({
        "start": True,
        "endpoint": ENDPOINT,
        "seed_count": seed_count,
        "concurrency": CONCURRENCY,
        "max_requests": MAX_REQUESTS,
        "grid_x_km": GRID_X_KM,
        "grid_y_km": GRID_Y_KM,
    }, ensure_ascii=False), flush=True)

    connector = aiohttp.TCPConnector(limit=CONCURRENCY, limit_per_host=CONCURRENCY, ttl_dns_cache=300)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        workers = [asyncio.create_task(worker(i, state, session)) for i in range(CONCURRENCY)]
        await state.queue.join()
        second_pass_added = 0
        if state.request_count < MAX_REQUESTS:
            second_pass_added = enqueue_dense_second_pass(state)
            if second_pass_added:
                await state.queue.join()
        for _ in workers:
            state.queue.put_nowait(None)
        await state.queue.join()
        await asyncio.gather(*workers)

    export_outputs(state, seed_count, second_pass_added)


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(130)
