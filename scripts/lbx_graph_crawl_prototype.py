#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

OUT = Path("graph_crawl_output")
OUT.mkdir(exist_ok=True)
URL = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
MAX_REQUESTS = 800
WORKERS = 8

SEEDS = [
    (28.2282, 112.9388, "长沙中心"),
    (28.1960, 113.0820, "长沙东"),
    (28.1390, 113.0080, "长沙南"),
    (28.2700, 112.9900, "长沙北"),
    (28.2400, 112.8600, "长沙西"),
]

local = threading.local()


def session() -> requests.Session:
    if not hasattr(local, "s"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
        })
        local.s = s
    return local.s


def fetch(item):
    lat, lon, source = item
    last = None
    for attempt in range(3):
        try:
            r = session().get(URL, params={"Latitude": lat, "Longitude": lon}, timeout=12)
            r.raise_for_status()
            obj = r.json()
            rows = obj.get("data", {}).get("data", [])
            if not isinstance(rows, list):
                rows = []
            return {"lat": lat, "lon": lon, "source": source, "rows": rows, "status": r.status_code}
        except Exception as exc:
            last = repr(exc)
            time.sleep(0.4 * (attempt + 1))
    return {"lat": lat, "lon": lon, "source": source, "rows": [], "error": last}


def coord_key(lat, lon):
    return (round(float(lat), 6), round(float(lon), 6))


def store_key(row):
    return str(row.get("shop_id") or row.get("sap_id") or row.get("org_code") or f"{row.get('deptName')}|{row.get('latGd')}|{row.get('lngGd')}")


def main():
    queue = deque(SEEDS)
    queued = {coord_key(x[0], x[1]) for x in SEEDS}
    queried = set()
    stores = {}
    query_log = []
    requests_made = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while queue and requests_made < MAX_REQUESTS:
            batch = []
            while queue and len(batch) < WORKERS * 2 and requests_made + len(batch) < MAX_REQUESTS:
                item = queue.popleft()
                ck = coord_key(item[0], item[1])
                if ck in queried:
                    continue
                queried.add(ck)
                batch.append(item)
            if not batch:
                continue
            futures = [pool.submit(fetch, item) for item in batch]
            for fut in as_completed(futures):
                result = fut.result()
                requests_made += 1
                rows = result.pop("rows")
                new_count = 0
                for row in rows:
                    sk = store_key(row)
                    if sk not in stores:
                        stores[sk] = row
                        new_count += 1
                    lat = row.get("latGd") or row.get("lat")
                    lon = row.get("lngGd") or row.get("lng")
                    try:
                        ck = coord_key(lat, lon)
                    except Exception:
                        continue
                    if ck not in queued and ck not in queried:
                        queue.append((float(lat), float(lon), f"store:{sk}"))
                        queued.add(ck)
                result.update({"row_count": len(rows), "new_store_count": new_count})
                query_log.append(result)
            if requests_made % 50 < WORKERS * 2:
                print(json.dumps({
                    "requests": requests_made,
                    "stores": len(stores),
                    "queue": len(queue),
                    "elapsed_s": round(time.time() - start, 1),
                }, ensure_ascii=False), flush=True)

    output = {
        "summary": {
            "requests": requests_made,
            "unique_stores": len(stores),
            "remaining_queue": len(queue),
            "elapsed_s": round(time.time() - start, 1),
            "max_requests": MAX_REQUESTS,
            "workers": WORKERS,
        },
        "stores": list(stores.values()),
        "queries": query_log,
    }
    (OUT / "result.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
