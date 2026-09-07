#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any

import requests

OUT = Path("store_endpoint_probe_output")
OUT.mkdir(exist_ok=True)
LAT, LON = 28.2282, 112.9388
WRAPPER = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
BASES = [
    "https://msapi.lbxcn.com:31443",
    "http://msapi.lbxcn.com:31380",
    "https://msapi.lbxcn.com",
    "https://msapitest.lbxcn.com:31443",
]
PATHS = [
    "/sems-store/nearby/store/pageNearbyStore",
    "/sems-store/api/nearby/store/pageNearbyStore",
    "/api/sems-store/nearby/store/pageNearbyStore",
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://yx.lbxcn.com",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
}


def get_rows(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    queue = [data]
    seen: set[int] = set()
    while queue:
        obj = queue.pop(0)
        oid = id(obj)
        if oid in seen:
            continue
        seen.add(oid)
        if isinstance(obj, list):
            if not obj or isinstance(obj[0], dict):
                return obj
            queue.extend(obj)
        elif isinstance(obj, dict):
            for key in ("records", "rows", "list", "data", "content", "items"):
                value = obj.get(key)
                if isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    queue.append(value)
            queue.extend(v for v in obj.values() if isinstance(v, (dict, list)))
    return None


def call(spec: dict[str, Any]) -> dict[str, Any]:
    name = spec["name"]
    method = spec["method"]
    url = spec["url"]
    kwargs: dict[str, Any] = {
        "headers": {**BASE_HEADERS, **spec.get("headers", {})},
        "timeout": (5, 8),
        "allow_redirects": True,
        "verify": True,
    }
    if spec.get("params") is not None:
        kwargs["params"] = spec["params"]
    if spec.get("json") is not None:
        kwargs["json"] = spec["json"]
    if spec.get("data") is not None:
        kwargs["data"] = spec["data"]
    started = time.time()
    rec: dict[str, Any] = {k: v for k, v in spec.items() if k not in {"headers"}}
    try:
        with requests.Session() as s:
            r = s.request(method, url, **kwargs)
        rec.update({
            "status": r.status_code,
            "final_url": r.url,
            "elapsed": round(time.time() - started, 3),
            "content_type": r.headers.get("content-type"),
            "response_headers": dict(r.headers),
            "length": len(r.content),
            "body": r.text[:20000],
        })
        try:
            payload = r.json()
            rows = get_rows(payload)
            rec["json"] = payload
            rec["row_count"] = len(rows) if isinstance(rows, list) else None
            rec["sample_rows"] = rows[:3] if isinstance(rows, list) else None
        except Exception as exc:  # noqa: BLE001
            rec["json_error"] = repr(exc)
    except Exception as exc:  # noqa: BLE001
        rec["elapsed"] = round(time.time() - started, 3)
        rec["error"] = repr(exc)
    (OUT / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def main() -> None:
    exact = {
        "latitude": str(LAT),
        "longitude": str(LON),
        "page": 1,
        "size": 5,
        "formatIdList": ["01", "20", "92"],
        "isClosed": 0,
        "isParent": 1,
        "radius": 100,
    }
    specs: list[dict[str, Any]] = []

    # Determine whether the public H5 wrapper passes optional query parameters through.
    wrapper_variants = {
        "base": {"Latitude": LAT, "Longitude": LON},
        "size100": {"Latitude": LAT, "Longitude": LON, "size": 100},
        "page2": {"Latitude": LAT, "Longitude": LON, "page": 2, "size": 10},
        "radius1": {"Latitude": LAT, "Longitude": LON, "radius": 1},
        "radius1000": {"Latitude": LAT, "Longitude": LON, "radius": 1000, "size": 100},
        "capitalized": {"Latitude": LAT, "Longitude": LON, "Page": 2, "Size": 100, "Radius": 1000},
    }
    for key, params in wrapper_variants.items():
        specs.append({"name": f"wrapper_{key}", "method": "GET", "url": WRAPPER, "params": params})

    body_variants = {
        "exact": exact,
        "size100": {**exact, "size": 100},
        "page2": {**exact, "page": 2, "size": 100},
        "radius1000": {**exact, "radius": 1000, "size": 100},
        "no_format": {k: v for k, v in {**exact, "radius": 1000, "size": 100}.items() if k != "formatIdList"},
        "empty_format": {**exact, "formatIdList": [], "radius": 1000, "size": 100},
    }
    for bi, base in enumerate(BASES):
        for pi, path in enumerate(PATHS):
            url = base + path
            # Exact request for every candidate URL; broader variants only on canonical path.
            specs.append({"name": f"b{bi}_p{pi}_json_exact", "method": "POST", "url": url, "json": exact})
            if pi == 0:
                for key, payload in body_variants.items():
                    specs.append({"name": f"b{bi}_json_{key}", "method": "POST", "url": url, "json": payload})
                specs.append({"name": f"b{bi}_form_exact", "method": "POST", "url": url, "data": exact, "headers": {"Content-Type": "application/x-www-form-urlencoded"}})
                specs.append({"name": f"b{bi}_get_exact", "method": "GET", "url": url, "params": exact})
                specs.append({"name": f"b{bi}_options", "method": "OPTIONS", "url": url})

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(call, spec): spec["name"] for spec in specs}
        for future in concurrent.futures.as_completed(futures):
            rec = future.result()
            results.append(rec)
            print(json.dumps({
                "name": rec.get("name"),
                "status": rec.get("status"),
                "elapsed": rec.get("elapsed"),
                "length": rec.get("length"),
                "row_count": rec.get("row_count"),
                "error": rec.get("error"),
                "body": (rec.get("body") or "")[:300],
            }, ensure_ascii=False), flush=True)

    results.sort(key=lambda x: x.get("name", ""))
    (OUT / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
