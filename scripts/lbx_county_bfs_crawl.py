#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

OUT = Path("county_crawl_output")
OUT.mkdir(exist_ok=True)
URL = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
GEO_URL = "https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/xzqh_with_amap_coordinates.json"
WORKERS = int(os.getenv("LBX_WORKERS", "12"))
BATCH_SIZE = int(os.getenv("LBX_BATCH_SIZE", "120"))
MAX_REQUESTS = int(os.getenv("LBX_MAX_REQUESTS", "30000"))
MAX_SECONDS = int(os.getenv("LBX_MAX_SECONDS", "2400"))
STARTED = time.monotonic()

CORE_MARKETS = {
    "湖南省", "江苏省", "安徽省", "甘肃省", "陕西省", "广西壮族自治区",
    "内蒙古自治区", "天津市", "湖北省", "浙江省", "山西省", "河南省",
    "山东省", "上海市", "宁夏回族自治区", "贵州省", "广东省", "江西省",
}

_local = threading.local()


def session() -> requests.Session:
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
        })
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=0)
        s.mount("https://", adapter)
        _local.session = s
    return _local.session


def coord_key(lat, lon):
    return round(float(lat), 6), round(float(lon), 6)


def store_key(row):
    for k in ("org_code", "shop_id"):
        v = str(row.get(k) or "").strip()
        if v and v not in {"0", "null", "None"}:
            return f"{k}:{v}"
    return "fallback:" + "|".join(str(row.get(k) or "").strip() for k in ("companyCode", "sap_id", "deptName", "deptAddr"))


def active(row):
    return str(row.get("is_close") or "").strip() in {"", "0"}


def fetch_point(item):
    lat, lon, source = item
    last = None
    for attempt in range(2):
        try:
            r = session().get(URL, params={"Latitude": lat, "Longitude": lon}, timeout=(4, 10))
            r.raise_for_status()
            obj = r.json()
            rows = obj.get("data", {}).get("data", [])
            if not isinstance(rows, list):
                rows = []
            return {"lat": lat, "lon": lon, "source": source, "rows": [x for x in rows if isinstance(x, dict)]}
        except Exception as exc:
            last = repr(exc)
            time.sleep(0.25 * (attempt + 1))
    return {"lat": lat, "lon": lon, "source": source, "rows": [], "error": last}


def collect_seeds():
    r = requests.get(GEO_URL, timeout=45)
    r.raise_for_status()
    provinces = r.json()
    seeds = []
    province_counts = Counter()

    def walk(node, province_name):
        center = node.get("center") if isinstance(node, dict) else None
        if isinstance(center, dict):
            lat = center.get("latitude")
            lon = center.get("longitude")
            try:
                ck = coord_key(lat, lon)
                seeds.append((ck[0], ck[1], f"admin:{province_name}:{node.get('level','')}:{node.get('name','')}"))
                province_counts[province_name] += 1
            except Exception:
                pass
        for child in node.get("children", []) if isinstance(node, dict) else []:
            walk(child, province_name)

    for province in provinces:
        pname = str(province.get("name") or "")
        if pname in CORE_MARKETS:
            walk(province, pname)

    seen = set()
    unique = []
    for item in seeds:
        ck = coord_key(item[0], item[1])
        if ck not in seen:
            seen.add(ck)
            unique.append(item)
    return unique, dict(province_counts)


def merge_store(existing, new):
    if existing is None:
        return dict(new)
    for k, v in new.items():
        if existing.get(k) in (None, "") and v not in (None, ""):
            existing[k] = v
    return existing


def write_outputs(stores, report, progress):
    store_rows = list(stores.values())
    (OUT / "stores.json").write_text(json.dumps(store_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "crawl_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "progress.json").write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = sorted(set().union(*(row.keys() for row in store_rows))) if store_rows else []
    with (OUT / "stores.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(store_rows)


def main():
    seeds, seed_province_counts = collect_seeds()
    queue = deque(seeds)
    queued = {coord_key(x[0], x[1]) for x in seeds}
    queried = set()
    stores = {}
    requests_made = 0
    errors = 0
    empty_responses = 0
    total_rows = 0
    seed_requests = 0
    store_requests = 0
    last_checkpoint = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while queue and requests_made < MAX_REQUESTS and time.monotonic() - STARTED < MAX_SECONDS:
            batch = []
            while queue and len(batch) < BATCH_SIZE and requests_made + len(batch) < MAX_REQUESTS:
                item = queue.popleft()
                ck = coord_key(item[0], item[1])
                if ck in queried:
                    continue
                queried.add(ck)
                batch.append(item)
            if not batch:
                continue
            futures = {pool.submit(fetch_point, item): item for item in batch}
            for fut in as_completed(futures):
                result = fut.result()
                requests_made += 1
                if result.get("source", "").startswith("admin:"):
                    seed_requests += 1
                else:
                    store_requests += 1
                if result.get("error"):
                    errors += 1
                rows = result.get("rows") or []
                total_rows += len(rows)
                if not rows:
                    empty_responses += 1
                for row in rows:
                    if not active(row):
                        continue
                    sk = store_key(row)
                    stores[sk] = merge_store(stores.get(sk), row)
                    lat = row.get("latGd") or row.get("lat") or row.get("latBd")
                    lon = row.get("lngGd") or row.get("lng") or row.get("lngBd")
                    try:
                        ck = coord_key(lat, lon)
                    except Exception:
                        continue
                    if ck not in queried and ck not in queued:
                        queue.append((ck[0], ck[1], f"store:{sk}"))
                        queued.add(ck)
            if requests_made - last_checkpoint >= 500:
                elapsed = round(time.monotonic() - STARTED, 1)
                progress = {
                    "requests": requests_made,
                    "unique_stores": len(stores),
                    "queue_remaining": len(queue),
                    "errors": errors,
                    "elapsed_s": elapsed,
                }
                (OUT / "progress.json").write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(progress, ensure_ascii=False), flush=True)
                last_checkpoint = requests_made

    elapsed = round(time.monotonic() - STARTED, 1)
    report = {
        "method": "county/city/province administrative centers plus recursive store-coordinate BFS",
        "endpoint": URL,
        "core_markets": sorted(CORE_MARKETS),
        "seed_count": len(seeds),
        "seed_count_by_province": seed_province_counts,
        "requests": requests_made,
        "seed_requests": seed_requests,
        "store_coordinate_requests": store_requests,
        "total_rows_returned": total_rows,
        "unique_active_store_records": len(stores),
        "errors": errors,
        "empty_responses": empty_responses,
        "remaining_queue": len(queue),
        "elapsed_s": elapsed,
        "max_requests": MAX_REQUESTS,
        "max_seconds": MAX_SECONDS,
        "workers": WORKERS,
        "batch_size": BATCH_SIZE,
        "stopped_by_request_limit": requests_made >= MAX_REQUESTS,
        "stopped_by_time_limit": elapsed >= MAX_SECONDS,
        "queue_converged": len(queue) == 0,
    }
    progress = {
        "requests": requests_made,
        "unique_stores": len(stores),
        "queue_remaining": len(queue),
        "errors": errors,
        "elapsed_s": elapsed,
        "finished": True,
    }
    write_outputs(stores, report, progress)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
