#!/usr/bin/env python3
from __future__ import annotations
import json, requests, time

S=requests.Session(); S.headers.update({
 'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
 'Accept':'application/json,text/plain,*/*',
 'Referer':'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4',
})
OLD='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
coords={'changsha':(28.2282,112.9388),'xian':(34.3416,108.9398),'nanjing':(32.0603,118.7969),'beijing':(39.9042,116.4074),'rural':(27.55,110.0)}

def rows_from(obj):
 try:return obj['data']['data']
 except Exception:return []

for name,(lat,lon) in coords.items():
 for extra in ({},{'page':2,'size':100,'radius':200},{'Page':2,'Size':100,'Radius':200}):
  try:
   r=S.get(OLD,params={'Latitude':lat,'Longitude':lon,**extra},timeout=30)
   o=r.json(); rows=rows_from(o)
   print(json.dumps({'kind':'wrapper','name':name,'extra':extra,'status':r.status_code,'count':len(rows),'ids':[x.get('shop_id') for x in rows],'distances':[x.get('distance') for x in rows],'keys':sorted(rows[0].keys()) if rows else [],'top_keys':list(o.keys())},ensure_ascii=False),flush=True)
  except Exception as e: print(json.dumps({'kind':'wrapper','name':name,'extra':extra,'error':repr(e)},ensure_ascii=False),flush=True)
  time.sleep(.25)

payload={'latitude':'28.2282','longitude':'112.9388','page':1,'size':100,'formatIdList':['01','20','92'],'isClosed':0,'isParent':1,'radius':100}
base_hosts=['https://msapi.lbxcn.com:31443','https://msapi.lbxcn.com','https://msapiprod.lbxcn.com:31443','https://api.lbxcn.com','https://msapi-prod.lbxcn.com:31443','https://msapitest.lbxcn.com:31443']
path='/sems-store/nearby/store/pageNearbyStore'
for host in base_hosts:
 try:
  r=S.post(host+path,json=payload,timeout=20)
  try:o=r.json()
  except Exception:o={'text':r.text[:1000]}
  print(json.dumps({'kind':'direct','url':host+path,'status':r.status_code,'length':len(r.content),'response':o},ensure_ascii=False)[:8000],flush=True)
 except Exception as e: print(json.dumps({'kind':'direct','url':host+path,'error':repr(e)},ensure_ascii=False),flush=True)
 time.sleep(.3)
