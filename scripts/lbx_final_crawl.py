#!/usr/bin/env python3
"""Nationwide crawl of public LBX Pharmacy nearby-store endpoint.

The endpoint is a public consumer-facing locator and returns at most 10 nearby
stores per coordinate. Coverage is expanded using administrative seeds, a
coarse mainland lattice, graph traversal from every discovered store, and
adaptive cells around discovered clusters. No authentication, CAPTCHA solving,
or internal-system access is used.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import re
import signal
import sys
import threading
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
CITY_LIST_URL = "https://www.amap.com/service/cityList?version=1"
OUT = Path(os.environ.get("LBX_OUTPUT_DIR", "lbx_final_output"))
OUT.mkdir(parents=True, exist_ok=True)

WORKERS = int(os.environ.get("LBX_WORKERS", "14"))
MAX_QUERIES = int(os.environ.get("LBX_MAX_QUERIES", "48000"))
REQUEST_TIMEOUT = float(os.environ.get("LBX_TIMEOUT", "15"))
MAINLAND_STEP = float(os.environ.get("LBX_MAINLAND_STEP", "1.0"))
CHECKPOINT_EVERY = int(os.environ.get("LBX_CHECKPOINT_EVERY", "1000"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# A broad mainland envelope. Administrative seeds and adaptive traversal do the
# detailed work; this lattice is only for isolated-cluster discovery.
MAINLAND_BBOX = (73.5, 135.1, 18.0, 53.8)  # min_lon, max_lon, min_lat, max_lat

STOP_REQUESTED = False
THREAD_LOCAL = threading.local()
PRINT_LOCK = threading.Lock()


def log(message: str) -> None:
    with PRINT_LOCK:
        print(time.strftime("%Y-%m-%d %H:%M:%S"), message, flush=True)


def handle_signal(signum: int, _frame: Any) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    log(f"signal={signum}; requesting graceful stop")


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def session() -> requests.Session:
    sess = getattr(THREAD_LOCAL, "session", None)
    if sess is None:
        sess = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.45,
            status_forcelist=(408, 425, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=WORKERS * 2, pool_maxsize=WORKERS * 2)
        sess.mount("https://", adapter)
        sess.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://yx.lbxcn.com/",
                "Connection": "keep-alive",
            }
        )
        THREAD_LOCAL.session = sess
    return sess


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return re.sub(r"\s+", " ", str(value)).strip()


def to_float(value: Any) -> float | None:
    try:
        if value in (None, "", [], {}):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    try:
        if value in (None, "", [], {}):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def valid_coord(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and 15.0 <= lat <= 55.8 and 70.0 <= lon <= 137.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def normalize_store_key(store: dict[str, Any]) -> str:
    sid = clean_text(store.get("id") or store.get("store_id") or store.get("storeId"))
    if sid:
        return f"id:{sid}"
    number = clean_text(store.get("store_no") or store.get("storeNo") or store.get("store_code"))
    if number:
        return f"no:{number}"
    name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", clean_text(store.get("store_name") or store.get("storeName") or store.get("name"))).lower()
    address = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", clean_text(store.get("address") or store.get("store_address"))).lower()
    lat = to_float(store.get("latitude") or store.get("lat"))
    lon = to_float(store.get("longitude") or store.get("lon") or store.get("lng"))
    coord = f"{lat:.5f},{lon:.5f}" if valid_coord(lat, lon) else ""
    return f"fallback:{name}|{address}|{coord}"


def extract_store_list(obj: Any) -> list[dict[str, Any]]:
    """Find the most store-like list in a JSON response."""
    candidates: list[tuple[int, list[dict[str, Any]]]] = []

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(node, list):
            dicts = [item for item in node if isinstance(item, dict)]
            if dicts:
                score = 0
                sample = dicts[: min(5, len(dicts))]
                for item in sample:
                    keys = {str(k).lower() for k in item.keys()}
                    if any(k in keys for k in ("store_name", "storename", "store_no", "storeno", "store_id")):
                        score += 6
                    if any(k in keys for k in ("latitude", "longitude", "address", "tel")):
                        score += 2
                if score:
                    candidates.append((score * 1000 + len(dicts), dicts))
            for item in node[:20]:
                walk(item, depth + 1)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value, depth + 1)

    walk(obj)
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def collect_total_hints(obj: Any) -> list[int]:
    hints: list[int] = []
    keys = {"total", "count", "totalcount", "total_count", "storecount", "store_count", "allcount"}

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                low = str(k).lower()
                if low in keys or ("total" in low and "page" not in low):
                    number = to_int(v)
                    if number is not None and 10 < number < 100000:
                        hints.append(number)
                if isinstance(v, (dict, list)):
                    walk(v, depth + 1)
        elif isinstance(node, list):
            for item in node[:20]:
                walk(item, depth + 1)

    walk(obj)
    return hints


@dataclass(frozen=True)
class ProbePoint:
    lat: float
    lon: float
    stage: str

    @property
    def key(self) -> str:
        return f"{self.lat:.5f},{self.lon:.5f}"


def query_point(point: ProbePoint) -> dict[str, Any]:
    started = time.time()
    params = {"lat": f"{point.lat:.6f}", "lon": f"{point.lon:.6f}"}
    try:
        response = session().get(ENDPOINT, params=params, timeout=REQUEST_TIMEOUT)
        status = response.status_code
        response.raise_for_status()
        obj = response.json()
        stores = extract_store_list(obj)
        return {
            "point": point,
            "ok": True,
            "status": status,
            "elapsed": round(time.time() - started, 4),
            "stores": stores,
            "store_count": len(stores),
            "total_hints": collect_total_hints(obj),
            "response_keys": list(obj.keys()) if isinstance(obj, dict) else [],
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "point": point,
            "ok": False,
            "status": getattr(getattr(exc, "response", None), "status_code", None),
            "elapsed": round(time.time() - started, 4),
            "stores": [],
            "store_count": 0,
            "total_hints": [],
            "response_keys": [],
            "error": repr(exc)[:1000],
        }


class CrawlState:
    def __init__(self, admin_nodes: list[dict[str, Any]], admin_code_map: dict[str, dict[str, str]]) -> None:
        self.stores: dict[str, dict[str, Any]] = {}
        self.store_discovery: dict[str, dict[str, Any]] = {}
        self.probed: set[str] = set()
        self.probe_rows: list[dict[str, Any]] = []
        self.query_count = 0
        self.success_count = 0
        self.error_count = 0
        self.saturated_count = 0
        self.total_hints: Counter[int] = Counter()
        self.stage_queries: Counter[str] = Counter()
        self.stage_new: Counter[str] = Counter()
        self.response_key_counts: Counter[str] = Counter()
        self.admin_nodes = admin_nodes
        self.admin_code_map = admin_code_map
        self.admin_buckets: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for node in admin_nodes:
            lat = node.get("lat")
            lon = node.get("lon")
            if valid_coord(lat, lon):
                self.admin_buckets[(int(lat), int(lon))].append(node)
        self.batch_history: list[dict[str, Any]] = []
        self.started_at = time.time()
        self.last_checkpoint_query = 0

    def can_query(self) -> bool:
        return not STOP_REQUESTED and self.query_count < MAX_QUERIES

    def reserve_points(self, points: Iterable[ProbePoint]) -> list[ProbePoint]:
        accepted: list[ProbePoint] = []
        for point in points:
            if not self.can_query():
                break
            if not valid_coord(point.lat, point.lon):
                continue
            if point.key in self.probed:
                continue
            self.probed.add(point.key)
            accepted.append(point)
            self.query_count += 1
        return accepted

    def process_result(self, result: dict[str, Any]) -> list[str]:
        point: ProbePoint = result["point"]
        stage = point.stage
        self.stage_queries[stage] += 1
        if result["ok"]:
            self.success_count += 1
        else:
            self.error_count += 1
        count = result["store_count"]
        if count >= 10:
            self.saturated_count += 1
        for hint in result["total_hints"]:
            self.total_hints[hint] += 1
        for key in result.get("response_keys", []):
            self.response_key_counts[str(key)] += 1

        new_keys: list[str] = []
        distances: list[float] = []
        for raw in result["stores"]:
            if not isinstance(raw, dict):
                continue
            store = dict(raw)
            lat = to_float(store.get("latitude") or store.get("lat"))
            lon = to_float(store.get("longitude") or store.get("lon") or store.get("lng"))
            if valid_coord(lat, lon):
                store["_latitude_num"] = lat
                store["_longitude_num"] = lon
            distance = to_float(store.get("distance") or store.get("distance_m"))
            if distance is not None:
                distances.append(distance)
            key = normalize_store_key(store)
            if key not in self.stores:
                self.stores[key] = store
                self.store_discovery[key] = {
                    "stage": stage,
                    "probe_lat": point.lat,
                    "probe_lon": point.lon,
                    "discovered_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "dedup_key": key,
                }
                new_keys.append(key)
                self.stage_new[stage] += 1
            else:
                existing = self.stores[key]
                for field, value in store.items():
                    if existing.get(field) in (None, "", [], {}) and value not in (None, "", [], {}):
                        existing[field] = value

        self.probe_rows.append(
            {
                "stage": stage,
                "lat": point.lat,
                "lon": point.lon,
                "ok": result["ok"],
                "http_status": result.get("status"),
                "elapsed_s": result["elapsed"],
                "returned_stores": count,
                "new_stores": len(new_keys),
                "max_distance": max(distances) if distances else "",
                "min_distance": min(distances) if distances else "",
                "error": result["error"],
            }
        )
        return new_keys

    def nearest_admin(self, lat: float, lon: float) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for radius in (1, 2, 4, 8):
            candidates.clear()
            for by in range(int(lat) - radius, int(lat) + radius + 1):
                for bx in range(int(lon) - radius, int(lon) + radius + 1):
                    candidates.extend(self.admin_buckets.get((by, bx), []))
            if candidates:
                break
        if not candidates:
            return None
        return min(candidates, key=lambda node: haversine_m(lat, lon, node["lat"], node["lon"]))

    def checkpoint(self, force: bool = False) -> None:
        if not force and self.query_count - self.last_checkpoint_query < CHECKPOINT_EVERY:
            return
        self.last_checkpoint_query = self.query_count
        write_outputs(self, final=False)
        log(
            f"checkpoint queries={self.query_count} success={self.success_count} "
            f"errors={self.error_count} stores={len(self.stores)}"
        )


def fetch_admin_data() -> tuple[list[dict[str, Any]], dict[str, dict[str, str]], dict[str, Any]]:
    log("fetching AMap public city list for administrative seed coordinates")
    response = session().get(CITY_LIST_URL, timeout=30)
    response.raise_for_status()
    obj = response.json()
    raw_path = OUT / "amap_city_list.json"
    raw_path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    nodes: list[dict[str, Any]] = []
    code_map: dict[str, dict[str, str]] = {}
    seen: set[tuple[str, str, float, float]] = set()

    def walk(node: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(node, dict):
            name = clean_text(node.get("name") or node.get("label"))
            adcode = clean_text(node.get("adcode"))
            lon = to_float(node.get("x") or node.get("longitude") or node.get("lon"))
            lat = to_float(node.get("y") or node.get("latitude") or node.get("lat"))
            next_path = path
            if name and name not in path:
                next_path = (*path, name)
            if adcode and name:
                hierarchy = [p for p in next_path if p and p != "全国"]
                code_map[adcode] = {
                    "name": name,
                    "province": hierarchy[0] if hierarchy else name,
                    "city": hierarchy[1] if len(hierarchy) >= 2 else "",
                    "district": hierarchy[2] if len(hierarchy) >= 3 else "",
                }
            if valid_coord(lat, lon) and name:
                key = (adcode, name, round(lat, 5), round(lon, 5))
                if key not in seen:
                    seen.add(key)
                    hierarchy = [p for p in next_path if p and p != "全国"]
                    nodes.append(
                        {
                            "name": name,
                            "adcode": adcode,
                            "lat": lat,
                            "lon": lon,
                            "path": hierarchy,
                            "province": hierarchy[0] if hierarchy else name,
                            "city": hierarchy[1] if len(hierarchy) >= 2 else "",
                            "district": hierarchy[2] if len(hierarchy) >= 3 else "",
                        }
                    )
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value, next_path)
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(obj)
    by_coord: dict[tuple[int, int], dict[str, Any]] = {}
    for node in nodes:
        key = (round(node["lat"] * 10000), round(node["lon"] * 10000))
        old = by_coord.get(key)
        if old is None or len(node.get("path", [])) > len(old.get("path", [])):
            by_coord[key] = node
    nodes = list(by_coord.values())
    log(f"administrative nodes={len(nodes)} code_map={len(code_map)}")
    return nodes, code_map, obj


def mainland_lattice(step: float) -> list[ProbePoint]:
    min_lon, max_lon, min_lat, max_lat = MAINLAND_BBOX
    points: list[ProbePoint] = []
    lat = min_lat
    row = 0
    while lat <= max_lat + 1e-9:
        lon = min_lon + (step / 2 if row % 2 else 0.0)
        while lon <= max_lon + 1e-9:
            if not (lon < 78 and lat < 27) and not (lon > 128 and lat < 30):
                points.append(ProbePoint(round(lat, 6), round(lon, 6), "mainland_lattice"))
            lon += step
        lat += step
        row += 1
    return points


def admin_seed_points(nodes: list[dict[str, Any]]) -> list[ProbePoint]:
    points: list[ProbePoint] = []
    for node in nodes:
        lat = node["lat"]
        lon = node["lon"]
        points.append(ProbePoint(lat, lon, "admin_center"))
        adcode = clean_text(node.get("adcode"))
        if adcode and (adcode.endswith("0000") or (adcode.endswith("00") and not adcode.endswith("0000"))):
            delta = 0.12 if adcode.endswith("0000") else 0.075
            coslat = max(0.35, math.cos(math.radians(lat)))
            dlon = delta / coslat
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                points.append(ProbePoint(lat + dy * delta, lon + dx * dlon, "admin_offset"))
    return points


def run_points(state: CrawlState, points: Iterable[ProbePoint], batch_label: str) -> list[str]:
    accepted = state.reserve_points(points)
    if not accepted:
        return []
    before = len(state.stores)
    log(f"stage={batch_label} probes={len(accepted)} stores_before={before} queries_reserved={state.query_count}")
    new_keys: list[str] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(query_point, point): point for point in accepted}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            new_keys.extend(state.process_result(result))
            if index % 500 == 0:
                log(
                    f"stage={batch_label} completed={index}/{len(accepted)} "
                    f"stores={len(state.stores)} errors={state.error_count}"
                )
                state.checkpoint()
            if STOP_REQUESTED:
                break
    after = len(state.stores)
    state.batch_history.append(
        {
            "stage": batch_label,
            "probes": len(accepted),
            "stores_before": before,
            "stores_after": after,
            "new_stores": after - before,
            "query_count": state.query_count,
        }
    )
    state.checkpoint(force=True)
    log(f"stage={batch_label} complete new_stores={after - before} stores={after}")
    return new_keys


def store_coordinate_points(state: CrawlState, keys: Iterable[str], stage: str) -> list[ProbePoint]:
    points: list[ProbePoint] = []
    for key in keys:
        store = state.stores.get(key, {})
        lat = to_float(store.get("_latitude_num") or store.get("latitude") or store.get("lat"))
        lon = to_float(store.get("_longitude_num") or store.get("longitude") or store.get("lon") or store.get("lng"))
        if valid_coord(lat, lon):
            points.append(ProbePoint(lat, lon, stage))
    return points


def crawl_store_graph(state: CrawlState, initial_keys: Iterable[str], label: str) -> int:
    queue: deque[str] = deque(initial_keys)
    enqueued: set[str] = set(initial_keys)
    total_new = 0
    round_no = 0
    while queue and state.can_query() and not STOP_REQUESTED:
        round_no += 1
        keys: list[str] = []
        while queue and len(keys) < 1400:
            keys.append(queue.popleft())
        new_keys = run_points(state, store_coordinate_points(state, keys, f"{label}_store_bfs"), f"{label}_bfs_{round_no}")
        total_new += len(new_keys)
        for key in new_keys:
            if key not in enqueued:
                enqueued.add(key)
                queue.append(key)
    return total_new


def cluster_frontier_points(state: CrawlState, cell: float = 0.05) -> list[ProbePoint]:
    occupied: Counter[tuple[int, int]] = Counter()
    for store in state.stores.values():
        lat = to_float(store.get("_latitude_num") or store.get("latitude") or store.get("lat"))
        lon = to_float(store.get("_longitude_num") or store.get("longitude") or store.get("lon") or store.get("lng"))
        if valid_coord(lat, lon):
            occupied[(math.floor(lat / cell), math.floor(lon / cell))] += 1
    core_cells = set(occupied)
    all_cells: set[tuple[int, int]] = set(core_cells)
    for cy, cx in core_cells:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                all_cells.add((cy + dy, cx + dx))
    neighbor_cells = all_cells - core_cells
    rng = random.Random(20260907 + round(cell * 10000))
    core_order = list(core_cells)
    neighbor_order = list(neighbor_cells)
    rng.shuffle(core_order)
    rng.shuffle(neighbor_order)
    ordered = core_order + neighbor_order
    points = [
        ProbePoint((cy + 0.5) * cell, (cx + 0.5) * cell, "cluster_frontier")
        for cy, cx in ordered
    ]
    log(
        f"cluster frontier cells={len(points)} occupied_cells={len(core_cells)} "
        f"neighbor_cells={len(neighbor_cells)} cell={cell}"
    )
    return points


def dense_subcell_points(state: CrawlState, coarse: float = 0.05, fine: float = 0.0125, cap: int = 10000) -> list[ProbePoint]:
    occupied: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    for store in state.stores.values():
        lat = to_float(store.get("_latitude_num") or store.get("latitude") or store.get("lat"))
        lon = to_float(store.get("_longitude_num") or store.get("longitude") or store.get("lon") or store.get("lng"))
        if valid_coord(lat, lon):
            occupied[(math.floor(lat / coarse), math.floor(lon / coarse))].append((lat, lon))
    dense = sorted(occupied.items(), key=lambda item: (-len(item[1]), item[0]))
    points: list[ProbePoint] = []
    for (cy, cx), stores in dense:
        if len(stores) < 5:
            break
        lat0 = cy * coarse
        lon0 = cx * coarse
        steps = max(1, round(coarse / fine))
        for iy in range(steps):
            for ix in range(steps):
                points.append(ProbePoint(lat0 + (iy + 0.5) * fine, lon0 + (ix + 0.5) * fine, "dense_subcell"))
                if len(points) >= cap:
                    log(f"dense subcell cap reached={cap}")
                    return points
    log(f"dense subcell points={len(points)} dense_cells={sum(1 for v in occupied.values() if len(v) >= 5)}")
    return points


def map_admin_fields(state: CrawlState, store: dict[str, Any]) -> dict[str, str]:
    result = {"province": "", "city": "", "district": "", "admin_match_method": ""}
    explicit_candidates = {
        "province": ("province_name", "provinceName", "province"),
        "city": ("city_name", "cityName", "city"),
        "district": ("area_name", "areaName", "district_name", "districtName", "district", "area"),
    }
    for target, keys in explicit_candidates.items():
        for key in keys:
            value = clean_text(store.get(key))
            if value and not value.isdigit():
                result[target] = value
                break
    if any(result[k] for k in ("province", "city", "district")):
        result["admin_match_method"] = "endpoint_name"

    id_fields = {
        "province": ("province_id", "provinceId"),
        "city": ("city_id", "cityId"),
        "district": ("area_id", "areaId", "district_id", "districtId"),
    }
    mapped_any = False
    for target, keys in id_fields.items():
        for key in keys:
            raw = clean_text(store.get(key))
            digits = re.sub(r"\D", "", raw)
            if len(digits) == 6 and digits in state.admin_code_map:
                mapped = state.admin_code_map[digits]
                if target == "province":
                    result["province"] = result["province"] or mapped.get("province", "") or mapped.get("name", "")
                elif target == "city":
                    result["province"] = result["province"] or mapped.get("province", "")
                    result["city"] = result["city"] or mapped.get("city", "") or mapped.get("name", "")
                else:
                    result["province"] = result["province"] or mapped.get("province", "")
                    result["city"] = result["city"] or mapped.get("city", "")
                    result["district"] = result["district"] or mapped.get("district", "") or mapped.get("name", "")
                mapped_any = True
                break
    if mapped_any:
        result["admin_match_method"] = "adcode"

    if not result["province"] or not result["city"]:
        lat = to_float(store.get("_latitude_num") or store.get("latitude") or store.get("lat"))
        lon = to_float(store.get("_longitude_num") or store.get("longitude") or store.get("lon") or store.get("lng"))
        if valid_coord(lat, lon):
            node = state.nearest_admin(lat, lon)
            if node:
                result["province"] = result["province"] or clean_text(node.get("province"))
                result["city"] = result["city"] or clean_text(node.get("city"))
                result["district"] = result["district"] or clean_text(node.get("district") or node.get("name"))
                if not result["admin_match_method"]:
                    result["admin_match_method"] = "nearest_admin_center_inferred"
    return result


def standard_row(state: CrawlState, key: str, store: dict[str, Any], seq: int) -> dict[str, Any]:
    discovery = state.store_discovery.get(key, {})
    admin = map_admin_fields(state, store)
    lat = to_float(store.get("_latitude_num") or store.get("latitude") or store.get("lat"))
    lon = to_float(store.get("_longitude_num") or store.get("longitude") or store.get("lon") or store.get("lng"))
    label = store.get("store_label") or store.get("storeLabel") or store.get("store_label_type")
    row = {
        "seq": seq,
        "id": clean_text(store.get("id") or store.get("store_id") or store.get("storeId")),
        "store_no": clean_text(store.get("store_no") or store.get("storeNo") or store.get("store_code")),
        "store_name": clean_text(store.get("store_name") or store.get("storeName") or store.get("name")),
        "province": admin["province"],
        "city": admin["city"],
        "district": admin["district"],
        "address": clean_text(store.get("address") or store.get("store_address") or store.get("storeAddress")),
        "tel": clean_text(store.get("tel") or store.get("telephone") or store.get("phone")),
        "start_hour": clean_text(store.get("start_hour") or store.get("startHour") or store.get("business_start")),
        "end_hour": clean_text(store.get("end_hour") or store.get("endHour") or store.get("business_end")),
        "longitude": lon if lon is not None else "",
        "latitude": lat if lat is not None else "",
        "distance_m": to_float(store.get("distance") or store.get("distance_m")) or "",
        "store_label": clean_text(label),
        "store_label_type": clean_text(store.get("store_label_type") or store.get("storeLabelType")),
        "is_night_work": clean_text(store.get("is_night_work") or store.get("isNightWork")),
        "is_medicare": clean_text(store.get("is_medicare") or store.get("isMedicare")),
        "province_id": clean_text(store.get("province_id") or store.get("provinceId")),
        "city_id": clean_text(store.get("city_id") or store.get("cityId")),
        "area_id": clean_text(store.get("area_id") or store.get("areaId") or store.get("district_id")),
        "cbs_poi_id": clean_text(store.get("cbs_poi_id") or store.get("cbsPoiId")),
        "jd_shop_id": clean_text(store.get("jd_shop_id") or store.get("jdShopId")),
        "img_id": clean_text(store.get("img_id") or store.get("imgId")),
        "is_enable": clean_text(store.get("is_enable") or store.get("isEnable")),
        "stock_panel_flag": clean_text(store.get("stock_panel_flag") or store.get("stockPanelFlag")),
        "admin_match_method": admin["admin_match_method"],
        "discovery_stage": discovery.get("stage", ""),
        "probe_lat": discovery.get("probe_lat", ""),
        "probe_lon": discovery.get("probe_lon", ""),
        "dedup_key": key,
        "source": "老百姓公开附近门店接口",
        "source_url": ENDPOINT,
        "crawl_time_utc": discovery.get("discovered_at_utc", ""),
        "raw_json": json.dumps({k: v for k, v in store.items() if not str(k).startswith("_")}, ensure_ascii=False, separators=(",", ":")),
    }
    return row


CSV_FIELDS = [
    "seq", "id", "store_no", "store_name", "province", "city", "district", "address", "tel",
    "start_hour", "end_hour", "longitude", "latitude", "distance_m", "store_label", "store_label_type",
    "is_night_work", "is_medicare", "province_id", "city_id", "area_id", "cbs_poi_id", "jd_shop_id",
    "img_id", "is_enable", "stock_panel_flag", "admin_match_method", "discovery_stage", "probe_lat", "probe_lon",
    "dedup_key", "source", "source_url", "crawl_time_utc", "raw_json",
]


def write_outputs(state: CrawlState, final: bool) -> None:
    rows = [standard_row(state, key, store, index) for index, (key, store) in enumerate(state.stores.items(), 1)]
    rows.sort(key=lambda r: (r["province"], r["city"], r["district"], r["store_name"], r["id"]))
    for index, row in enumerate(rows, 1):
        row["seq"] = index

    csv_path = OUT / "lbx_stores.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    json_path = OUT / "lbx_stores.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    probe_fields = [
        "stage", "lat", "lon", "ok", "http_status", "elapsed_s", "returned_stores", "new_stores",
        "max_distance", "min_distance", "error",
    ]
    with (OUT / "lbx_probe_stats.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=probe_fields)
        writer.writeheader()
        writer.writerows(state.probe_rows)

    by_province = Counter(clean_text(row["province"]) or "未识别" for row in rows)
    by_city = Counter((clean_text(row["province"]) or "未识别", clean_text(row["city"]) or "未识别") for row in rows)
    errors = Counter(row["error"] for row in state.probe_rows if row.get("error"))
    total_hint = state.total_hints.most_common(1)[0][0] if state.total_hints else None
    total_hint_frequency = state.total_hints.most_common(1)[0][1] if state.total_hints else 0
    last_batches = state.batch_history[-8:]
    summary = {
        "final": final,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - state.started_at, 2),
        "endpoint": ENDPOINT,
        "unique_store_count": len(rows),
        "query_count_reserved": state.query_count,
        "successful_queries": state.success_count,
        "failed_queries": state.error_count,
        "saturated_query_count_returned_10": state.saturated_count,
        "saturation_ratio": round(state.saturated_count / state.success_count, 6) if state.success_count else 0,
        "api_total_hint_mode": total_hint,
        "api_total_hint_frequency": total_hint_frequency,
        "api_total_hints": dict(state.total_hints),
        "stage_queries": dict(state.stage_queries),
        "stage_new_stores": dict(state.stage_new),
        "response_key_counts": dict(state.response_key_counts),
        "batch_history": state.batch_history,
        "last_batches": last_batches,
        "new_stores_last_3_batches": sum(batch.get("new_stores", 0) for batch in state.batch_history[-3:]),
        "new_stores_last_batch": state.batch_history[-1].get("new_stores", 0) if state.batch_history else None,
        "province_counts": dict(by_province.most_common()),
        "city_counts": [
            {"province": province, "city": city, "store_count": count}
            for (province, city), count in by_city.most_common()
        ],
        "top_errors": [{"error": err, "count": count} for err, count in errors.most_common(20)],
        "coverage_method": [
            "AMap public administrative-center seeds",
            f"mainland staggered lattice step={MAINLAND_STEP} degrees",
            "iterative traversal from every newly discovered store coordinate",
            "adaptive frontier cells around all occupied store cells",
            "dense subcell probes for high-density clusters",
            "deduplication by store id, then store number, then normalized identity",
        ],
        "limitations": [
            "The public locator returns at most 10 nearby stores per coordinate.",
            "Completeness is assessed by spatial convergence and any API total hint; it is not an official corporate export.",
            "Administrative names may be inferred from the nearest public administrative-center coordinate when the endpoint exposes only IDs.",
        ],
    }
    (OUT / "lbx_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    with (OUT / "README.txt").open("w", encoding="utf-8") as f:
        f.write("老百姓大药房全国门店公开接口抓取结果\n")
        f.write(f"生成时间(UTC): {summary['generated_at_utc']}\n")
        f.write(f"唯一门店数: {summary['unique_store_count']}\n")
        f.write(f"查询点数: {summary['query_count_reserved']}\n")
        f.write(f"成功/失败: {summary['successful_queries']}/{summary['failed_queries']}\n")
        f.write(f"API总数提示: {summary['api_total_hint_mode']} (出现{summary['api_total_hint_frequency']}次)\n")
        f.write(f"最近3批新增: {summary['new_stores_last_3_batches']}\n")
        f.write("数据源: 老百姓公开附近门店接口\n")
        f.write("说明: 该接口单点最多返回10家，结果通过全国空间遍历、门店图遍历和自适应加密获得；非公司官方导出。\n")


def main() -> int:
    random.seed(20260907)
    log(
        f"start workers={WORKERS} max_queries={MAX_QUERIES} "
        f"mainland_step={MAINLAND_STEP} output={OUT}"
    )
    try:
        admin_nodes, code_map, _ = fetch_admin_data()
    except Exception as exc:  # noqa: BLE001
        log(f"admin city list failed: {exc!r}; continuing with lattice only")
        admin_nodes, code_map = [], {}

    state = CrawlState(admin_nodes, code_map)
    try:
        run_points(state, mainland_lattice(MAINLAND_STEP), "bootstrap_lattice")
        initial_keys = list(state.stores.keys())
        crawl_store_graph(state, initial_keys, "lattice")

        run_points(state, admin_seed_points(admin_nodes), "bootstrap_admin")
        unqueried_store_keys = [
            key for key, store in state.stores.items()
            if ProbePoint(
                to_float(store.get("_latitude_num") or store.get("latitude") or 0) or 0,
                to_float(store.get("_longitude_num") or store.get("longitude") or 0) or 0,
                "x",
            ).key not in state.probed
        ]
        crawl_store_graph(state, unqueried_store_keys, "admin")

        frontier_new = run_points(state, cluster_frontier_points(state, 0.05), "cluster_frontier")
        crawl_store_graph(state, frontier_new, "frontier")

        if state.can_query() and not STOP_REQUESTED:
            dense_new = run_points(state, dense_subcell_points(state, cap=10000), "dense_subcells")
            crawl_store_graph(state, dense_new, "dense")

        if state.can_query() and not STOP_REQUESTED:
            final_new = run_points(state, cluster_frontier_points(state, 0.08), "final_frontier")
            crawl_store_graph(state, final_new, "final")
    except Exception as exc:  # noqa: BLE001
        log(f"crawl exception: {exc!r}")
        (OUT / "crawl_exception.txt").write_text(repr(exc), encoding="utf-8")
    finally:
        write_outputs(state, final=True)

    summary = json.loads((OUT / "lbx_summary.json").read_text(encoding="utf-8"))
    log(
        f"done stores={summary['unique_store_count']} queries={summary['query_count_reserved']} "
        f"failures={summary['failed_queries']} api_total_hint={summary['api_total_hint_mode']} "
        f"last3_new={summary['new_stores_last_3_batches']}"
    )
    return 0 if summary["unique_store_count"] > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
