#!/usr/bin/env python3
from __future__ import annotations
import json, time
from pathlib import Path
import requests

OUT=Path('wrapper_fast_output'); OUT.mkdir(exist_ok=True)
headers={
 'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.56',
 'Accept':'application/json,text/javascript,*/*;q=0.01',
 'Referer':'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4',
 'X-Requested-With':'XMLHttpRequest'
}
urls=[
 'https://yx.lbxcn.com/out/2026api/getlbxStoreList',
 'https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
]
tests=[
 ('changsha', {'Latitude':28.228304,'Longitude':112.938882}),
 ('xian', {'Latitude':34.343207,'Longitude':108.939645}),
 ('beijing', {'Latitude':39.904179,'Longitude':116.407387}),
 ('zero', {'Latitude':0,'Longitude':0}),
 ('missing', {}),
]

def find_rows(x):
 if isinstance(x,list): return x
 if isinstance(x,dict):
  for k in ('rows','records','list'):
   if isinstance(x.get(k),list): return x[k]
  d=x.get('data')
  if isinstance(d,list): return d
  if isinstance(d,dict):
   for k in ('rows','records','list','data'):
    if isinstance(d.get(k),list): return d[k]
 return None

report=[]
for u in urls:
 for name,p in tests:
  rec={'endpoint':u,'test':name,'params':p}
  try:
   t=time.time(); r=requests.get(u,params=p,headers=headers,timeout=15)
   rec.update(status=r.status_code,url=r.url,length=len(r.content),content_type=r.headers.get('content-type'),elapsed=round(time.time()-t,3),preview=r.text[:1200])
   try:
    data=r.json(); rows=find_rows(data)
    rec['json_keys']=list(data) if isinstance(data,dict) else None
    rec['row_count']=len(rows) if isinstance(rows,list) else None
    rec['row_keys']=sorted({k for x in (rows or [])[:100] if isinstance(x,dict) for k in x})
    rec['sample']=(rows or [])[:5]
    (OUT/f"{urls.index(u)}_{name}.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
   except Exception as e: rec['json_error']=repr(e)
  except Exception as e: rec['error']=repr(e)
  report.append(rec); print(json.dumps(rec,ensure_ascii=False)[:4000],flush=True)
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'compact.txt').write_text('\n'.join(f"{x.get('endpoint')}\t{x.get('test')}\tstatus={x.get('status')}\trows={x.get('row_count')}\tkeys={x.get('row_keys')}\tpreview={x.get('preview','')[:300]}" for x in report),encoding='utf-8')
