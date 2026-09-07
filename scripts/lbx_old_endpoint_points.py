#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures, json, time
from pathlib import Path
import requests

OUT=Path('old_endpoint_points_output'); OUT.mkdir(exist_ok=True)
URL='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
H={'User-Agent':'Mozilla/5.0','Accept':'application/json, text/javascript, */*; q=0.01','Referer':'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4','X-Requested-With':'XMLHttpRequest'}
POINTS={
'长沙':(28.228304,112.938882),'株洲':(27.827433,113.134002),'岳阳':(29.357104,113.129191),'北京':(39.904179,116.407387),'上海':(31.230525,121.473667),'天津':(39.085318,117.201509),'南京':(32.059344,118.796624),'苏州':(31.299758,120.585294),'杭州':(30.246026,120.210792),'宁波':(29.868336,121.543990),'合肥':(31.820567,117.227267),'武汉':(30.593354,114.304569),'郑州':(34.746303,113.625351),'济南':(36.651216,117.120098),'青岛':(36.066938,120.382665),'西安':(34.343207,108.939645),'兰州':(36.061089,103.834303),'银川':(38.487194,106.230909),'呼和浩特':(40.842585,111.749180),'太原':(37.870590,112.548879),'贵阳':(26.647661,106.630153),'南宁':(22.817002,108.366543),'广州':(23.130061,113.264499),'深圳':(22.543527,114.057939),'南昌':(28.682892,115.858198),'沈阳':(41.677576,123.464675),'白城':(45.619026,122.838714),'成都':(30.572961,104.066301),'重庆':(29.562680,106.551787),'乌鲁木齐':(43.825592,87.616848),'拉萨':(29.652491,91.172110),'海口':(20.044220,110.199890),'昆明':(25.038859,102.718277),'三亚':(18.252847,109.511909),'漠河':(52.972272,122.538592),'东海':(30.0,130.0)}

def stores(obj):
 try:
  x=obj['data']['data']; return x if isinstance(x,list) else []
 except Exception:return []

def one(kv):
 city,(lat,lng)=kv; t=time.time()
 try:
  r=requests.get(URL,params={'Latitude':lat,'Longitude':lng},headers=H,timeout=18)
  try:o=r.json()
  except:o=None
  ss=stores(o); ds=[]
  for x in ss:
   try:ds.append(float(x.get('distanceGd') or x.get('distance')))
   except:pass
  return {'city':city,'query_lat':lat,'query_lng':lng,'status':r.status_code,'elapsed':round(time.time()-t,3),'count':len(ss),'max_distance':max(ds) if ds else None,'stores':ss,'preview':r.text[:500]}
 except Exception as e:return {'city':city,'query_lat':lat,'query_lng':lng,'elapsed':round(time.time()-t,3),'error':repr(e),'count':0,'stores':[]}

def main():
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: rows=list(ex.map(one,POINTS.items()))
 rows.sort(key=lambda x:list(POINTS).index(x['city']))
 (OUT/'points.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 cols=['city','status','count','max_distance','elapsed','error','store_ids','store_cities']
 lines=['\t'.join(cols)]
 for r in rows:
  vals={'store_ids':','.join(str(x.get('shop_id','')) for x in r['stores']),'store_cities':','.join(sorted(set(str(x.get('city','')) for x in r['stores'])))}
  lines.append('\t'.join(str((vals|r).get(c,'')).replace('\t',' ').replace('\n',' ') for c in cols))
 (OUT/'points.tsv').write_text('\n'.join(lines),encoding='utf-8')
 print('\n'.join(lines))
if __name__=='__main__':main()
