#!/usr/bin/env python3
"""Crawl the public LBX nearby-store endpoint and build a nationwide deduplicated dataset.

Method:
1) Query a 1-degree China-wide seed grid (every mainland point is <~80 km from a seed).
2) Recursively query every newly discovered store coordinate (10-nearest-neighbour graph walk).
3) Add targeted dense-cell samples and walk newly discovered records again.

The endpoint is public and used by an LBX H5 page. Requests use modest concurrency,
retry/backoff, and checkpoint output. The result is an independently collected public
snapshot, not an official corporate export.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

URL = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
OUT = Path("nationwide_crawl_output")
OUT.mkdir(exist_ok=True)
MAX_WORKERS = int(os.getenv("LBX_WORKERS", "10"))
REQUEST_TIMEOUT = (8, 22)
MAX_RETRIES = 4
CHECKPOINT_EVERY = 500
SOURCE_PAGE = "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4"

_tls = threading.local()


def session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Referer": SOURCE_PAGE,
        })
        _tls.session = s
    return s


def finite_coord(value: Any, low: float, high: float) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or x < low or x > high or x == 0:
        return None
    return x


def store_coord(store: dict[str, Any]) -> tuple[float, float] | None:
    lat = finite_coord(store.get("latGd") or store.get("lat"), 15, 56)
    lon = finite_coord(store.get("lngGd") or store.get("lng"), 70, 140)
    if lat is None or lon is None:
        return None
    return round(lat, 7), round(lon, 7)


def store_key(store: dict[str, Any]) -> str:
    for field in ("shop_id", "org_code", "sap_id"):
        value = str(store.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    coord = store_coord(store)
    return "fallback:" + "|".join([
        str(store.get("deptName") or store.get("org_name") or "").strip(),
        str(coord or ""),
        str(store.get("deptAddr") or "").strip(),
    ])


def extract_rows(obj: Any) -> list[dict[str, Any]]:
    try:
        rows = obj["data"]["data"]
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
    except Exception:
        pass
    return []


def query_point(point: tuple[float, float], phase: str) -> dict[str, Any]:
    lat, lon = point
    params = {"Latitude": f"{lat:.7f}", "Longitude": f"{lon:.7f}"}
    last_error = None
    started = time.monotonic()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session().get(URL, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
            obj = response.json()
            rows = extract_rows(obj)
            # A successful no-data response is valid; top-level code is normally 1.
            inner = obj.get("data") if isinstance(obj, dict) else None
            inner_code = inner.get("code") if isinstance(inner, dict) else None
            if isinstance(obj, dict) and obj.get("code") == 1 and inner_code == 0:
                elapsed = round(time.monotonic() - started, 3)
                time.sleep(0.035 + random.random() * 0.04)
                distances = []
                for row in rows:
                    try:
                        distances.append(float(row.get("distance") or row.get("distanceGd") or 0))
                    except (TypeError, ValueError):
                        pass
                return {
                    "point": [lat, lon], "phase": phase, "ok": True,
                    "count": len(rows), "max_distance_km": max(distances or [0]),
                    "elapsed_s": elapsed, "rows": rows,
                }
            raise RuntimeError(f"Unexpected JSON: {json.dumps(obj, ensure_ascii=False)[:500]}")
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
            if attempt < MAX_RETRIES:
                time.sleep((0.5 * (2 ** (attempt - 1))) + random.random() * 0.3)
    return {
        "point": [lat, lon], "phase": phase, "ok": False,
        "count": 0, "max_distance_km": 0,
        "elapsed_s": round(time.monotonic() - started, 3), "error": last_error,
        "rows": [],
    }


class CrawlState:
    def __init__(self) -> None:
        self.stores: dict[str, dict[str, Any]] = {}
        self.queried: set[str] = set()
        self.query_summaries: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.phase_counts: Counter[str] = Counter()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.total_attempted = 0

    @staticmethod
    def point_key(point: tuple[float, float]) -> str:
        # ~1 metre coordinate dedupe.
        return f"{point[0]:.5f},{point[1]:.5f}"

    def add_store(self, row: dict[str, Any], phase: str, query_point_value: tuple[float, float]) -> bool:
        key = store_key(row)
        now = datetime.now(timezone.utc).isoformat()
        enriched = dict(row)
        enriched["_store_key"] = key
        enriched["_source_url"] = URL
        enriched["_source_page"] = SOURCE_PAGE
        enriched["_first_seen_phase"] = phase
        enriched["_first_seen_query_lat"] = query_point_value[0]
        enriched["_first_seen_query_lon"] = query_point_value[1]
        enriched["_crawled_at_utc"] = now
        if key not in self.stores:
            self.stores[key] = enriched
            return True
        # Prefer later nonblank values without overwriting existing populated values.
        current = self.stores[key]
        for k, v in enriched.items():
            if (current.get(k) is None or current.get(k) == "") and v not in (None, ""):
                current[k] = v
        return False

    def save_checkpoint(self, label: str) -> None:
        stores_sorted = sorted(
            self.stores.values(),
            key=lambda x: (str(x.get("city") or ""), str(x.get("deptName") or ""), str(x.get("shop_id") or "")),
        )
        (OUT / "stores.json").write_text(
            json.dumps(stores_sorted, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (OUT / "query_summaries.json").write_text(
            json.dumps(self.query_summaries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (OUT / "errors.json").write_text(
            json.dumps(self.errors, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        progress = {
            "label": label,
            "started_at_utc": self.started_at,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "store_count": len(self.stores),
            "query_count": len(self.queried),
            "total_attempted": self.total_attempted,
            "error_count": len(self.errors),
            "phase_counts": dict(self.phase_counts),
            "workers": MAX_WORKERS,
            "source_url": URL,
        }
        (OUT / "progress.json").write_text(
            json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        write_csv(OUT / "stores.csv", stores_sorted)
        print("CHECKPOINT", json.dumps(progress, ensure_ascii=False), flush=True)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    preferred = [
        "shop_id", "sap_id", "org_code", "deptName", "org_name", "parentName",
        "third_org_name", "city", "deptAddr", "phone", "contactPerson", "shopLabels",
        "sales_scan_name", "sales_scan_id", "is_close", "is_m_shop", "deptType",
        "summer_start_hours", "summer_closing_hours", "winter_start_hours", "winter_closing_hours",
        "shipStartTime", "shipEndTime", "lngGd", "latGd", "lngBd", "latBd", "lng", "lat",
        "companyCode", "pdeptId", "third_org_code", "_store_key", "_first_seen_phase",
        "_first_seen_query_lat", "_first_seen_query_lon", "_crawled_at_utc", "_source_url", "_source_page",
    ]
    extra = sorted({k for row in rows for k in row.keys()} - set(preferred))
    fields = preferred + extra
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def unique_unqueried(points: Iterable[tuple[float, float]], state: CrawlState) -> list[tuple[float, float]]:
    result = []
    local = set()
    for lat, lon in points:
        if not (15 <= lat <= 56 and 70 <= lon <= 140):
            continue
        point = (round(float(lat), 7), round(float(lon), 7))
        key = state.point_key(point)
        if key in state.queried or key in local:
            continue
        local.add(key)
        result.append(point)
    return result


def run_points(points: Iterable[tuple[float, float]], phase: str, state: CrawlState) -> list[dict[str, Any]]:
    points_list = unique_unqueried(points, state)
    if not points_list:
        return []
    print(f"PHASE {phase}: querying {len(points_list)} points with {MAX_WORKERS} workers", flush=True)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(query_point, p, phase): p for p in points_list}
        for future in as_completed(futures):
            point = futures[future]
            key = state.point_key(point)
            state.queried.add(key)
            state.total_attempted += 1
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = {"point": list(point), "phase": phase, "ok": False, "count": 0, "rows": [], "error": repr(exc)}
            rows = result.pop("rows", [])
            summary = dict(result)
            state.query_summaries.append(summary)
            state.phase_counts[phase] += 1
            if not summary.get("ok"):
                state.errors.append(summary)
            for row in rows:
                state.add_store(row, phase, point)
            results.append({**summary, "rows": rows})
            if state.total_attempted % CHECKPOINT_EVERY == 0:
                state.save_checkpoint(f"{phase}_{state.total_attempted}")
    state.save_checkpoint(f"{phase}_complete")
    return results


def china_grid(step: float = 1.0) -> list[tuple[float, float]]:
    points = []
    lat = 18.0
    while lat <= 54.0001:
        lon = 73.0
        while lon <= 135.0001:
            points.append((round(lat, 6), round(lon, 6)))
            lon += step
        lat += step
    return points


def walk_store_graph(state: CrawlState, phase_prefix: str, max_rounds: int = 80) -> None:
    for round_no in range(1, max_rounds + 1):
        frontier = []
        for store in list(state.stores.values()):
            coord = store_coord(store)
            if coord and state.point_key(coord) not in state.queried:
                frontier.append(coord)
        frontier = unique_unqueried(frontier, state)
        if not frontier:
            print(f"GRAPH {phase_prefix}: converged after {round_no - 1} rounds", flush=True)
            return
        before = len(state.stores)
        run_points(frontier, f"{phase_prefix}_round_{round_no}", state)
        added = len(state.stores) - before
        print(f"GRAPH {phase_prefix} round {round_no}: +{added}, total={len(state.stores)}", flush=True)
        if added == 0:
            return
    print(f"GRAPH {phase_prefix}: reached max rounds {max_rounds}", flush=True)


def dense_cell_points(state: CrawlState) -> list[tuple[float, float]]:
    # Four quadrant samples in every 0.1-degree cell containing >=6 stores,
    # plus centre samples for occupied neighbouring cells. This seeds possible
    # directed k-NN components that a pure graph walk might not reach.
    cells: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    for store in state.stores.values():
        coord = store_coord(store)
        if not coord:
            continue
        lat, lon = coord
        cells[(math.floor(lat * 10), math.floor(lon * 10))].append(coord)
    points: set[tuple[float, float]] = set()
    for (ilat, ilon), coords in cells.items():
        if len(coords) < 6:
            continue
        base_lat = ilat / 10.0
        base_lon = ilon / 10.0
        for a in (0.025, 0.075):
            for b in (0.025, 0.075):
                points.add((round(base_lat + a, 7), round(base_lon + b, 7)))
        # Sample immediate cells to reduce edge/boundary misses.
        for da, db in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            points.add((round((ilat + da) / 10.0 + 0.05, 7), round((ilon + db) / 10.0 + 0.05, 7)))
    return sorted(points)


def saturated_seed_refinement(seed_results: list[dict[str, Any]], state: CrawlState) -> None:
    # Refine only seed points whose response is near the endpoint cap and whose
    # 8th/10th neighbour is relatively close. This avoids excessive rural calls.
    level = []
    for result in seed_results:
        if result.get("ok") and int(result.get("count") or 0) >= 8 and float(result.get("max_distance_km") or 0) <= 35:
            lat, lon = result["point"]
            level.append((float(lat), float(lon), 1.0))
    for depth in range(1, 4):
        child_points = []
        child_steps: dict[str, float] = {}
        for lat, lon, parent_step in level:
            child_step = parent_step / 2.0
            offset = parent_step / 4.0
            for dlat in (-offset, offset):
                for dlon in (-offset, offset):
                    p = (round(lat + dlat, 7), round(lon + dlon, 7))
                    child_points.append(p)
                    child_steps[state.point_key(p)] = child_step
        if not child_points:
            return
        results = run_points(child_points, f"seed_refine_depth_{depth}", state)
        next_level = []
        for result in results:
            if result.get("ok") and int(result.get("count") or 0) >= 8 and float(result.get("max_distance_km") or 0) <= 25:
                lat, lon = result["point"]
                step = child_steps.get(state.point_key((float(lat), float(lon))), 1.0 / (2 ** depth))
                if step > 0.125:
                    next_level.append((float(lat), float(lon), step))
        level = next_level


def final_summary(state: CrawlState) -> None:
    rows = list(state.stores.values())
    city_counts = Counter(str(x.get("city") or "未标注") for x in rows)
    parent_counts = Counter(str(x.get("parentName") or "未标注") for x in rows)
    summary = {
        "started_at_utc": state.started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": URL,
        "source_page": SOURCE_PAGE,
        "method": "1-degree China seed grid + saturated-cell refinement + recursive store-coordinate graph walk + dense-cell sampling",
        "store_count": len(rows),
        "query_count": len(state.queried),
        "error_count": len(state.errors),
        "workers": MAX_WORKERS,
        "city_count": len([k for k in city_counts if k != "未标注"]),
        "top_cities": city_counts.most_common(50),
        "top_parent_companies": parent_counts.most_common(50),
        "field_names": sorted({k for row in rows for k in row}),
        "limitations": [
            "The public endpoint caps each coordinate response and ignores page/size parameters.",
            "The crawl uses spatial seeding and nearest-neighbour graph expansion; it is not an official database export.",
            "The endpoint appears to return currently queryable LBX-system outlets and may include affiliates, franchises or non-pharmacy service locations.",
            "Closed, offline, newly opened, or un-geocoded locations may be absent.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    state.save_checkpoint("final")
    print("FINAL", json.dumps({k: v for k, v in summary.items() if k not in {"top_cities", "top_parent_companies", "field_names"}}, ensure_ascii=False), flush=True)


def main() -> None:
    state = CrawlState()
    seed_results = run_points(china_grid(1.0), "china_seed_grid_1deg", state)
    saturated_seed_refinement(seed_results, state)
    walk_store_graph(state, "graph_walk_1")

    dense_points = dense_cell_points(state)
    print(f"DENSE CELL SAMPLES: {len(dense_points)}", flush=True)
    run_points(dense_points, "dense_cell_sampling", state)
    walk_store_graph(state, "graph_walk_2")

    # One second dense-cell pass catches cells that became dense only after walk 2.
    dense_points_2 = dense_cell_points(state)
    run_points(dense_points_2, "dense_cell_sampling_2", state)
    walk_store_graph(state, "graph_walk_3")
    final_summary(state)


if __name__ == "__main__":
    main()
