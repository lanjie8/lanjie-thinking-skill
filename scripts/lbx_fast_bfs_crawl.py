#!/usr/bin/env python3
"""Accelerated crawler for the public LBX nearby-store endpoint.

Seeds the published 18 operating markets with a coarse grid, then traverses the
store nearest-neighbour graph by querying each newly discovered coordinate.
"""
from __future__ import annotations

import csv
import json
import os
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
OUT = Path("lbx_fast_bfs_output")
OUT.mkdir(exist_ok=True)
WORKERS = int(os.getenv("LBX_WORKERS", "32"))
BATCH = int(os.getenv("LBX_BATCH_SIZE", "800"))
MAX_REQUESTS = int(os.getenv("LBX_MAX_REQUESTS", "30000"))
MAX_SECONDS = int(os.getenv("LBX_MAX_SECONDS", "3300"))
SEED_STEP = float(os.getenv("LBX_SEED_STEP", "2.0"))

MARKETS = {
    "湖南": (24.4, 30.3, 108.6, 114.5), "江苏": (30.5, 35.3, 116.0, 122.1),
    "安徽": (29.2, 34.8, 114.7, 119.9), "甘肃": (32.4, 42.9, 92.0, 109.0),
    "陕西": (31.5, 39.7, 105.3, 111.5), "广西": (20.6, 26.6, 104.2, 112.3),
    "内蒙古": (37.2, 53.5, 97.0, 126.4), "天津": (38.4, 40.4, 116.5, 118.3),
    "湖北": (28.8, 33.4, 108.1, 116.4), "浙江": (26.8, 31.5, 117.8, 123.2),
    "山西": (34.3, 40.9, 110.0, 114.8), "河南": (31.2, 36.6, 110.1, 116.9),
    "山东": (34.1, 38.6, 114.6, 123.0), "上海": (30.5, 32.0, 120.7, 122.1),
    "宁夏": (35.0, 39.6, 104.1, 107.9), "贵州": (24.3, 29.5, 103.3, 109.8),
    "广东": (19.9, 25.8, 109.3, 117.6), "江西": (24.2, 30.3, 113.3, 118.8),
}
KEEP_FIELDS = [
    "org_code", "shop_id", "sap_id", "deptName", "org_name", "parentName",
    "third_org_name", "third_org_code", "city", "deptAddr", "phone", "latGd",
    "lngGd", "latBd", "lngBd", "lat", "lng", "shopLabels",
    "winter_start_hours", "winter_closing_hours", "summer_start_hours",
    "summer_closing_hours", "shipStartTime", "shipEndTime", "is_m_shop",
    "is_close", "deptType", "sales_scan_name", "sales_scan_id", "companyCode", "pdeptId",
]

_tls = threading.local()
_lock = threading.Lock()
_started = time.monotonic()
request_count = 0
error_count = 0


def get_session() -> requests.Session:
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
        })
        _tls.s = s
    return s


def rows_from(data: Any) -> list[dict[str, Any]]:
    try:
        rows = data["data"]["data"]
        return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    except Exception:
        return []


def query(point: tuple[float, float]) -> tuple[tuple[float, float], list[dict[str, Any]], str | None]:
    global request_count, error_count
    lat, lon = point
    with _lock:
        if request_count >= MAX_REQUESTS or time.monotonic() - _started >= MAX_SECONDS:
            return point, [], "limit"
        request_count += 1
    err = None
    for attempt in range(4):
        try:
            r = get_session().get(ENDPOINT, params={"Latitude": lat, "Longitude": lon}, timeout=(8, 30))
            if r.status_code == 200:
                data = r.json()
                return point, rows_from(data), None
            err = f"HTTP {r.status_code} {r.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            err = repr(exc)
        time.sleep(0.4 * (2 ** attempt) + random.random() * 0.2)
    with _lock:
        error_count += 1
    return point, [], err


def pkey(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        a, b = float(lat), float(lon)
        if 15 <= a <= 55 and 70 <= b <= 140:
            return round(a, 6), round(b, 6)
    except (TypeError, ValueError):
        pass
    return None


def skey(r: dict[str, Any]) -> str:
    for k in ("org_code", "shop_id"):
        v = str(r.get(k) or "").strip()
        if v and v not in {"0", "null", "None"}:
            return f"{k}:{v}"
    return "fallback:" + "|".join(str(r.get(k) or "").strip() for k in ("companyCode", "sap_id", "deptName", "deptAddr"))


def coord(r: dict[str, Any]) -> tuple[float, float] | None:
    for a, b in (("latGd", "lngGd"), ("lat", "lng"), ("latBd", "lngBd")):
        p = pkey(r.get(a), r.get(b))
        if p:
            return p
    return None


def merge(stores: dict[str, dict[str, Any]], r: dict[str, Any]) -> bool:
    key = skey(r)
    cleaned = {k: r.get(k, "") for k in KEEP_FIELDS}
    cleaned["source_endpoint"] = ENDPOINT
    if key not in stores:
        stores[key] = cleaned
        return True
    for k, v in cleaned.items():
        if stores[key].get(k) in (None, "") and v not in (None, ""):
            stores[key][k] = v
    return False


def seeds() -> list[tuple[float, float]]:
    result = set()
    for lat0, lat1, lon0, lon1 in MARKETS.values():
        lat = lat0
        while lat <= lat1 + 1e-9:
            lon = lon0
            while lon <= lon1 + 1e-9:
                result.add((round(lat, 6), round(lon, 6)))
                lon += SEED_STEP
            lat += SEED_STEP
        result.add((round((lat0 + lat1) / 2, 6), round((lon0 + lon1) / 2, 6)))
    return sorted(result)


def run(points: list[tuple[float, float]]):
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(query, p) for p in points]
        for fut in as_completed(futures):
            yield fut.result()


def checkpoint(stores, seen, queue, phase):
    payload = {
        "phase": phase, "time": datetime.now(timezone.utc).isoformat(),
        "stores": len(stores), "requests": request_count, "errors": error_count,
        "seen_points": len(seen), "queue": len(queue),
    }
    (OUT / "progress.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main():
    stores: dict[str, dict[str, Any]] = {}
    seen: set[tuple[float, float]] = set()
    queued: set[tuple[float, float]] = set()
    queue: deque[tuple[float, float]] = deque()

    seed_points = seeds()
    print(f"SEEDS {len(seed_points)} workers={WORKERS}", flush=True)
    for point, rows, err in run(seed_points):
        seen.add(point)
        for r in rows:
            if str(r.get("is_close", "0")) not in ("", "0"):
                continue
            if merge(stores, r):
                c = coord(r)
                if c and c not in seen and c not in queued:
                    queue.append(c); queued.add(c)
    checkpoint(stores, seen, queue, "seeds")

    wave = 0
    stable_zero_waves = 0
    while queue and request_count < MAX_REQUESTS and time.monotonic() - _started < MAX_SECONDS:
        wave += 1
        pts = []
        while queue and len(pts) < BATCH:
            p = queue.popleft()
            if p not in seen:
                pts.append(p)
        if not pts:
            continue
        before = len(stores)
        for point, rows, err in run(pts):
            seen.add(point)
            for r in rows:
                if str(r.get("is_close", "0")) not in ("", "0"):
                    continue
                if merge(stores, r):
                    c = coord(r)
                    if c and c not in seen and c not in queued:
                        queue.append(c); queued.add(c)
        added = len(stores) - before
        stable_zero_waves = stable_zero_waves + 1 if added == 0 else 0
        checkpoint(stores, seen, queue, f"wave-{wave}-added-{added}")
        # All queued coordinate nodes have been exhausted, so zero waves are not
        # needed for convergence; guard only protects against malformed duplicates.
        if stable_zero_waves >= 3 and not queue:
            break

    now = datetime.now(timezone.utc).isoformat()
    rows = sorted(stores.values(), key=lambda r: (str(r.get("third_org_name") or ""), str(r.get("city") or ""), str(r.get("parentName") or ""), str(r.get("deptName") or ""), str(r.get("org_code") or "")))
    for r in rows:
        r["crawl_time_utc"] = now
    (OUT / "stores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = KEEP_FIELDS + ["source_endpoint", "crawl_time_utc"]
    with (OUT / "stores.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    report = {
        "source": ENDPOINT, "crawl_time_utc": now, "published_markets": list(MARKETS),
        "active_unique_store_count": len(rows), "requests": request_count,
        "errors": error_count, "seen_points": len(seen), "remaining_queue": len(queue),
        "workers": WORKERS, "seed_step": SEED_STEP,
        "elapsed_seconds": round(time.monotonic() - _started, 1),
        "stopped_by_limit": request_count >= MAX_REQUESTS or time.monotonic() - _started >= MAX_SECONDS,
    }
    (OUT / "crawl_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

if __name__ == "__main__":
    main()
