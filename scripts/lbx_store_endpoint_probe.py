#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

OUT = Path("store_endpoint_probe_output")
OUT.mkdir(exist_ok=True)
S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
})

POINTS = {
    "changsha_center": (28.2282, 112.9388),
    "changsha_east": (28.1900, 113.1000),
    "beijing": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737),
    "xian": (34.3416, 108.9398),
    "hangzhou": (30.2741, 120.1551),
    "wuhan": (30.5928, 114.3055),
    "guangzhou": (23.1291, 113.2644),
    "chengdu": (30.5728, 104.0668),
    "harbin": (45.8038, 126.5349),
}
ENDPOINTS = [
    "https://yx.lbxcn.com/out/2026api/getlbxStoreList",
    "https://muyang.hn.cn/out/2026api/getlbxStoreList",
    "https://yx.lbxcn.com/out/2212sping/getlbxStoreList",
    "https://muyang.hn.cn/out/2212sping/getlbxStoreList",
]
PARAM_VARIANTS = [
    lambda lat, lon: {"Latitude": lat, "Longitude": lon},
    lambda lat, lon: {"latitude": lat, "longitude": lon},
    lambda lat, lon: {"lat": lat, "lng": lon},
]


def summarize_json(data):
    out = {"type": type(data).__name__}
    if isinstance(data, dict):
        out["keys"] = list(data.keys())
        out["code"] = data.get("code")
        out["message"] = data.get("message") or data.get("msg")
        d = data.get("data")
        out["data_type"] = type(d).__name__
        if isinstance(d, dict):
            out["data_keys"] = list(d.keys())
            for k in ("rows", "data", "list", "records"):
                v = d.get(k)
                if isinstance(v, list):
                    out["list_key"] = k
                    out["list_len"] = len(v)
                    out["sample"] = v[:3]
                    break
        elif isinstance(d, list):
            out["list_key"] = "data"
            out["list_len"] = len(d)
            out["sample"] = d[:3]
    elif isinstance(data, list):
        out["list_len"] = len(data)
        out["sample"] = data[:3]
    return out


def main():
    report = []
    for endpoint in ENDPOINTS:
        # Test exact capitalization at Changsha, then all points if successful.
        variants = PARAM_VARIANTS if endpoint == ENDPOINTS[0] else PARAM_VARIANTS[:1]
        for variant_idx, variant in enumerate(variants):
            point_items = list(POINTS.items()) if variant_idx == 0 else [("changsha_center", POINTS["changsha_center"])]
            for point_name, (lat, lon) in point_items:
                params = variant(lat, lon)
                url = endpoint + "?" + urlencode(params)
                rec = {"endpoint": endpoint, "point": point_name, "params": params, "url": url}
                try:
                    started = time.time()
                    r = S.get(endpoint, params=params, timeout=30)
                    rec.update({"status": r.status_code, "content_type": r.headers.get("content-type"), "length": len(r.content), "elapsed": round(time.time()-started, 3), "preview": r.text[:1000]})
                    try:
                        data = r.json()
                        rec["json_summary"] = summarize_json(data)
                        safe_name = f"{ENDPOINTS.index(endpoint):02d}_{variant_idx:02d}_{point_name}.json"
                        (OUT / safe_name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception as exc:
                        rec["json_error"] = repr(exc)
                except Exception as exc:
                    rec["error"] = repr(exc)
                report.append(rec)
                print(json.dumps({k: v for k, v in rec.items() if k != "preview"}, ensure_ascii=False, indent=2), flush=True)
                time.sleep(0.3)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
