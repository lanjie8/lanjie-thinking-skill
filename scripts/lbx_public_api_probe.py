#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

OUT = Path("public_api_probe_output")
OUT.mkdir(exist_ok=True)

ENDPOINTS = [
    "https://muyang.hn.cn/out/2026api/getlbxStoreList",
    "https://muyang.hn.cn/out/2212sping/getlbxStoreList",
]

POINTS = [
    ("no_params", None, None),
    ("changsha_center", 28.2282, 112.9388),
    ("changsha_north", 28.3500, 112.9800),
    ("changsha_west", 28.2300, 112.8000),
    ("beijing", 39.9042, 116.4074),
    ("shanghai", 31.2304, 121.4737),
    ("xian", 34.3416, 108.9398),
    ("guangzhou", 23.1291, 113.2644),
    ("hangzhou", 30.2741, 120.1551),
    ("wuhan", 30.5928, 114.3055),
    ("zhengzhou", 34.7466, 113.6254),
    ("chengdu", 30.5728, 104.0668),
    ("harbin", 45.8038, 126.5350),
    ("urumqi", 43.8256, 87.6168),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://yx.lbxcn.com/",
}


def shape(x: Any, depth: int = 0) -> Any:
    if depth > 4:
        return type(x).__name__
    if isinstance(x, dict):
        return {str(k): shape(v, depth + 1) for k, v in list(x.items())[:30]}
    if isinstance(x, list):
        return {"type": "list", "length": len(x), "sample": [shape(v, depth + 1) for v in x[:3]]}
    return {"type": type(x).__name__, "value": x if isinstance(x, (str, int, float, bool)) else None}


def collect_lists(x: Any, path: str = "$") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(x, list):
        out.append({"path": path, "length": len(x), "sample": x[:3]})
        for i, v in enumerate(x[:3]):
            out.extend(collect_lists(v, f"{path}[{i}]"))
    elif isinstance(x, dict):
        for k, v in x.items():
            out.extend(collect_lists(v, f"{path}.{k}"))
    return out


def main() -> None:
    session = requests.Session()
    session.headers.update(HEADERS)
    report: list[dict[str, Any]] = []
    for endpoint in ENDPOINTS:
        for label, lat, lon in POINTS:
            params = {} if lat is None else {"Latitude": lat, "Longitude": lon}
            started = time.time()
            item: dict[str, Any] = {"endpoint": endpoint, "label": label, "params": params}
            try:
                r = session.get(endpoint, params=params, timeout=30)
                item.update(
                    status=r.status_code,
                    final_url=r.url,
                    elapsed=round(time.time() - started, 3),
                    content_type=r.headers.get("content-type"),
                    text_preview=r.text[:1000],
                )
                try:
                    data = r.json()
                    item["json"] = data
                    item["shape"] = shape(data)
                    item["lists"] = collect_lists(data)
                except Exception as exc:
                    item["json_error"] = repr(exc)
            except Exception as exc:
                item.update(elapsed=round(time.time() - started, 3), error=repr(exc))
            print(json.dumps({k: v for k, v in item.items() if k != "json"}, ensure_ascii=False)[:5000], flush=True)
            report.append(item)
            time.sleep(0.4)
    (OUT / "probe_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Compact summary for easy inspection.
    compact = []
    for it in report:
        row = {k: it.get(k) for k in ["endpoint", "label", "params", "status", "elapsed", "content_type", "error", "json_error"]}
        row["lists"] = [{"path": x.get("path"), "length": x.get("length"), "sample": x.get("sample")} for x in it.get("lists", [])[:8]]
        row["top_json_keys"] = list(it.get("json", {}).keys()) if isinstance(it.get("json"), dict) else None
        compact.append(row)
    (OUT / "compact.json").write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
