#!/usr/bin/env python3
"""Crawl LBX Pharmacy stores nationwide from LBX's public nearby-store endpoint.

The endpoint returns up to 10 nearby stores. Coverage is expanded in stages:
1) all province/prefecture/county administrative centers;
2) graph expansion by querying each newly discovered store coordinate;
3) eight offset points around administrative centers in active provinces;
4) another graph expansion;
5) a bounded city-grid supplement and final graph expansion.
"""
from __future__ import annotations

import csv
import json
import math
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
ADMIN_URL = "https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/xzqh_with_amap_coordinates.json"
OUT = Path("national_crawl_output")
OUT.mkdir(exist_ok=True)

MAX_WORKERS = 12
REQUESTS_PER_SECOND = 18.0
MAX_BFS_QUERIES = 24000
MAX_GRID_QUERIES = 16000
TIMEOUT_SECONDS = 25

_tls = threading.local()
_rate_lock = threading.Lock()
_next_request_time = 0.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.50",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
    "Origin": "https://yx.lbxcn.com",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=MAX_WORKERS * 2, pool_maxsize=MAX_WORKERS * 2, max_retries=0)
        s.mount("https://", adapter)
        _tls.session = s
    return s


def rate_limit() -> None:
    global _next_request_time
    interval = 1.0 / REQUESTS_PER_SECOND
    with _rate_lock:
        now = time.monotonic()
        wait = max(0.0, _next_request_time - now)
        _next_request_time = max(now, _next_request_time) + interval
    if wait:
        time.sleep(wait)


def coord_key(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def to_float(value: Any) -> float | None:
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except (TypeError, ValueError):
        pass
    return None


def query_endpoint(point: dict[str, Any]) -> dict[str, Any]:
    lat = float(point["lat"])
    lon = float(point["lon"])
    last_error = ""
    for attempt in range(1, 4):
        try:
            rate_limit()
            r = session().get(
                ENDPOINT,
                params={"Latitude": f"{lat:.8f}", "Longitude": f"{lon:.8f}"},
                timeout=TIMEOUT_SECONDS,
            )
            payload = r.json()
            rows = None
            if payload.get("code") == 1 and isinstance(payload.get("data"), dict):
                rows = payload["data"].get("data")
            if isinstance(rows, list):
                return {
                    "ok": True,
                    "rows": rows,
                    "status": r.status_code,
                    "point": point,
                    "attempt": attempt,
                }
            last_error = f"unexpected payload code={payload.get('code')} message={payload.get('message')}"
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
        if attempt < 3:
            time.sleep(0.3 * attempt + random.random() * 0.2)
    return {"ok": False, "rows": [], "point": point, "error": last_error}


def download_admin() -> list[dict[str, Any]]:
    r = requests.get(ADMIN_URL, timeout=60, headers={"User-Agent": HEADERS["User-Agent"]})
    r.raise_for_status()
    data = r.json()
    (OUT / "admin_hierarchy.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def flatten_admin(data: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    points: list[dict[str, Any]] = []
    city_to_province: dict[str, str] = {}

    def walk(node: dict[str, Any], province: str = "", prefecture: str = "") -> None:
        level = str(node.get("level") or "")
        name = str(node.get("name") or "")
        if level == "province":
            province = name
            if name in ("北京市", "天津市", "上海市", "重庆市"):
                city_to_province[name] = name
        elif level in ("prefecture", "city"):
            prefecture = name
            city_to_province[name] = province
        center = node.get("center") or {}
        lat = to_float(center.get("latitude"))
        lon = to_float(center.get("longitude"))
        if lat is not None and lon is not None:
            points.append({
                "lat": lat,
                "lon": lon,
                "stage": "admin_center",
                "admin_code": node.get("code"),
                "admin_name": name,
                "admin_level": level,
                "seed_province": province,
                "seed_prefecture": prefecture,
            })
        for child in node.get("children") or []:
            walk(child, province, prefecture)

    for province_node in data:
        walk(province_node)
    return points, city_to_province


def clean_key_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def store_key(row: dict[str, Any]) -> str:
    org_code = clean_key_text(row.get("org_code"))
    if org_code:
        return "org:" + org_code
    shop_id = clean_key_text(row.get("shop_id"))
    if shop_id:
        return "shop:" + shop_id
    sap_id = clean_key_text(row.get("sap_id"))
    if sap_id:
        return "sap:" + sap_id
    return "fallback:" + "|".join([
        clean_key_text(row.get("deptName") or row.get("org_name")),
        clean_key_text(row.get("deptAddr")),
        clean_key_text(row.get("latGd") or row.get("lat")),
        clean_key_text(row.get("lngGd") or row.get("lng")),
    ])


def infer_province(row: dict[str, Any], city_to_province: dict[str, str], seed_province: str = "") -> str:
    city = str(row.get("city") or "").strip()
    if city in city_to_province:
        return city_to_province[city]
    text = " ".join(str(row.get(k) or "") for k in ("parentName", "third_org_name", "deptAddr", "deptName"))
    aliases = {
        "北京": "北京市", "天津": "天津市", "上海": "上海市", "重庆": "重庆市",
        "河北": "河北省", "山西": "山西省", "辽宁": "辽宁省", "吉林": "吉林省", "黑龙江": "黑龙江省",
        "江苏": "江苏省", "浙江": "浙江省", "安徽": "安徽省", "福建": "福建省", "江西": "江西省",
        "山东": "山东省", "河南": "河南省", "湖北": "湖北省", "湖南": "湖南省", "广东": "广东省",
        "广西": "广西壮族自治区", "海南": "海南省", "四川": "四川省", "贵州": "贵州省", "云南": "云南省",
        "西藏": "西藏自治区", "陕西": "陕西省", "甘肃": "甘肃省", "青海": "青海省",
        "宁夏": "宁夏回族自治区", "新疆": "新疆维吾尔自治区", "内蒙古": "内蒙古自治区",
    }
    for token, province in aliases.items():
        if token in text:
            return province
    return seed_province


class CrawlState:
    def __init__(self, city_to_province: dict[str, str]) -> None:
        self.city_to_province = city_to_province
        self.stores: dict[str, dict[str, Any]] = {}
        self.queried_coords: set[str] = set()
        self.failures: list[dict[str, Any]] = []
        self.stage_stats: dict[str, Counter] = defaultdict(Counter)
        self.active_provinces: set[str] = set()
        self.started_at = now_iso()

    def ingest(self, rows: list[dict[str, Any]], point: dict[str, Any]) -> list[dict[str, Any]]:
        new_stores: list[dict[str, Any]] = []
        stage = str(point.get("stage") or "unknown")
        seed_province = str(point.get("seed_province") or "")
        if rows and seed_province:
            self.active_provinces.add(seed_province)
        for row0 in rows:
            if not isinstance(row0, dict):
                continue
            row = dict(row0)
            key = store_key(row)
            distance = to_float(row.get("distanceGd") or row.get("distance") or row.get("distanceBd"))
            if key not in self.stores:
                row["_store_key"] = key
                row["_province"] = infer_province(row, self.city_to_province, seed_province)
                row["_first_seen_stage"] = stage
                row["_first_seed_admin"] = point.get("admin_name") or ""
                row["_seen_count"] = 1
                row["_min_observed_distance_km"] = distance
                row["_crawl_source"] = ENDPOINT
                row["_crawl_time_utc"] = now_iso()
                self.stores[key] = row
                new_stores.append(row)
            else:
                existing = self.stores[key]
                existing["_seen_count"] = int(existing.get("_seen_count") or 0) + 1
                if distance is not None:
                    old = to_float(existing.get("_min_observed_distance_km"))
                    if old is None or distance < old:
                        existing["_min_observed_distance_km"] = distance
                for k, v in row.items():
                    if (existing.get(k) is None or existing.get(k) == "") and v not in (None, ""):
                        existing[k] = v
        return new_stores

    def checkpoint(self, label: str) -> None:
        summary = {
            "label": label,
            "started_at": self.started_at,
            "checkpoint_at": now_iso(),
            "unique_store_count": len(self.stores),
            "queried_coordinate_count": len(self.queried_coords),
            "failure_count": len(self.failures),
            "active_provinces": sorted(self.active_provinces),
            "stage_stats": {k: dict(v) for k, v in self.stage_stats.items()},
        }
        (OUT / "crawl_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        stores_sorted = sorted(
            self.stores.values(),
            key=lambda x: (str(x.get("_province") or ""), str(x.get("city") or ""), str(x.get("deptName") or ""), str(x.get("org_code") or "")),
        )
        (OUT / "stores.json").write_text(json.dumps(stores_sorted, ensure_ascii=False), encoding="utf-8")
        (OUT / "failures.json").write_text(json.dumps(self.failures[-5000:], ensure_ascii=False), encoding="utf-8")
        write_csv(stores_sorted, OUT / "stores.csv")
        print("CHECKPOINT", json.dumps(summary, ensure_ascii=False), flush=True)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    preferred = [
        "_store_key", "_province", "city", "deptName", "org_name", "deptAddr", "phone", "contactPerson",
        "latGd", "lngGd", "latBd", "lngBd", "parentName", "third_org_name", "third_org_code",
        "companyCode", "pdeptId", "org_code", "shop_id", "sap_id", "shopLabels", "sales_scan_name",
        "deptType", "is_close", "is_m_shop", "summer_start_hours", "summer_closing_hours",
        "winter_start_hours", "winter_closing_hours", "shipStartTime", "shipEndTime",
        "_first_seen_stage", "_first_seed_admin", "_seen_count", "_min_observed_distance_km",
        "_crawl_source", "_crawl_time_utc",
    ]
    keys: set[str] = set()
    for row in rows:
        keys.update(row.keys())
    fields = [k for k in preferred if k in keys] + sorted(keys - set(preferred))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_points(state: CrawlState, points: Iterable[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    todo: list[dict[str, Any]] = []
    for p0 in points:
        p = dict(p0)
        p["stage"] = stage
        lat = to_float(p.get("lat"))
        lon = to_float(p.get("lon"))
        if lat is None or lon is None or not (0 < lat < 60 and 70 < lon < 140):
            continue
        ck = coord_key(lat, lon)
        if ck in state.queried_coords:
            continue
        state.queried_coords.add(ck)
        p["lat"], p["lon"] = lat, lon
        todo.append(p)
    print(f"STAGE {stage}: querying {len(todo)} coordinates", flush=True)
    new_rows: list[dict[str, Any]] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(query_endpoint, p) for p in todo]
        for fut in as_completed(futures):
            result = fut.result()
            completed += 1
            rows = result.get("rows") or []
            point = result.get("point") or {}
            if result.get("ok"):
                state.stage_stats[stage]["success_queries"] += 1
                state.stage_stats[stage]["rows_returned"] += len(rows)
                if len(rows) >= 10:
                    state.stage_stats[stage]["full_queries"] += 1
                new_rows.extend(state.ingest(rows, point))
            else:
                state.stage_stats[stage]["failed_queries"] += 1
                if len(state.failures) < 5000:
                    state.failures.append({"stage": stage, "point": point, "error": result.get("error")})
            if completed % 500 == 0:
                print(f"PROGRESS {stage}: {completed}/{len(todo)}, stores={len(state.stores)}, failures={len(state.failures)}", flush=True)
    state.checkpoint(stage)
    return new_rows


def store_points(rows: Iterable[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    points = []
    for row in rows:
        lat = to_float(row.get("latGd") or row.get("lat"))
        lon = to_float(row.get("lngGd") or row.get("lng"))
        if lat is None or lon is None:
            continue
        points.append({
            "lat": lat,
            "lon": lon,
            "stage": stage,
            "seed_province": row.get("_province") or "",
            "admin_name": row.get("deptName") or "",
        })
    return points


def bfs_expand(state: CrawlState, initial_rows: Iterable[dict[str, Any]], label: str) -> None:
    queue = deque(store_points(initial_rows, label))
    total_scheduled = 0
    round_no = 0
    while queue and total_scheduled < MAX_BFS_QUERIES:
        round_no += 1
        batch: list[dict[str, Any]] = []
        while queue and len(batch) < 1200 and total_scheduled + len(batch) < MAX_BFS_QUERIES:
            batch.append(queue.popleft())
        new_rows = run_points(state, batch, f"{label}_r{round_no}")
        total_scheduled += len(batch)
        queue.extend(store_points(new_rows, label))
        print(f"BFS {label}: round={round_no}, scheduled={total_scheduled}, pending={len(queue)}, stores={len(state.stores)}", flush=True)
        if not new_rows and not queue:
            break


def offset_points(admin_points: list[dict[str, Any]], active_provinces: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in admin_points:
        if p.get("seed_province") not in active_provinces:
            continue
        if p.get("admin_level") not in ("county", "prefecture", "city"):
            continue
        lat = float(p["lat"])
        lon = float(p["lon"])
        # Ring radius roughly 18 km. Diagonals use 12.7 km per axis.
        dlat = 18.0 / 111.0
        dlon = 18.0 / max(30.0, 111.0 * math.cos(math.radians(lat)))
        dlat_diag = 12.7 / 111.0
        dlon_diag = 12.7 / max(30.0, 111.0 * math.cos(math.radians(lat)))
        offsets = [
            (dlat, 0), (-dlat, 0), (0, dlon), (0, -dlon),
            (dlat_diag, dlon_diag), (dlat_diag, -dlon_diag), (-dlat_diag, dlon_diag), (-dlat_diag, -dlon_diag),
        ]
        for dy, dx in offsets:
            q = dict(p)
            q["lat"] = lat + dy
            q["lon"] = lon + dx
            q["admin_name"] = f"{p.get('admin_name','')} offset"
            out.append(q)
    return out


def city_grid_points(state: CrawlState) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for row in state.stores.values():
        lat = to_float(row.get("latGd") or row.get("lat"))
        lon = to_float(row.get("lngGd") or row.get("lng"))
        if lat is None or lon is None:
            continue
        province = str(row.get("_province") or "")
        city = str(row.get("city") or province or "未知")
        groups[(province, city)].append((lat, lon))

    candidates: list[dict[str, Any]] = []
    group_specs = []
    for (province, city), coords in groups.items():
        lats = [x[0] for x in coords]
        lons = [x[1] for x in coords]
        minlat, maxlat = min(lats) - 0.08, max(lats) + 0.08
        minlon, maxlon = min(lons) - 0.10, max(lons) + 0.10
        area = max(0.001, (maxlat - minlat) * (maxlon - minlon))
        group_specs.append((len(coords), area, province, city, minlat, maxlat, minlon, maxlon))
    group_specs.sort(reverse=True)

    for count, area, province, city, minlat, maxlat, minlon, maxlon in group_specs:
        midlat = (minlat + maxlat) / 2
        step_lat = 6.0 / 111.0
        step_lon = 6.0 / max(30.0, 111.0 * math.cos(math.radians(midlat)))
        nlat = max(1, math.ceil((maxlat - minlat) / step_lat))
        nlon = max(1, math.ceil((maxlon - minlon) / step_lon))
        total = nlat * nlon
        if total > 900:
            scale = math.sqrt(total / 900)
            step_lat *= scale
            step_lon *= scale
            nlat = max(1, math.ceil((maxlat - minlat) / step_lat))
            nlon = max(1, math.ceil((maxlon - minlon) / step_lon))
        for iy in range(nlat + 1):
            lat = minlat + iy * step_lat
            if lat > maxlat + 1e-9:
                break
            for ix in range(nlon + 1):
                lon = minlon + ix * step_lon
                if lon > maxlon + 1e-9:
                    break
                candidates.append({
                    "lat": lat, "lon": lon, "stage": "city_grid",
                    "seed_province": province, "admin_name": city,
                })
                if len(candidates) >= MAX_GRID_QUERIES:
                    return candidates
    return candidates


def main() -> None:
    print("START", now_iso(), flush=True)
    admin_data = download_admin()
    admin_points, city_to_province = flatten_admin(admin_data)
    print(f"ADMIN points={len(admin_points)}", flush=True)
    state = CrawlState(city_to_province)

    new_rows = run_points(state, admin_points, "admin_center")
    bfs_expand(state, new_rows, "bfs_after_admin")

    offsets = offset_points(admin_points, state.active_provinces)
    print(f"OFFSET active_provinces={len(state.active_provinces)} points={len(offsets)}", flush=True)
    new_rows = run_points(state, offsets, "admin_offset_18km")
    bfs_expand(state, new_rows, "bfs_after_offsets")

    grid = city_grid_points(state)
    print(f"CITY GRID points={len(grid)}", flush=True)
    new_rows = run_points(state, grid, "city_grid_6km")
    bfs_expand(state, new_rows, "bfs_after_grid")

    state.checkpoint("complete")
    print(f"COMPLETE stores={len(state.stores)} queries={len(state.queried_coords)} failures={len(state.failures)}", flush=True)


if __name__ == "__main__":
    main()
