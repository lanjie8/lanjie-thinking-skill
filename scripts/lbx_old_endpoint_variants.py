#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures,json,time
from pathlib import Path
import requests
OUT=Path('old_endpoint_variants_output');OUT.mkdir(exist_ok=True)
URL='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
H={'User-Agent':'Mozilla/5.0','Accept':'application/json, text/javascript, */*; q=0.01','Referer':'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4','X-Requested-With':'XMLHttpRequest'}
lat,lng=28.228304,112.938882
BASE={'Latitude':lat,'Longitude':lng}
V={
'base':{},'size1':{'size':1},'size5':{'size':5},'size20':{'size':20},'size100':{'size':100},'limit100':{'limit':100},'pageSize100':{'pageSize':100},'pagesize100':{'pagesize':100},'rows100':{'rows':100},'page1':{'page':1},'page2':{'page':2},'pageNum2':{'pageNum':2},'pagenum2':{'pagenum':2},'radius1':{'radius':1},'radius5':{'radius':5},'radius20':{'radius':20},'radius100':{'radius':100},'Radius100':{'Radius':100},'distance100':{'distance':100},'Distance100':{'Distance':100},'page2_size100':{'page':2,'size':100},'pageNum2_pageSize100':{'pageNum':2,'pageSize':100},'offset10_limit100':{'offset':10,'limit':100},'start10_rows100':{'start':10,'rows':100}}
def one(kv):
 n,x=kv;p=BASE|x;t=time.time()
 try:
  r=requests.get(URL,params=p,headers=H,timeout=20);o=r.json();s=o.get('data',{}).get('data',[]) if isinstance(o,dict) else []
  return {'name':n,'params':p,'status':r.status_code,'count':len(s) if isinstance(s,list) else None,'ids':[str(z.get('shop_id','')) for z in s] if isinstance(s,list) else [],'max_distance':max([float(z.get('distanceGd') or z.get('distance')) for z in s if z.get('distanceGd') or z.get('distance')],default=None),'elapsed':round(time.time()-t,3),'json':o}
 except Exception as e:return {'name':n,'params':p,'error':repr(e),'elapsed':round(time.time()-t,3)}
def main():
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:rows=list(ex.map(one,V.items()))
 rows.sort(key=lambda r:list(V).index(r['name']))
 (OUT/'variants.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 cols=['name','status','count','max_distance','ids','elapsed','error'];lines=['\t'.join(cols)]
 for r in rows:lines.append('\t'.join(json.dumps(r.get(c,''),ensure_ascii=False) if isinstance(r.get(c),(list,dict)) else str(r.get(c,'') or '') for c in cols))
 (OUT/'variants.tsv').write_text('\n'.join(lines),encoding='utf-8');print('\n'.join(lines))
if __name__=='__main__':main()
