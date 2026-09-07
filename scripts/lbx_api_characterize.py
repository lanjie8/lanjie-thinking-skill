#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import requests

OUT = Path('api_characterize_output')
OUT.mkdir(exist_ok=True)
S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4',
})

BASE = 'https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
POINT = {'Latitude': 31.2304, 'Longitude': 121.4737}
DIRECTS = [
    'https://msapitest.lbxcn.com:31443/sems-store/nearby/store/pageNearbyStore',
    'https://msapitest.lbxcn.com/sems-store/nearby/store/pageNearbyStore',
    'https://msapi.lbxcn.com:31443/sems-store/nearby/store/pageNearbyStore',
    'https://msapi.lbxcn.com/sems-store/nearby/store/pageNearbyStore',
]


def extract_rows(data):
    try:
        if isinstance(data, dict) and isinstance(data.get('data'), dict):
            inner = data['data']
            if isinstance(inner.get('data'), list): return inner['data']
            if isinstance(inner.get('rows'), list): return inner['rows']
        if isinstance(data, dict) and isinstance(data.get('rows'), list): return data['rows']
    except Exception:
        pass
    return []


def summary(r, data=None):
    rec = {
        'status': r.status_code,
        'content_type': r.headers.get('content-type'),
        'length': len(r.content),
        'preview': r.text[:2000],
    }
    if data is not None:
        rec['json_type'] = type(data).__name__
        if isinstance(data, dict): rec['keys'] = list(data.keys())
        rows = extract_rows(data)
        rec['row_count'] = len(rows)
        if rows:
            rec['first'] = rows[0]
            rec['last'] = rows[-1]
            try: rec['max_distance'] = max(float(x.get('distance') or x.get('distanceGd') or 0) for x in rows)
            except Exception: pass
    return rec


def main():
    report = {'legacy_variants': [], 'direct_endpoints': [], 'dns': {}}
    variants = [
        {},
        {'page': 1, 'size': 100, 'radius': 100},
        {'pageNo': 1, 'pageSize': 100, 'radius': 100},
        {'limit': 100, 'radius': 100},
        {'size': 5, 'radius': 1},
        {'size': 50, 'radius': 5},
        {'size': 50, 'radius': 20},
        {'size': 50, 'radius': 200},
    ]
    for extra in variants:
        params = POINT | extra
        item = {'params': params}
        try:
            r = S.get(BASE, params=params, timeout=30)
            try: data = r.json()
            except Exception: data = None
            item.update(summary(r, data))
        except Exception as e: item['error'] = repr(e)
        report['legacy_variants'].append(item)
        print('LEGACY', json.dumps(item, ensure_ascii=False)[:5000], flush=True)
        time.sleep(.4)

    payloads = [
        {'latitude':'31.2304','longitude':'121.4737','page':1,'size':5,'formatIdList':['01','20','92'],'isClosed':0,'isParent':1,'radius':100},
        {'latitude':'31.2304','longitude':'121.4737','page':1,'size':100,'formatIdList':['01','20','92'],'isClosed':0,'isParent':1,'radius':100},
        {'latitude':'31.2304','longitude':'121.4737','page':1,'size':1000,'formatIdList':['01','20','92'],'isClosed':0,'isParent':1,'radius':1000},
    ]
    for url in DIRECTS:
        host = requests.utils.urlparse(url).hostname
        try: report['dns'][host] = socket.gethostbyname_ex(host)[2]
        except Exception as e: report['dns'][host] = {'error':repr(e)}
        for payload in payloads:
            item = {'url': url, 'payload': payload}
            try:
                r = S.post(url, json=payload, timeout=30, verify=True)
                try: data = r.json()
                except Exception: data = None
                item.update(summary(r, data))
            except Exception as e: item['error'] = repr(e)
            report['direct_endpoints'].append(item)
            print('DIRECT', json.dumps(item, ensure_ascii=False)[:5000], flush=True)
            time.sleep(.4)

    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()

# Triggered again on 2026-09-07 for nationwide-crawl preparation.
