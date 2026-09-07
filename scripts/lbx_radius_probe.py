#!/usr/bin/env python3
from __future__ import annotations
import json, requests
from math import radians, sin, cos, asin, sqrt

URL='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*','Referer':'https://yx.lbxcn.com/h5/springgame/index.html'})
points={
 'changsha_center':(28.2282,112.9388),
 'changsha_west_72km':(28.2282,112.2000),
 'changsha_north_75km':(28.9000,112.9388),
 'changsha_far_west_105km':(28.2282,111.8500),
 'lanzhou_west_93km':(36.0611,102.8000),
 'beijing_northwest_70km':(40.40,115.85),
 'shandong_sparse':(36.8,117.0),
}
for name,(lat,lng) in points.items():
 try:
  r=S.get(URL,params={'Latitude':lat,'Longitude':lng},timeout=30); o=r.json(); rows=o.get('data',{}).get('data',[])
  print(json.dumps({'name':name,'lat':lat,'lng':lng,'status':r.status_code,'count':len(rows),'distances':[x.get('distance') for x in rows],'names':[x.get('deptName') for x in rows],'coords':[[x.get('latGd'),x.get('lngGd')] for x in rows]},ensure_ascii=False),flush=True)
 except Exception as e: print(json.dumps({'name':name,'error':repr(e)},ensure_ascii=False),flush=True)
