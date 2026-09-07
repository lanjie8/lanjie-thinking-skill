#!/usr/bin/env python3
"""Inspect LBX legacy store endpoint behavior and pagination parameters."""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

OUT = Path("store_probe_output")
OUT.mkdir(exist_ok=True)

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.50",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
    "Origin": "https://yx.lbxcn.com",
})

OLD = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
NEW_BACKEND = "https://msapitest.lbxcn.com:31443/sems-store/nearby/store/pageNearbyStore"


def save_result(name: str, response: requests.Response | None, error: Exception | None, started: float) -> dict:
    if response is None:
        return {"name": name, "elapsed": round(time.time()-started, 3), "error": repr(error)}
    body = response.content
    (OUT / f"{name}.txt").write_bytes(body)
    try:
        parsed = response.json()
    except Exception:
        parsed = None
    return {
        "name": name,
        "url": response.url,
        "status": response.status_code,
        "headers": dict(response.headers),
        "length": len(body),
        "elapsed": round(time.time()-started, 3),
        "json": parsed,
        "preview": response.text[:3000],
    }


def get(name: str, params: dict | None) -> dict:
    started = time.time()
    try:
        r = S.get(OLD, params=params, timeout=35)
        return save_result(name, r, None, started)
    except Exception as exc:
        return save_result(name, None, exc, started)


def post(name: str, url: str, payload: dict, headers: dict | None = None) -> dict:
    started = time.time()
    try:
        r = S.post(url, json=payload, headers=headers or {}, timeout=35)
        return save_result(name, r, None, started)
    except Exception as exc:
        return save_result(name, None, exc, started)


def main() -> None:
    lat, lon = 28.2283, 112.9388
    cases = [
        ("old_valid", {"Latitude": lat, "Longitude": lon}),
        ("old_no_params", None),
        ("old_only_lat", {"Latitude": lat}),
        ("old_invalid_text", {"Latitude": "abc", "Longitude": "xyz"}),
        ("old_zero", {"Latitude": 0, "Longitude": 0}),
        ("old_page_lower", {"Latitude": lat, "Longitude": lon, "page": 2, "size": 100, "radius": 100}),
        ("old_page_upper", {"Latitude": lat, "Longitude": lon, "Page": 2, "Size": 100, "Radius": 100}),
        ("old_pagesize", {"Latitude": lat, "Longitude": lon, "page": 2, "pageSize": 100, "Radius": 100}),
        ("old_alt_coords", {"latitude": lat, "longitude": lon, "page": 2, "size": 100}),
    ]
    results = []
    for name, params in cases:
        result = get(name, params)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:12000], flush=True)
        time.sleep(0.4)

    base_payload = {
        "latitude": lat,
        "longitude": lon,
        "page": 1,
        "size": 100,
        "formatIdList": ["01", "20", "92"],
        "isClosed": 0,
        "isParent": 1,
        "radius": 100,
    }
    payloads = [
        ("new_backend_numeric", base_payload),
        ("new_backend_string", {**base_payload, "latitude": str(lat), "longitude": str(lon)}),
        ("new_backend_no_formats", {k:v for k,v in base_payload.items() if k != "formatIdList"}),
        ("new_backend_radius20", {**base_payload, "radius": 20}),
    ]
    header_variants = [
        ("plain", {}),
        ("ajax", {"X-Requested-With": "XMLHttpRequest"}),
        ("source", {"source": "4", "channel": "h5"}),
    ]
    for pname, payload in payloads:
        for hname, headers in header_variants:
            name = f"{pname}_{hname}"
            result = post(name, NEW_BACKEND, payload, headers)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False, indent=2)[:12000], flush=True)
            time.sleep(0.4)

    (OUT / "probe_summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
