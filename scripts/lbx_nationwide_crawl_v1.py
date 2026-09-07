#!/usr/bin/env python3
"""Nationwide discovery crawl of the public LBX nearby-store endpoint.

Method:
1. Seed from a public China province/city/county coordinate list.
2. Add small coordinate offsets around every administrative centre.
3. Add a coarse nationwide fallback grid.
4. Recursively query every newly discovered store coordinate, which walks the
   nearest-neighbour graph inside each local store cluster.

Only the public endpoint used by LBX's H5 store selector is queried. Requests
are bounded, retried conservatively, and all output carries crawl metadata.
"""
from __future__ import annotations

import csv
import json
import math
import os
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
ADMIN_COORDS_URL = (
    "https://gist.githubusercontent.com/showmethecode9527/"
    "b6b95af804eeb76193d24f943c66811a/raw/"
    "47ef738f88b7bcbdc60adfa054b1dbf2845ec813/longitude-latitude-china.json"
)
AMAP_CITY_URL = "https://www.amap.com/service/cityList?version=1"
OUT = Path("nationwide_crawl_output")
OUT.mkdir(exist_ok=True)

WORKERS = int(os.getenv("LBX_WORKERS", "18"))
MAX_REQUESTS = int(os.getenv("LBX_MAX_REQUESTS", "52000"))
MAX_RUNTIME_SECONDS = int(os.getenv("LBX_MAX_RUNTIME_SECONDS", "6900"))
BATCH_SIZE = WORKERS * 4
CHECKPOINT_EVERY = 3000

_tls = threading.local()


def get_session() -> requests.Session:
    if not hasattr(_tls, "session"):
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": (
                    "https://yx.lbxcn.com/h5/springgame/index.html?"
                    "gameCode=spring_251230_6&source=4"
                ),
            }
        )
        _tls.session = s
    return _tls.session


def extract_rows(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, dict):
        return []
    outer = obj.get("data")
    if isinstance(outer, dict):
        rows = outer.get("data")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        rows = outer.get("rows")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    rows = obj.get("rows")
    if isinstance(rows, list):
        return [r for r in rows if isinstance(r, dict)]
    return []


def fetch_point(item: tuple[float, float, str, str, str]) -> dict[str, Any]:
    lat, lon, kind, province, seed_name = item
    last_error = None
    for attempt in range(3):
        started = time.time()
        try:
            resp = get_session().get(
                ENDPOINT,
                params={"Latitude": f"{lat:.8f}", "Longitude": f"{lon:.8f}"},
                timeout=(6, 20),
            )
            resp.raise_for_status()
            obj = resp.json()
            rows = extract_rows(obj)
            time.sleep(0.02)
            return {
                "lat": lat,
                "lon": lon,
                "kind": kind,
                "province": province,
                "seed_name": seed_name,
                "rows": rows,
                "status": resp.status_code,
                "elapsed_ms": round((time.time() - started) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
            time.sleep(0.35 * (attempt + 1))
    return {
        "lat": lat,
        "lon": lon,
        "kind": kind,
        "province": province,
        "seed_name": seed_name,
        "rows": [],
        "error": last_error,
    }


def coord_key(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        a, b = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90 <= a <= 90 and -180 <= b <= 180):
        return None
    return (round(a, 5), round(b, 5))


def store_key(row: dict[str, Any]) -> str:
    for field in ("shop_id", "sap_id", "org_code"):
        value = str(row.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    return "fallback:" + "|".join(
        str(row.get(k) or "").strip()
        for k in ("deptName", "deptAddr", "phone", "latGd", "lngGd")
    )


def load_admin_seeds() -> tuple[list[tuple[float, float, str, str, str]], list[dict[str, Any]]]:
    response = requests.get(ADMIN_COORDS_URL, timeout=45)
    response.raise_for_status()
    data = response.json()
    seeds: list[tuple[float, float, str, str, str]] = []
    admin_points: list[dict[str, Any]] = []

    offsets = [
        (0.0, 0.0),
        (0.08, 0.0),
        (-0.08, 0.0),
        (0.0, 0.08),
        (0.0, -0.08),
        (0.08, 0.08),
        (0.08, -0.08),
        (-0.08, 0.08),
        (-0.08, -0.08),
    ]

    for province_obj in data:
        province = str(province_obj.get("name") or "").strip()
        items = [province_obj] + list(province_obj.get("children") or [])
        for obj in items:
            name = str(obj.get("name") or "").strip()
            try:
                lon = float(obj.get("log"))
                lat = float(obj.get("lat"))
            except (TypeError, ValueError):
                continue
            admin_points.append(
                {"province": province, "name": name, "lat": lat, "lon": lon}
            )
            for dlat, dlon in offsets:
                seeds.append((lat + dlat, lon + dlon, "admin", province, name))

    # Coarse fallback grid. It catches renamed/new districts and store clusters
    # away from old administrative centres, while keeping total requests bounded.
    lat = 18.0
    while lat <= 54.0 + 1e-9:
        lon = 73.5
        while lon <= 135.0 + 1e-9:
            seeds.append((lat, lon, "grid", "", f"grid:{lat:.2f},{lon:.2f}"))
            lon += 0.75
        lat += 0.75

    # Add current Amap city centres when available. Parsing is deliberately
    # generic because the endpoint has changed shape over time.
    try:
        city_obj = requests.get(AMAP_CITY_URL, timeout=30).json()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                name = str(value.get("name") or value.get("city_name") or "").strip()
                x = value.get("x") or value.get("lng") or value.get("longitude")
                y = value.get("y") or value.get("lat") or value.get("latitude")
                try:
                    lon_v = float(x)
                    lat_v = float(y)
                except (TypeError, ValueError):
                    pass
                else:
                    if 70 < lon_v < 140 and 15 < lat_v < 56:
                        seeds.append((lat_v, lon_v, "amap_city", "", name))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(city_obj)
    except Exception as exc:  # noqa: BLE001
        print("AMAP city seed warning:", repr(exc), flush=True)

    # Coordinate-level deduplication of seeds.
    deduped: list[tuple[float, float, str, str, str]] = []
    seen: set[tuple[float, float]] = set()
    for item in seeds:
        key = coord_key(item[0], item[1])
        if key is None or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped, admin_points


def nearest_admin(lat: float, lon: float, admin_points: list[dict[str, Any]]) -> dict[str, Any]:
    # Equirectangular approximation is sufficient for nearest seed assignment.
    best = None
    best_score = float("inf")
    cos_lat = math.cos(math.radians(lat))
    for p in admin_points:
        dlat = lat - float(p["lat"])
        dlon = (lon - float(p["lon"])) * cos_lat
        score = dlat * dlat + dlon * dlon
        if score < best_score:
            best_score = score
            best = p
    return best or {"province": "", "name": "", "lat": None, "lon": None}


def serialise_store(row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    rec = dict(row)
    rec["_crawl_first_query_kind"] = meta.get("kind", "")
    rec["_crawl_first_seed_province"] = meta.get("province", "")
    rec["_crawl_first_seed_name"] = meta.get("seed_name", "")
    rec["_crawl_first_query_lat"] = meta.get("lat")
    rec["_crawl_first_query_lon"] = meta.get("lon")
    return rec


def save_checkpoint(
    stores: dict[str, dict[str, Any]],
    summary: dict[str, Any],
    admin_points: list[dict[str, Any]],
    prefix: str = "checkpoint",
) -> None:
    tmp = OUT / f"{prefix}_stores.jsonl"
    with tmp.open("w", encoding="utf-8") as fh:
        for row in stores.values():
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (OUT / f"{prefix}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if prefix == "final":
        (OUT / "admin_points.json").write_text(
            json.dumps(admin_points, ensure_ascii=False), encoding="utf-8"
        )


def main() -> None:
    crawl_started = datetime.now(timezone.utc).isoformat()
    seeds, admin_points = load_admin_seeds()
    print(
        json.dumps(
            {"seed_count": len(seeds), "admin_point_count": len(admin_points)},
            ensure_ascii=False,
        ),
        flush=True,
    )

    seed_queue = deque(seeds)
    store_queue: deque[tuple[float, float, str, str, str]] = deque()
    queued_coords = {coord_key(x[0], x[1]) for x in seeds}
    queued_coords.discard(None)
    queried: set[tuple[float, float]] = set()
    stores: dict[str, dict[str, Any]] = {}
    error_rows: list[dict[str, Any]] = []
    response_counts: Counter[int] = Counter()
    source_counts: Counter[str] = Counter()
    requests_made = 0
    start = time.time()
    last_checkpoint = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while (
            (seed_queue or store_queue)
            and requests_made < MAX_REQUESTS
            and time.time() - start < MAX_RUNTIME_SECONDS
        ):
            batch: list[tuple[float, float, str, str, str]] = []
            for i in range(BATCH_SIZE):
                if not seed_queue and not store_queue:
                    break
                # Interleave discovery seeds and recursive store queries so one
                # dense city cannot starve nationwide coverage.
                if store_queue and (i % 2 == 0 or not seed_queue):
                    item = store_queue.popleft()
                else:
                    item = seed_queue.popleft()
                key = coord_key(item[0], item[1])
                if key is None or key in queried:
                    continue
                queried.add(key)
                batch.append(item)
                if requests_made + len(batch) >= MAX_REQUESTS:
                    break
            if not batch:
                continue

            futures = [pool.submit(fetch_point, item) for item in batch]
            for future in as_completed(futures):
                result = future.result()
                requests_made += 1
                rows = result.pop("rows")
                response_counts[len(rows)] += 1
                source_counts[str(result.get("kind") or "")] += 1
                if result.get("error"):
                    error_rows.append(result)
                for row in rows:
                    key = store_key(row)
                    if key not in stores:
                        stores[key] = serialise_store(row, result)
                    lat = row.get("latGd") or row.get("lat") or row.get("latBd")
                    lon = row.get("lngGd") or row.get("lng") or row.get("lngBd")
                    ck = coord_key(lat, lon)
                    if ck is None or ck in queried or ck in queued_coords:
                        continue
                    # Province propagation is only provisional; final province is
                    # assigned by nearest administrative centre below.
                    store_queue.append(
                        (
                            float(lat),
                            float(lon),
                            "store",
                            str(result.get("province") or ""),
                            str(row.get("deptName") or key),
                        )
                    )
                    queued_coords.add(ck)

            if requests_made % 500 < len(batch):
                progress = {
                    "requests": requests_made,
                    "unique_stores": len(stores),
                    "seed_queue": len(seed_queue),
                    "store_queue": len(store_queue),
                    "errors": len(error_rows),
                    "elapsed_s": round(time.time() - start, 1),
                }
                print(json.dumps(progress, ensure_ascii=False), flush=True)
            if requests_made - last_checkpoint >= CHECKPOINT_EVERY:
                summary = {
                    "status": "running",
                    "requests": requests_made,
                    "unique_stores": len(stores),
                    "seed_queue": len(seed_queue),
                    "store_queue": len(store_queue),
                    "elapsed_s": round(time.time() - start, 1),
                }
                save_checkpoint(stores, summary, admin_points, "checkpoint")
                last_checkpoint = requests_made

    # Attach nearest administrative seed as a transparent province hint.
    for row in stores.values():
        try:
            lat = float(row.get("latGd") or row.get("lat") or row.get("latBd"))
            lon = float(row.get("lngGd") or row.get("lng") or row.get("lngBd"))
        except (TypeError, ValueError):
            row["_nearest_admin_province"] = ""
            row["_nearest_admin_name"] = ""
            continue
        nearest = nearest_admin(lat, lon, admin_points)
        row["_nearest_admin_province"] = nearest.get("province", "")
        row["_nearest_admin_name"] = nearest.get("name", "")

    rows_sorted = sorted(
        stores.values(),
        key=lambda r: (
            str(r.get("_nearest_admin_province") or ""),
            str(r.get("city") or ""),
            str(r.get("parentName") or ""),
            str(r.get("deptName") or ""),
        ),
    )

    summary = {
        "status": "completed",
        "crawl_started_utc": crawl_started,
        "crawl_finished_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT,
        "admin_seed_source": ADMIN_COORDS_URL,
        "requests": requests_made,
        "unique_stores": len(rows_sorted),
        "remaining_seed_queue": len(seed_queue),
        "remaining_store_queue": len(store_queue),
        "max_requests": MAX_REQUESTS,
        "max_runtime_seconds": MAX_RUNTIME_SECONDS,
        "workers": WORKERS,
        "elapsed_s": round(time.time() - start, 1),
        "error_count": len(error_rows),
        "response_row_count_distribution": dict(sorted(response_counts.items())),
        "query_source_distribution": dict(source_counts),
        "complete_queue_exhaustion": not seed_queue and not store_queue,
    }

    save_checkpoint(stores, summary, admin_points, "final")
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "errors.json").write_text(
        json.dumps(error_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    all_fields = sorted({key for row in rows_sorted for key in row.keys()})
    preferred = [
        "shop_id", "sap_id", "org_code", "deptName", "org_name",
        "parentName", "third_org_name", "third_org_code", "companyCode",
        "city", "deptAddr", "phone", "shopLabels", "sales_scan_name",
        "is_close", "deptType", "latGd", "lngGd", "latBd", "lngBd",
        "lat", "lng", "winter_start_hours", "winter_closing_hours",
        "summer_start_hours", "summer_closing_hours", "shipStartTime",
        "shipEndTime", "_nearest_admin_province", "_nearest_admin_name",
        "_crawl_first_query_kind", "_crawl_first_seed_province",
        "_crawl_first_seed_name", "_crawl_first_query_lat",
        "_crawl_first_query_lon",
    ]
    fields = preferred + [f for f in all_fields if f not in preferred]
    with (OUT / "stores.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_sorted)

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
