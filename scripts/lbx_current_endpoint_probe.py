#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

OUT = Path('lbx_current_endpoint_probe')
OUT.mkdir(exist_ok=True)
S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4',
})
ENDPOINTS={
    'current':'https://yx.lbxcn.com/out/2026api/getlbxStoreList',
    'legacy':'https://yx.lbxcn.com/out/2212sping/getlbxStoreList',
}


def find_lists(obj, path='$', depth=0):
    if depth>5: return []
    out=[]
    if isinstance(obj,list):
        out.append({'path':path,'length':len(obj),'sample':obj[:2]})
        for i,x in enumerate(obj[:2]): out += find_lists(x,f'{path}[{i}]',depth+1)
    elif isinstance(obj,dict):
        for k,v in obj.items(): out += find_lists(v,f'{path}.{k}',depth+1)
    return out


def request(name, endpoint, params):
    rec={'name':name,'endpoint':endpoint,'params':params}
    t=time.time()
    try:
        r=S.get(endpoint,params=params,timeout=25,allow_redirects=True)
        rec.update({'status':r.status_code,'url':r.url,'length':len(r.content),'content_type':r.headers.get('content-type'),'elapsed':round(time.time()-t,3)})
        (OUT/f'{name}.txt').write_bytes(r.content)
        try:
            data=r.json()
            rec['top_keys']=list(data.keys()) if isinstance(data,dict) else None
            rec['lists']=find_lists(data)
            (OUT/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as e:
            rec['json_error']=repr(e); rec['preview']=r.text[:1200]
    except Exception as e:
        rec['error']=repr(e); rec['elapsed']=round(time.time()-t,3)
    print(json.dumps(rec,ensure_ascii=False,indent=2)[:25000],flush=True)
    return rec


def main():
    points={
        'shanghai':(31.2304,121.4737),
        'changsha':(28.2283,112.9389),
        'wuhan':(30.5928,114.3055),
        'xian':(34.3416,108.9398),
        'remote_lhasa':(29.6520,91.1721),
        'remote_urumqi':(43.8256,87.6168),
        'zero':(0.0,0.0),
    }
    variants=[
        ('base',{}),
        ('page_size',{'page':1,'size':1000}),
        ('pageNo_pageSize',{'pageNo':1,'pageSize':1000}),
        ('pn_rn',{'pn':0,'rn':1000}),
        ('limit',{'limit':1000}),
        ('rows',{'rows':1000}),
        ('radius',{'radius':10000000}),
        ('distance',{'distance':10000000}),
    ]
    report=[]
    for ek,endpoint in ENDPOINTS.items():
        for pname,(lat,lng) in points.items():
            report.append(request(f'{ek}_{pname}_base',endpoint,{'Latitude':lat,'Longitude':lng}))
        for vname,extra in variants[1:]:
            params={'Latitude':28.2283,'Longitude':112.9389,**extra}
            report.append(request(f'{ek}_changsha_{vname}',endpoint,params))
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
