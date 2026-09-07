#!/usr/bin/env python3
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("quick_output")
OUT.mkdir(exist_ok=True)
CTX = ssl.create_default_context()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.amap.com/",
    "X-Requested-With": "XMLHttpRequest",
}


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25, context=CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"status": resp.status, "url": resp.geturl(), "headers": dict(resp.headers), "body": body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"status": exc.code, "url": exc.geturl(), "headers": dict(exc.headers), "body": body, "error": str(exc)}
    except Exception as exc:
        return {"status": None, "url": url, "body": "", "error": repr(exc)}


def amap(host: str, city: str, page: int = 1) -> str:
    params = {
        "query_type": "TQUERY",
        "pagesize": "100",
        "pagenum": str(page),
        "qii": "true",
        "cluster_state": "5",
        "need_utd": "true",
        "utd_sceneid": "1000",
        "div": "PC1000",
        "addr_poi_merge": "true",
        "is_classify": "true",
        "zoom": "10",
        "city": city,
        "keywords": "老百姓大药房",
    }
    return f"https://{host}/service/poiInfo?{urllib.parse.urlencode(params)}"


def summarize(body: str):
    try:
        data = json.loads(body)
    except Exception as exc:
        return {"json": False, "error": repr(exc), "preview": body[:1500]}
    summary = {"json": True, "type": type(data).__name__}
    if isinstance(data, dict):
        summary["keys"] = list(data)[:50]
        for key in ["status", "info", "count", "total", "message", "result", "data"]:
            if key in data:
                val = data[key]
                summary[key] = val if not isinstance(val, (dict, list)) else {"type": type(val).__name__, "length": len(val), "keys": list(val)[:30] if isinstance(val, dict) else None}
        text = json.dumps(data, ensure_ascii=False)
        summary["contains_keyword"] = "老百姓" in text
        summary["preview"] = text[:5000]
    else:
        summary["preview"] = repr(data)[:5000]
    return summary


def main():
    probes = []
    for host in ["www.amap.com", "ditu.amap.com"]:
        for city in ["430100", "610100", "110000"]:
            url = amap(host, city)
            raw = get(url)
            probes.append({
                "name": f"{host}-{city}",
                "request_url": url,
                "status": raw.get("status"),
                "final_url": raw.get("url"),
                "content_type": raw.get("headers", {}).get("Content-Type"),
                "error": raw.get("error"),
                "summary": summarize(raw.get("body", "")),
            })
    (OUT / "amap_probe.json").write_text(json.dumps(probes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(probes, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
