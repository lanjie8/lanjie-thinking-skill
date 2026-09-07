#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

OUT = Path("lbx_store_api_probe_output")
OUT.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
    "Origin": "https://yx.lbxcn.com",
    "X-Requested-With": "XMLHttpRequest",
})

POINTS = {
    "长沙": (28.2282, 112.9388),
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "西安": (34.3416, 108.9398),
    "武汉": (30.5928, 114.3055),
    "成都": (30.5728, 104.0668),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551),
    "南京": (32.0603, 118.7969),
    "天津": (39.0842, 117.2009),
    "沈阳": (41.8057, 123.4315),
    "南宁": (22.8170, 108.3665),
    "兰州": (36.0611, 103.8343),
    "乌鲁木齐": (43.8256, 87.6168),
}

ENDPOINTS = {
    "new_muyang": "https://muyang.hn.cn/out/2026api/getlbxStoreList",
    "new_yx": "https://yx.lbxcn.com/out/2026api/getlbxStoreList",
    "old_muyang": "https://muyang.hn.cn/out/2212sping/getlbxStoreList",
    "old_yx": "https://yx.lbxcn.com/out/2212sping/getlbxStoreList",
}


def safe_json(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        try:
            return json.loads(resp.text.lstrip("\ufeff"))
        except Exception:
            return None


def find_lists(obj, path="$", depth=0):
    out = []
    if depth > 8:
        return out
    if isinstance(obj, list):
        out.append({"path": path, "count": len(obj), "sample": obj[:2]})
        for i, item in enumerate(obj[:2]):
            out.extend(find_lists(item, f"{path}[{i}]", depth + 1))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            out.extend(find_lists(value, f"{path}.{key}", depth + 1))
    return out


def flatten_key_summary(obj, path="$", depth=0):
    out = []
    if depth > 6:
        return out
    if isinstance(obj, dict):
        out.append({"path": path, "keys": list(obj.keys())[:100]})
        for key, value in list(obj.items())[:30]:
            if isinstance(value, (dict, list)):
                out.extend(flatten_key_summary(value, f"{path}.{key}", depth + 1))
    elif isinstance(obj, list) and obj:
        out.extend(flatten_key_summary(obj[0], f"{path}[0]", depth + 1))
    return out


def request_one(endpoint_name: str, endpoint: str, city: str, lat: float, lng: float, variant: str):
    params = {"Latitude": lat, "Longitude": lng}
    if variant == "lower":
        params = {"latitude": lat, "longitude": lng}
    elif variant == "latlng":
        params = {"lat": lat, "lng": lng}
    elif variant == "swapped":
        params = {"Latitude": lng, "Longitude": lat}
    url = endpoint + "?" + urlencode(params)
    started = time.time()
    try:
        resp = SESSION.get(url, timeout=45, allow_redirects=True)
        data = safe_json(resp)
        raw_name = f"{endpoint_name}_{city}_{variant}.txt".replace("/", "_")
        (OUT / raw_name).write_text(resp.text, encoding="utf-8")
        record = {
            "endpoint_name": endpoint_name,
            "endpoint": endpoint,
            "city": city,
            "latitude": lat,
            "longitude": lng,
            "variant": variant,
            "url": url,
            "status": resp.status_code,
            "final_url": resp.url,
            "content_type": resp.headers.get("content-type"),
            "length": len(resp.content),
            "elapsed": round(time.time() - started, 3),
            "response_headers": {k: v for k, v in resp.headers.items() if k.lower() in {"server", "content-type", "cache-control", "access-control-allow-origin"}},
            "preview": resp.text[:3000],
            "json": data,
            "list_summary": find_lists(data) if data is not None else [],
            "key_summary": flatten_key_summary(data) if data is not None else [],
        }
        return record
    except Exception as exc:
        return {
            "endpoint_name": endpoint_name,
            "endpoint": endpoint,
            "city": city,
            "latitude": lat,
            "longitude": lng,
            "variant": variant,
            "url": url,
            "status": None,
            "elapsed": round(time.time() - started, 3),
            "error": repr(exc),
        }


def compact_for_stdout(record):
    return {k: record.get(k) for k in [
        "endpoint_name", "city", "variant", "status", "content_type", "length", "elapsed", "error", "list_summary", "key_summary"
    ]}


def main():
    report = []
    # Probe the production 2026 endpoint across many cities using the exact parameter names from the official campaign JS.
    for city, (lat, lng) in POINTS.items():
        rec = request_one("new_muyang", ENDPOINTS["new_muyang"], city, lat, lng, "exact")
        report.append(rec)
        print(json.dumps(compact_for_stdout(rec), ensure_ascii=False, indent=2)[:12000], flush=True)
        time.sleep(0.8)

    # Probe host aliases and parameter variants only at Changsha to understand contract behavior.
    lat, lng = POINTS["长沙"]
    for endpoint_name in ["new_yx", "old_muyang", "old_yx"]:
        rec = request_one(endpoint_name, ENDPOINTS[endpoint_name], "长沙", lat, lng, "exact")
        report.append(rec)
        print(json.dumps(compact_for_stdout(rec), ensure_ascii=False, indent=2)[:12000], flush=True)
        time.sleep(0.8)
    for variant in ["lower", "latlng", "swapped"]:
        rec = request_one("new_muyang", ENDPOINTS["new_muyang"], "长沙", lat, lng, variant)
        report.append(rec)
        print(json.dumps(compact_for_stdout(rec), ensure_ascii=False, indent=2)[:12000], flush=True)
        time.sleep(0.8)

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
