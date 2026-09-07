#!/usr/bin/env python3
"""Collect publicly mapped LBX-related pharmacy POIs from OpenStreetMap/Overpass.

The result is a supplementary, non-official dataset. It is intentionally tagged
with source and verification level so it can be merged with official public
attachments without overstating completeness.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

OUT = Path("overpass_output")
OUT.mkdir(exist_ok=True)

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

# Main LBX brand plus major regional banners publicly associated with the group.
PATTERNS = [
    "老百姓大药房|老百姓健康药房",
    "怀仁大药房|怀仁健康药房|怀仁连锁",
    "惠仁堂|人川大药房|泽强大药房",
    "百佳惠苏禾|百佳惠大药房|苏禾大药房|新千秋药房|三品堂大药房|隆泰源大药房|华康大药房|龙盛大药房",
]


def post_overpass(query: str) -> tuple[str, dict[str, Any]]:
    body = parse.urlencode({"data": query}).encode("utf-8")
    last_error: Exception | None = None
    for mirror in MIRRORS:
        req = request.Request(
            mirror,
            data=body,
            headers={
                "User-Agent": "LBX-public-POI-research/1.0 (public-data compilation)",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=240) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                return mirror, data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(3)
    raise RuntimeError(f"All Overpass mirrors failed: {last_error!r}")


def point(el: dict[str, Any]) -> tuple[float | None, float | None]:
    if "lat" in el and "lon" in el:
        return el.get("lat"), el.get("lon")
    center = el.get("center") or {}
    return center.get("lat"), center.get("lon")


def tag(tags: dict[str, Any], *names: str) -> str:
    for name in names:
        value = tags.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def build_address(tags: dict[str, Any]) -> str:
    full = tag(tags, "addr:full")
    if full:
        return full
    parts = [
        tag(tags, "addr:province"),
        tag(tags, "addr:city"),
        tag(tags, "addr:district", "addr:county"),
        tag(tags, "addr:subdistrict", "addr:town", "addr:village"),
        tag(tags, "addr:street", "addr:place"),
        tag(tags, "addr:housenumber"),
        tag(tags, "addr:unit"),
    ]
    return "".join(p for p in parts if p)


def main() -> None:
    all_elements: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for idx, pattern in enumerate(PATTERNS, start=1):
        query = f'''[out:json][timeout:180];
area["ISO3166-1"="CN"][admin_level=2]->.cn;
(
  nwr["name"~"{pattern}",i](area.cn);
  nwr["brand"~"{pattern}",i](area.cn);
  nwr["operator"~"{pattern}",i](area.cn);
);
out center tags;'''
        try:
            mirror, data = post_overpass(query)
            elements = data.get("elements", [])
            all_elements.extend(elements)
            reports.append({"pattern": pattern, "mirror": mirror, "count": len(elements), "error": ""})
        except Exception as exc:  # noqa: BLE001
            reports.append({"pattern": pattern, "mirror": "", "count": 0, "error": repr(exc)})
        time.sleep(4)

    dedup: dict[tuple[str, int], dict[str, Any]] = {}
    for el in all_elements:
        key = (str(el.get("type", "")), int(el.get("id", 0)))
        dedup[key] = el

    rows: list[dict[str, Any]] = []
    for (osm_type, osm_id), el in dedup.items():
        tags = el.get("tags") or {}
        lat, lon = point(el)
        name = tag(tags, "name", "brand")
        if not name:
            continue
        rows.append(
            {
                "store_name": name,
                "province": tag(tags, "addr:province"),
                "city": tag(tags, "addr:city"),
                "district": tag(tags, "addr:district", "addr:county"),
                "address": build_address(tags),
                "phone": tag(tags, "contact:phone", "phone"),
                "opening_hours": tag(tags, "opening_hours"),
                "brand": tag(tags, "brand"),
                "operator": tag(tags, "operator"),
                "latitude_wgs84": lat,
                "longitude_wgs84": lon,
                "osm_type": osm_type,
                "osm_id": osm_id,
                "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                "source": "OpenStreetMap/Overpass",
                "verification_level": "公开地图待核验",
            }
        )

    rows.sort(key=lambda r: (r["province"], r["city"], r["district"], r["store_name"], r["osm_id"]))
    fields = list(rows[0].keys()) if rows else [
        "store_name", "province", "city", "district", "address", "phone",
        "opening_hours", "brand", "operator", "latitude_wgs84", "longitude_wgs84",
        "osm_type", "osm_id", "source_url", "source", "verification_level",
    ]
    with (OUT / "lbx_osm_pois.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    (OUT / "lbx_osm_pois.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "row_count": len(rows),
        "queries": reports,
        "note": "Supplementary public-map data; not an official full LBX store master.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
