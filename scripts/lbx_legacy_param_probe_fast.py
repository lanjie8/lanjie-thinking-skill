#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

OUT = Path("legacy_param_probe_output")
OUT.mkdir(exist_ok=True)
URL = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
})

POINTS = {
    "changsha": (28.2282, 112.9388),
    "xian": (34.3416, 108.9398),
}
VARIANTS = [
    ("default", {}),
    ("size_1", {"size": 1}),
    ("size_3", {"size": 3}),
    ("size_100", {"size": 100}),
    ("page_2_size_10", {"page": 2, "size": 10}),
    ("pageNo_2_pageSize_100", {"pageNo": 2, "pageSize": 100}),
    ("radius_1", {"radius": 1}),
    ("radius_5", {"radius": 5}),
    ("radius_200", {"radius": 200}),
    ("upper_case", {"Page": 2, "Size": 100, "Radius": 200}),
]


def get_rows(obj):
    try:
        rows = obj["data"]["data"]
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def main():
    report = []
    for point_name, (lat, lon) in POINTS.items():
        for variant_name, extra in VARIANTS:
            params = {"Latitude": lat, "Longitude": lon, **extra}
            rec = {"point": point_name, "variant": variant_name, "params": params}
            try:
                r = S.get(URL, params=params, timeout=15)
                rec.update({"status": r.status_code, "length": len(r.content), "url": r.url})
                obj = r.json()
                rows = get_rows(obj)
                rec["count"] = len(rows)
                rec["ids"] = [str(x.get("shop_id") or "") for x in rows]
                rec["distances"] = [x.get("distance") for x in rows]
                rec["max_distance"] = max([float(x.get("distance") or 0) for x in rows] or [0])
                rec["first"] = rows[0] if rows else None
            except Exception as exc:
                rec["error"] = repr(exc)
            report.append(rec)
            print(json.dumps({k: v for k, v in rec.items() if k != "first"}, ensure_ascii=False), flush=True)
            time.sleep(0.15)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
