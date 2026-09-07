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

LAT, LON = 28.2282, 112.9388
WRAPPER = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
DIRECTS = [
    "https://msapitest.lbxcn.com:31443/sems-store/nearby/store/pageNearbyStore",
    "https://msapi.lbxcn.com:31443/sems-store/nearby/store/pageNearbyStore",
    "https://msapi.lbxcn.com/sems-store/nearby/store/pageNearbyStore",
    "https://api.lbxcn.com/sems-store/nearby/store/pageNearbyStore",
    "https://gateway.lbxcn.com/sems-store/nearby/store/pageNearbyStore",
]


def get_list(data):
    if not isinstance(data, dict):
        return data if isinstance(data, list) else None
    d = data.get("data")
    if isinstance(d, dict):
        for k in ("data", "rows", "list", "records"):
            if isinstance(d.get(k), list):
                return d[k]
    if isinstance(d, list):
        return d
    for k in ("rows", "list", "records"):
        if isinstance(data.get(k), list):
            return data[k]
    return None


def request(name, method, url, *, params=None, payload=None, headers=None):
    rec = {"name": name, "method": method, "url": url, "params": params, "payload": payload}
    try:
        started = time.time()
        r = S.request(method, url, params=params, json=payload, headers=headers or {}, timeout=35, allow_redirects=True)
        rec.update({
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("content-type"),
            "length": len(r.content),
            "elapsed": round(time.time() - started, 3),
            "preview": r.text[:2500],
        })
        try:
            data = r.json()
            rows = get_list(data)
            rec["json_keys"] = list(data.keys()) if isinstance(data, dict) else None
            rec["list_len"] = len(rows) if isinstance(rows, list) else None
            rec["sample"] = rows[:2] if isinstance(rows, list) else None
            (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            rec["json_error"] = repr(exc)
    except Exception as exc:
        rec["error"] = repr(exc)
    print(json.dumps({k: v for k, v in rec.items() if k not in ("preview", "sample")}, ensure_ascii=False, indent=2), flush=True)
    time.sleep(0.2)
    return rec


def main():
    report = []
    # Wrapper: test whether paging/size/radius are passed through.
    wrapper_params = [
        ("base", {"Latitude": LAT, "Longitude": LON}),
        ("size50", {"Latitude": LAT, "Longitude": LON, "size": 50}),
        ("size500", {"Latitude": LAT, "Longitude": LON, "size": 500}),
        ("page2", {"Latitude": LAT, "Longitude": LON, "page": 2, "size": 10}),
        ("radius1000", {"Latitude": LAT, "Longitude": LON, "radius": 1000, "size": 500}),
        ("lowercase", {"latitude": LAT, "longitude": LON, "page": 1, "size": 500, "radius": 1000}),
    ]
    for name, params in wrapper_params:
        report.append(request("wrapper_" + name, "GET", WRAPPER, params=params))
    for name, payload in wrapper_params[:5]:
        report.append(request("wrapper_post_" + name, "POST", WRAPPER, payload=payload))

    payloads = [
        ("exact", {"latitude": str(LAT), "longitude": str(LON), "page": 1, "size": 5, "formatIdList": ["01", "20", "92"], "isClosed": 0, "isParent": 1, "radius": 100}),
        ("numeric", {"latitude": LAT, "longitude": LON, "page": 1, "size": 10, "formatIdList": ["01", "20", "92"], "isClosed": 0, "isParent": 1, "radius": 100}),
        ("nofmt", {"latitude": LAT, "longitude": LON, "page": 1, "size": 100, "isClosed": 0, "isParent": 1, "radius": 1000}),
        ("emptyfmt", {"latitude": LAT, "longitude": LON, "page": 1, "size": 100, "formatIdList": [], "isClosed": 0, "isParent": 1, "radius": 1000}),
        ("minimal", {"latitude": LAT, "longitude": LON, "page": 1, "size": 100}),
    ]
    header_variants = [
        ("plain", {}),
        ("origin", {"Origin": "https://yx.lbxcn.com", "Referer": "https://yx.lbxcn.com/"}),
        ("app", {"Origin": "https://yx.lbxcn.com", "Referer": "https://yx.lbxcn.com/", "channel": "H5", "tenantId": "1", "appId": "lbx"}),
    ]
    for idx, direct in enumerate(DIRECTS):
        for pname, payload in payloads:
            # Keep alternate header tests to the known test host only.
            variants = header_variants if idx == 0 and pname == "exact" else header_variants[:1]
            for hname, headers in variants:
                report.append(request(f"direct_{idx}_{pname}_{hname}", "POST", direct, payload=payload, headers=headers))
        report.append(request(f"direct_{idx}_get", "GET", direct, params=payloads[1][1]))
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
