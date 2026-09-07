#!/usr/bin/env python3
"""Probe the public LBX campaign store-list endpoints with sample coordinates."""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

OUT = Path("store_probe_output")
OUT.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.50",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
        "Origin": "https://yx.lbxcn.com",
    }
)

COORDS = {
    "changsha_center": (28.2283, 112.9388),
    "changsha_yuelu": (28.2353, 112.9314),
    "xian_center": (34.3432, 108.9396),
    "beijing_center": (39.9042, 116.4074),
    "nanjing_center": (32.0593, 118.7966),
    "hefei_center": (31.8206, 117.2272),
    "shanghai_center": (31.2304, 121.4737),
    "lanzhou_center": (36.0611, 103.8343),
    "hangzhou_center": (30.2741, 120.1551),
    "wuhan_center": (30.5928, 114.3055),
}

ENDPOINTS = [
    "https://yx.lbxcn.com/out/2026api/getlbxStoreList",
    "https://yx.lbxcn.com/out/2212sping/getlbxStoreList",
]


def probe(name: str, url: str, params: dict[str, object] | None = None) -> dict[str, object]:
    started = time.time()
    try:
        response = SESSION.get(url, params=params, timeout=30, allow_redirects=True)
        body = response.content
        text = body.decode(response.encoding or "utf-8", errors="replace")
        suffix = "json" if "json" in (response.headers.get("content-type") or "").lower() else "txt"
        (OUT / f"{name}.{suffix}").write_bytes(body)
        parsed = None
        try:
            parsed = response.json()
        except Exception:
            pass
        return {
            "name": name,
            "url": response.url,
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "length": len(body),
            "elapsed": round(time.time() - started, 3),
            "json": parsed,
            "preview": text[:2000],
        }
    except Exception as exc:
        return {
            "name": name,
            "url": url + ("?" + urlencode(params) if params else ""),
            "elapsed": round(time.time() - started, 3),
            "error": repr(exc),
        }


def main() -> None:
    results: list[dict[str, object]] = []
    for endpoint in ENDPOINTS:
        tag = "2026" if "2026api" in endpoint else "2212"
        for coord_name, (lat, lon) in COORDS.items():
            result = probe(
                f"{tag}_{coord_name}",
                endpoint,
                {"Latitude": lat, "Longitude": lon},
            )
            results.append(result)
            print(json.dumps(result, ensure_ascii=False, indent=2)[:5000], flush=True)
            time.sleep(0.6)

    # Parameter behavior probes.
    extras = [
        ("2026_no_params", ENDPOINTS[0], None),
        ("2026_lowercase", ENDPOINTS[0], {"latitude": 28.2283, "longitude": 112.9388}),
        ("2026_zero", ENDPOINTS[0], {"Latitude": 0, "Longitude": 0}),
        ("2026_page", ENDPOINTS[0], {"Latitude": 28.2283, "Longitude": 112.9388, "page": 2, "pageSize": 100}),
    ]
    for name, url, params in extras:
        result = probe(name, url, params)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:5000], flush=True)
        time.sleep(0.6)

    # Download the two official footer codes for later decoding/inspection.
    images = {
        "official_scan_to_buy.jpg": "https://omo-oss-image.thefastimg.com/portal-saas/pg2024101217574431839/cms/image/68ec6b77-7b58-4aca-9a76-1bdb3531b2c7.jpg",
        "official_service_wechat.jpg": "https://omo-oss-image.thefastimg.com/portal-saas/pg2024101217574431839/cms/image/b26fce50-3b1f-41d6-b621-5292ce6cedf2.jpg",
    }
    for filename, url in images.items():
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            (OUT / filename).write_bytes(r.content)
            results.append({"name": filename, "url": url, "status": r.status_code, "length": len(r.content), "content_type": r.headers.get("content-type")})
        except Exception as exc:
            results.append({"name": filename, "url": url, "error": repr(exc)})

    (OUT / "probe_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
