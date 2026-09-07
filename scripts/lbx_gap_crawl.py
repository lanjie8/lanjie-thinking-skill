#!/usr/bin/env python3
"""Gap-fill crawl for LBX stores outside the 18 half-year-report markets.

Uses all known prefecture/province centers plus a variable-density grid, then
reuses the same nearest-store graph traversal and physical-store deduplication
as the main crawl.
"""
from __future__ import annotations

import csv
from pathlib import Path

import lbx_fast_bfs_crawl as base

base.OUT = Path("lbx_gap_output")
base.OUT.mkdir(exist_ok=True)

GAPS = {
    "北京": (39.3, 41.1, 115.4, 117.6, 0.25),
    "河北": (36.0, 42.7, 113.5, 119.9, 0.50),
    "辽宁": (38.7, 43.5, 118.8, 125.8, 0.50),
    "吉林": (40.8, 46.3, 121.6, 131.3, 0.50),
    "黑龙江": (43.4, 53.6, 121.1, 135.2, 0.80),
    "福建": (23.5, 28.4, 115.8, 120.7, 0.40),
    "海南": (18.0, 20.3, 108.6, 111.2, 0.35),
    "四川": (26.0, 34.3, 97.3, 108.6, 0.50),
    "重庆": (28.1, 32.2, 105.3, 110.2, 0.40),
    "云南": (21.1, 29.3, 97.5, 106.2, 0.60),
    "西藏": (26.8, 36.5, 78.4, 99.1, 1.00),
    "青海": (31.6, 39.2, 89.3, 103.1, 0.90),
    "新疆": (34.3, 49.2, 73.4, 96.4, 1.00),
}


def gap_seeds() -> list[tuple[float, float]]:
    result: set[tuple[float, float]] = set()
    for _name, (lat0, lat1, lon0, lon1, step) in GAPS.items():
        lat = lat0
        while lat <= lat1 + 1e-9:
            lon = lon0
            while lon <= lon1 + 1e-9:
                result.add((round(lat, 6), round(lon, 6)))
                lon += step
            lat += step
        result.add((round((lat0 + lat1) / 2, 6), round((lon0 + lon1) / 2, 6)))

    city_file = Path("city_seed_output/all_city_seeds.csv")
    if city_file.exists():
        with city_file.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                province = str(row.get("province") or row.get("name") or "").strip()
                if province not in GAPS:
                    continue
                try:
                    lat = float(row.get("latitude") or "")
                    lon = float(row.get("longitude") or "")
                except ValueError:
                    continue
                if 15 <= lat <= 55 and 70 <= lon <= 140:
                    result.add((round(lat, 6), round(lon, 6)))
    return sorted(result)


base.MARKETS = {name: vals[:4] for name, vals in GAPS.items()}
base.seeds = gap_seeds

if __name__ == "__main__":
    print(f"GAP_PROVINCES {list(GAPS)}", flush=True)
    base.main()
