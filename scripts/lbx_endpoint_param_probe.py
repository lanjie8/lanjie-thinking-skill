#!/usr/bin/env python3
from __future__ import annotations
import json, requests

URL='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
S=requests.Session()
S.headers.update({'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*','Referer':'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4','X-Requested-With':'XMLHttpRequest'})
CASES={
'no_params':{},
'zero':{'Latitude':0,'Longitude':0},
'normal':{'Latitude':28.2282,'Longitude':112.9388},
'page_size':{'Latitude':28.2282,'Longitude':112.9388,'pageSize':1000,'pageNum':1},
'limit':{'Latitude':28.2282,'Longitude':112.9388,'limit':1000},
'distance':{'Latitude':28.2282,'Longitude':112.9388,'distance':999999},
'lowercase':{'latitude':28.2282,'longitude':112.9388,'pageSize':1000},
}
def extract(d):
    x=d
    for _ in range(5):
        if isinstance(x,list): return x
        if not isinstance(x,dict): return []
        if isinstance(x.get('data'),list): return x['data']
        x=x.get('data')
    return []
for name,p in CASES.items():
    try:
        r=S.get(URL,params=p,timeout=30); d=r.json(); rows=extract(d)
        print(json.dumps({'case':name,'status':r.status_code,'url':r.url,'rows':len(rows),'keys':list(d) if isinstance(d,dict) else None,'preview':d},ensure_ascii=False)[:120000])
    except Exception as e: print(json.dumps({'case':name,'error':repr(e)},ensure_ascii=False))
