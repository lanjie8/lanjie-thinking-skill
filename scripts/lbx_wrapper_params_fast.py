#!/usr/bin/env python3
from __future__ import annotations
import json,time
from pathlib import Path
import requests
OUT=Path('wrapper_params_output');OUT.mkdir(exist_ok=True)
URL='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
BASE={'Latitude':28.228304,'Longitude':112.938882}
TESTS={
 'base':{},'size50':{'size':50},'size500':{'size':500},'page2_size10':{'page':2,'size':10},
 'pageNo2_pageSize10':{'pageNo':2,'pageSize':10},'limit100':{'limit':100},
 'radius1':{'radius':1},'radius5':{'radius':5},'radius20':{'radius':20},'radius100':{'radius':100},'radius1000':{'radius':1000},
 'findAll':{'findAll':'findAll'},'alltrue':{'all':'true'},
 'lower':{'latitude':28.228304,'longitude':112.938882},
}
H={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*','Referer':'https://yx.lbxcn.com/h5/springgame/index.html'}
def rows(d):
 if isinstance(d,dict):
  d=d.get('data',d)
  if isinstance(d,dict):
   for k in ('data','rows','list','records'):
    if isinstance(d.get(k),list):return d[k]
 return []
report=[]
for name,extra in TESTS.items():
 p=dict(BASE);p.update(extra)
 # lower test should omit uppercase
 if name=='lower':p=extra
 rec={'name':name,'params':p}
 try:
  t=time.time();r=requests.get(URL,params=p,headers=H,timeout=15);d=r.json();rs=rows(d)
  rec.update(status=r.status_code,length=len(r.content),count=len(rs),ids=[x.get('shop_id') for x in rs],distances=[x.get('distance') for x in rs],first=rs[0] if rs else None,last=rs[-1] if rs else None,elapsed=round(time.time()-t,3),url=r.url)
  (OUT/f'{name}.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
 except Exception as e:rec['error']=repr(e)
 report.append(rec);print(json.dumps(rec,ensure_ascii=False)[:4000],flush=True)
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'compact.txt').write_text('\n'.join(f"{x['name']}\tcount={x.get('count')}\tids={x.get('ids')}\td={x.get('distances')}\terror={x.get('error')}" for x in report),encoding='utf-8')
