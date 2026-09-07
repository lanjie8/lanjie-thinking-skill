#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

API_URL = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
SEED_FILE = Path("city_seed_output/official_market_seeds.csv")
OUT_DIR = Path("full_store_output_v3")
OUT_DIR.mkdir(parents=True, exist_ok=True)

WORKERS = int(os.environ.get("LBX_WORKERS", "8"))
MAX_REQUESTS = int(os.environ.get("LBX_MAX_REQUESTS", "24000"))
REQUEST_TIMEOUT = float(os.environ.get("LBX_TIMEOUT", "15"))
COORD_PRECISION = 5

thread_local = threading.local()


def get_session() -> requests.Session:
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
            }
        )
        adapter = requests.adapters.HTTPAdapter(pool_connections=WORKERS * 2, pool_maxsize=WORKERS * 2)
        session.mount("https://", adapter)
        thread_local.session = session
    return thread_local.session


def coord_key(lat: Any, lon: Any) -> tuple[float, float]:
    return (round(float(lat), COORD_PRECISION), round(float(lon), COORD_PRECISION))


def load_seeds() -> list[tuple[float, float, str]]:
    rows: list[dict[str, str]] = []
    with SEED_FILE.open("r", encoding="utf-8-sig", newline="") as handle:
        rows.extend(csv.DictReader(handle))

    seeds: list[tuple[float, float, str]] = []
    # Nine points around each official-market administrative centre.  This
    # improves coverage for suburban/county clusters while keeping traffic
    # modest.  Returned store coordinates are subsequently traversed as a graph.
    offsets = [
        (0.0, 0.0),
        (-0.30, 0.0),
        (0.30, 0.0),
        (0.0, -0.40),
        (0.0, 0.40),
        (-0.25, -0.35),
        (-0.25, 0.35),
        (0.25, -0.35),
        (0.25, 0.35),
    ]
    for row in rows:
        if str(row.get("official_market", "")).lower() not in {"true", "1", "yes"}:
            continue
        lat = float(row["latitude"])
        lon = float(row["longitude"])
        level = row.get("level", "")
        # Province-level centres are useful for municipalities; prefectures and
        # county-level special cities are the main coverage anchors.
        use_offsets = offsets if level in {"province", "prefecture", "county"} else [(0.0, 0.0)]
        for dlat, dlon in use_offsets:
            seeds.append(
                (
                    lat + dlat,
                    lon + dlon,
                    f"seed:{row.get('province','')}|{row.get('label') or row.get('name','')}|{level}|{dlat:+.2f},{dlon:+.2f}",
                )
            )

    unique: dict[tuple[float, float], tuple[float, float, str]] = {}
    for lat, lon, source in seeds:
        unique.setdefault(coord_key(lat, lon), (lat, lon, source))
    return list(unique.values())


def recursively_find_lists(value: Any, path: str = "$") -> list[tuple[str, list[dict[str, Any]]]]:
    found: list[tuple[str, list[dict[str, Any]]]] = []
    if isinstance(value, list):
        dict_rows = [item for item in value if isinstance(item, dict)]
        if dict_rows:
            found.append((path, dict_rows))
        for idx, item in enumerate(value[:10]):
            found.extend(recursively_find_lists(item, f"{path}[{idx}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(recursively_find_lists(item, f"{path}.{key}"))
    return found


def list_score(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return -1.0
    keys = {str(key).lower() for row in rows[:10] for key in row.keys()}
    score = min(len(rows), 1000) / 1000.0
    for token in ("shop_id", "shopid", "sap_id", "sapid", "org_code", "orgcode", "deptname", "shopname"):
        if token in keys:
            score += 4
    for token in ("latgd", "lnggd", "latitude", "longitude", "lat", "lng"):
        if token in keys:
            score += 2
    for token in ("address", "deptaddress", "shopaddress", "phone", "telephone"):
        if token in keys:
            score += 1
    return score


def extract_rows(obj: Any) -> tuple[list[dict[str, Any]], str | None]:
    # Known response shape first.
    if isinstance(obj, dict):
        data = obj.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            rows = [item for item in data["data"] if isinstance(item, dict)]
            if rows:
                return rows, "$.data.data"
    candidates = recursively_find_lists(obj)
    if not candidates:
        return [], None
    path, rows = max(candidates, key=lambda item: list_score(item[1]))
    if list_score(rows) < 2:
        return [], path
    return rows, path


def first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def get_store_coord(row: dict[str, Any]) -> tuple[float, float] | None:
    lat = first_value(row, ("latGd", "latitude", "lat", "Latitude", "shopLat", "deptLat"))
    lon = first_value(row, ("lngGd", "longitude", "lng", "lon", "Longitude", "shopLng", "deptLng"))
    if lat in (None, "") or lon in (None, ""):
        return None
    try:
        f_lat, f_lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90 <= f_lat <= 90 and -180 <= f_lon <= 180):
        return None
    return f_lat, f_lon


def store_key(row: dict[str, Any]) -> str:
    identifier = first_value(
        row,
        (
            "shop_id",
            "shopId",
            "sap_id",
            "sapId",
            "org_code",
            "orgCode",
            "deptCode",
            "storeCode",
            "id",
        ),
    )
    if identifier not in (None, ""):
        return f"id:{identifier}"
    name = first_value(row, ("deptName", "shopName", "storeName", "name")) or ""
    address = first_value(row, ("deptAddress", "shopAddress", "storeAddress", "address")) or ""
    coord = get_store_coord(row)
    coord_text = f"{coord[0]:.6f},{coord[1]:.6f}" if coord else ""
    return f"fallback:{name}|{address}|{coord_text}"


def fetch_one(item: tuple[float, float, str]) -> dict[str, Any]:
    lat, lon, source = item
    started = time.time()
    last_error: str | None = None
    for attempt in range(3):
        try:
            response = get_session().get(
                API_URL,
                params={"Latitude": f"{lat:.7f}", "Longitude": f"{lon:.7f}"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            obj = response.json()
            rows, row_path = extract_rows(obj)
            return {
                "lat": lat,
                "lon": lon,
                "source": source,
                "status": response.status_code,
                "rows": rows,
                "row_path": row_path,
                "top_keys": list(obj.keys()) if isinstance(obj, dict) else None,
                "elapsed": round(time.time() - started, 3),
                "response": obj,
            }
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
            time.sleep(0.35 * (attempt + 1))
    return {
        "lat": lat,
        "lon": lon,
        "source": source,
        "status": None,
        "rows": [],
        "row_path": None,
        "elapsed": round(time.time() - started, 3),
        "error": last_error,
    }


def scalarize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_store_csv(stores: dict[str, dict[str, Any]], meta: dict[str, dict[str, Any]]) -> list[str]:
    all_keys = {str(key) for row in stores.values() for key in row.keys()}
    priority = [
        "deptName",
        "shopName",
        "storeName",
        "name",
        "shop_id",
        "shopId",
        "sap_id",
        "sapId",
        "org_code",
        "orgCode",
        "deptCode",
        "storeCode",
        "deptAddress",
        "shopAddress",
        "storeAddress",
        "address",
        "province",
        "city",
        "district",
        "phone",
        "telephone",
        "latGd",
        "lngGd",
        "latitude",
        "longitude",
        "lat",
        "lng",
        "distance",
    ]
    ordered = [key for key in priority if key in all_keys]
    ordered.extend(sorted(all_keys - set(ordered), key=lambda value: value.lower()))
    fieldnames = ["__store_key", "__first_source", "__first_query_lat", "__first_query_lon"] + ordered
    with (OUT_DIR / "stores_all_fields.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for key, row in sorted(stores.items(), key=lambda item: item[0]):
            record = {name: scalarize(value) for name, value in row.items()}
            record.update(
                {
                    "__store_key": key,
                    "__first_source": meta[key].get("source"),
                    "__first_query_lat": meta[key].get("query_lat"),
                    "__first_query_lon": meta[key].get("query_lon"),
                }
            )
            writer.writerow(record)
    return fieldnames


def main() -> None:
    seeds = load_seeds()
    queue: deque[tuple[float, float, str]] = deque(seeds)
    queued = {coord_key(lat, lon) for lat, lon, _ in seeds}
    queried: set[tuple[float, float]] = set()
    stores: dict[str, dict[str, Any]] = {}
    store_meta: dict[str, dict[str, Any]] = {}
    query_log: list[dict[str, Any]] = []
    response_row_counts: Counter[int] = Counter()
    response_paths: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    sample_response: Any = None
    requests_made = 0
    successes = 0
    started = time.time()

    print(json.dumps({"seed_points": len(seeds), "workers": WORKERS, "max_requests": MAX_REQUESTS}, ensure_ascii=False), flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while queue and requests_made < MAX_REQUESTS:
            batch: list[tuple[float, float, str]] = []
            while queue and len(batch) < WORKERS * 3 and requests_made + len(batch) < MAX_REQUESTS:
                item = queue.popleft()
                ck = coord_key(item[0], item[1])
                if ck in queried:
                    continue
                queried.add(ck)
                batch.append(item)
            if not batch:
                continue

            futures = [pool.submit(fetch_one, item) for item in batch]
            for future in as_completed(futures):
                result = future.result()
                requests_made += 1
                rows = result.pop("rows", [])
                response_obj = result.pop("response", None)
                if result.get("status") == 200:
                    successes += 1
                    if sample_response is None and rows:
                        sample_response = response_obj
                else:
                    errors[str(result.get("error") or result.get("status"))[:300]] += 1

                response_row_counts[len(rows)] += 1
                if result.get("row_path"):
                    response_paths[str(result["row_path"])] += 1

                new_stores = 0
                new_coords = 0
                for row in rows:
                    skey = store_key(row)
                    if skey not in stores:
                        stores[skey] = row
                        store_meta[skey] = {
                            "source": result.get("source"),
                            "query_lat": result.get("lat"),
                            "query_lon": result.get("lon"),
                        }
                        new_stores += 1
                    coord = get_store_coord(row)
                    if coord is not None:
                        ck = coord_key(coord[0], coord[1])
                        if ck not in queued and ck not in queried:
                            queue.append((coord[0], coord[1], f"store:{skey}"))
                            queued.add(ck)
                            new_coords += 1

                query_log.append(
                    {
                        "query_lat": result.get("lat"),
                        "query_lon": result.get("lon"),
                        "source": result.get("source"),
                        "status": result.get("status"),
                        "row_count": len(rows),
                        "new_store_count": new_stores,
                        "new_coordinate_count": new_coords,
                        "row_path": result.get("row_path"),
                        "elapsed": result.get("elapsed"),
                        "error": result.get("error"),
                    }
                )

            if requests_made % 200 < len(batch):
                print(
                    json.dumps(
                        {
                            "requests": requests_made,
                            "successes": successes,
                            "unique_stores": len(stores),
                            "queue": len(queue),
                            "elapsed_s": round(time.time() - started, 1),
                            "row_counts": response_row_counts.most_common(5),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    fields = write_store_csv(stores, store_meta)
    with (OUT_DIR / "query_log.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "query_lat",
            "query_lon",
            "source",
            "status",
            "row_count",
            "new_store_count",
            "new_coordinate_count",
            "row_path",
            "elapsed",
            "error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(query_log)

    summary = {
        "api_url": API_URL,
        "seed_file": str(SEED_FILE),
        "seed_points": len(seeds),
        "workers": WORKERS,
        "max_requests": MAX_REQUESTS,
        "requests_made": requests_made,
        "successful_requests": successes,
        "unique_stores": len(stores),
        "remaining_queue": len(queue),
        "queried_coordinates": len(queried),
        "queued_coordinates": len(queued),
        "elapsed_seconds": round(time.time() - started, 1),
        "response_row_counts": dict(response_row_counts),
        "response_paths": dict(response_paths),
        "errors": dict(errors),
        "csv_fields": fields,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "stores_raw.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "stores": [
                    {"__store_key": key, "__meta": store_meta[key], **row}
                    for key, row in stores.items()
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if sample_response is not None:
        (OUT_DIR / "sample_response.json").write_text(
            json.dumps(sample_response, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not stores:
        raise SystemExit("No stores were returned by the public endpoint")


if __name__ == "__main__":
    main()
