#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path('probe_output/amap_city_list.txt')
OUT = Path('city_seed_output')
OUT.mkdir(exist_ok=True)
TARGET_PROVINCES = {
    '11': '北京', '12': '天津', '14': '山西', '15': '内蒙古',
    '31': '上海', '32': '江苏', '33': '浙江', '34': '安徽',
    '36': '江西', '37': '山东', '41': '河南', '42': '湖北',
    '43': '湖南', '44': '广东', '45': '广西', '52': '贵州',
    '61': '陕西', '62': '甘肃', '64': '宁夏',
}
# Official corporate page lists 18 operating markets and treats Beijing only as HQ,
# not an operating market. Keep Beijing candidates separately for diagnostics.
OFFICIAL_MARKETS = {
    '12': '天津', '14': '山西', '15': '内蒙古', '31': '上海', '32': '江苏',
    '33': '浙江', '34': '安徽', '36': '江西', '37': '山东', '41': '河南',
    '42': '湖北', '43': '湖南', '44': '广东', '45': '广西', '52': '贵州',
    '61': '陕西', '62': '甘肃', '64': '宁夏',
}


def walk(obj, path='$'):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f'{path}[{i}]')


def level_for(adcode: str) -> str:
    if len(adcode) != 6 or not adcode.isdigit():
        return 'unknown'
    if adcode.endswith('0000'):
        return 'province'
    if adcode.endswith('00'):
        return 'prefecture'
    return 'county'


def main():
    raw = json.loads(SRC.read_text(encoding='utf-8'))
    points = {}
    occurrences = Counter()
    paths = defaultdict(list)
    for path, d in walk(raw):
        adcode = str(d.get('adcode') or '').strip()
        x = str(d.get('x') or '').strip()
        y = str(d.get('y') or '').strip()
        name = str(d.get('name') or d.get('label') or '').strip()
        if len(adcode) != 6 or not adcode.isdigit() or not x or not y or not name:
            continue
        try:
            lon = float(x); lat = float(y)
        except ValueError:
            continue
        if not (70 <= lon <= 140 and 10 <= lat <= 60):
            continue
        occurrences[adcode] += 1
        paths[adcode].append(path)
        row = {
            'adcode': adcode,
            'name': name,
            'label': str(d.get('label') or '').strip(),
            'spell': str(d.get('spell') or '').strip(),
            'longitude': lon,
            'latitude': lat,
            'level': level_for(adcode),
            'province_code': adcode[:2],
            'province': TARGET_PROVINCES.get(adcode[:2], ''),
            'official_market': adcode[:2] in OFFICIAL_MARKETS,
            'occurrences': occurrences[adcode],
            'path': path,
        }
        existing = points.get(adcode)
        # Prefer rows with a fuller label, while preserving one unique seed per adcode.
        if existing is None or len(row['label']) > len(existing['label']):
            points[adcode] = row

    rows = sorted(points.values(), key=lambda r: r['adcode'])
    for r in rows:
        r['occurrences'] = occurrences[r['adcode']]
        r['paths'] = ' | '.join(paths[r['adcode']][:8])
    target = [r for r in rows if r['official_market']]
    diagnostics = [r for r in rows if r['province_code'] == '11']

    fields = ['adcode','name','label','spell','longitude','latitude','level','province_code','province','official_market','occurrences','path','paths']
    for name, data in [('all_city_seeds.csv', rows), ('official_market_seeds.csv', target), ('beijing_diagnostic_seeds.csv', diagnostics)]:
        with (OUT / name).open('w', encoding='utf-8-sig', newline='') as fp:
            w = csv.DictWriter(fp, fieldnames=fields)
            w.writeheader(); w.writerows(data)
    (OUT / 'official_market_seeds.json').write_text(json.dumps(target, ensure_ascii=False, indent=2), encoding='utf-8')

    by_province = defaultdict(Counter)
    for r in target:
        by_province[r['province']][r['level']] += 1
    summary = {
        'all_unique_adcodes': len(rows),
        'official_market_seeds': len(target),
        'official_market_level_counts': Counter(r['level'] for r in target),
        'province_counts': {k: dict(v) for k, v in sorted(by_province.items())},
        'sample_first': target[:20],
        'sample_last': target[-20:],
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
