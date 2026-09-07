#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path
from typing import Any, Iterable

import requests

OUT = Path('county_seed_output')
OUT.mkdir(exist_ok=True)
BASE = 'https://geo.datav.aliyun.com/areas_v3/bound/'
MARKETS = {
    '120000': '天津', '140000': '山西', '150000': '内蒙古', '310000': '上海',
    '320000': '江苏', '330000': '浙江', '340000': '安徽', '360000': '江西',
    '370000': '山东', '410000': '河南', '420000': '湖北', '430000': '湖南',
    '440000': '广东', '450000': '广西', '520000': '贵州', '610000': '陕西',
    '620000': '甘肃', '640000': '宁夏',
}
H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
    'Accept': 'application/geo+json,application/json,text/plain,*/*',
    'Referer': 'https://datav.aliyun.com/',
}
S = requests.Session(); S.headers.update(H)


def fetch(code: str, full: bool = True) -> dict[str, Any] | None:
    suffix = '_full.json' if full else '.json'
    url = BASE + code + suffix
    for attempt in range(4):
        try:
            r = S.get(url, timeout=(8, 25))
            if r.status_code == 200 and 'json' in (r.headers.get('content-type') or '').lower():
                return r.json()
            if r.status_code == 200 and r.text.lstrip().startswith('{'):
                return r.json()
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(0.8 * (attempt + 1))
    return None


def iter_coords(geometry: Any) -> Iterable[tuple[float, float]]:
    if not isinstance(geometry, dict):
        return
    stack = [geometry.get('coordinates')]
    while stack:
        x = stack.pop()
        if isinstance(x, (list, tuple)):
            if len(x) >= 2 and isinstance(x[0], (int, float)) and isinstance(x[1], (int, float)):
                yield float(x[0]), float(x[1])
            else:
                stack.extend(x)


def geometry_bbox_center(geometry: Any) -> tuple[float, float] | None:
    coords = list(iter_coords(geometry))
    coords = [(x, y) for x, y in coords if 70 <= x <= 140 and 10 <= y <= 60]
    if not coords:
        return None
    xs = [x for x, _ in coords]; ys = [y for _, y in coords]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def point_from_feature(feature: dict[str, Any]) -> tuple[float, float] | None:
    p = feature.get('properties') or {}
    for key in ('center', 'centroid'):
        v = p.get(key)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            try:
                x, y = float(v[0]), float(v[1])
                if 70 <= x <= 140 and 10 <= y <= 60:
                    return x, y
            except Exception:
                pass
    return geometry_bbox_center(feature.get('geometry'))


def feature_row(feature: dict[str, Any], province_code: str, province: str, parent_code: str, parent_name: str) -> dict[str, Any] | None:
    p = feature.get('properties') or {}
    adcode = str(p.get('adcode') or '').strip()
    name = str(p.get('name') or '').strip()
    point = point_from_feature(feature)
    if len(adcode) != 6 or not adcode.isdigit() or not name or not point:
        return None
    level = str(p.get('level') or '').strip().lower()
    if not level:
        level = 'province' if adcode.endswith('0000') else ('city' if adcode.endswith('00') else 'district')
    return {
        'province_code': province_code,
        'province': province,
        'parent_code': parent_code,
        'parent_name': parent_name,
        'adcode': adcode,
        'name': name,
        'level': level,
        'longitude': point[0],
        'latitude': point[1],
        'center_source': 'properties.center/centroid_or_bbox',
    }


def main():
    rows: dict[str, dict[str, Any]] = {}
    failures = []
    for province_code, province in MARKETS.items():
        print('PROVINCE', province_code, province, flush=True)
        data = fetch(province_code, True)
        if not data:
            failures.append({'code': province_code, 'name': province, 'stage': 'province_full'})
            continue
        features = data.get('features') or []
        city_rows = []
        for f in features:
            row = feature_row(f, province_code, province, province_code, province)
            if row:
                rows[row['adcode']] = row
                city_rows.append(row)
        # In a direct-controlled municipality, province_full may already contain districts.
        for city in city_rows:
            code = city['adcode']
            if not code.endswith('00') or code == province_code:
                continue
            child = fetch(code, True)
            if child is None:
                failures.append({'code': code, 'name': city['name'], 'stage': 'city_full'})
                continue
            for f in child.get('features') or []:
                row = feature_row(f, province_code, province, code, city['name'])
                if row:
                    rows[row['adcode']] = row
            time.sleep(0.04)
        time.sleep(0.08)

    data_rows = sorted(rows.values(), key=lambda r: (r['province_code'], r['adcode']))
    # Retain every city/district seed plus a few deterministic offsets. Offsets help when
    # the administrative center falls in a low-density/new-development area.
    expanded = []
    offsets = [(0, 0), (0.035, 0), (-0.035, 0), (0, 0.035), (0, -0.035)]
    for row in data_rows:
        for i, (dx, dy) in enumerate(offsets):
            r = dict(row)
            r['seed_variant'] = i
            r['longitude'] = round(float(row['longitude']) + dx, 6)
            r['latitude'] = round(float(row['latitude']) + dy, 6)
            expanded.append(r)

    fields = ['province_code','province','parent_code','parent_name','adcode','name','level','longitude','latitude','center_source','seed_variant']
    for filename, records in [('county_city_seeds.csv', data_rows), ('expanded_seeds.csv', expanded)]:
        with (OUT / filename).open('w', newline='', encoding='utf-8-sig') as fp:
            w = csv.DictWriter(fp, fieldnames=fields)
            w.writeheader(); w.writerows(records)
    (OUT / 'county_city_seeds.json').write_text(json.dumps(data_rows, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {
        'unique_seed_areas': len(data_rows),
        'expanded_seed_points': len(expanded),
        'levels': {},
        'province_counts': {},
        'failures': failures,
    }
    for r in data_rows:
        summary['levels'][r['level']] = summary['levels'].get(r['level'], 0) + 1
        summary['province_counts'][r['province']] = summary['province_counts'].get(r['province'], 0) + 1
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
