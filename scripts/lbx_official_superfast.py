#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures, csv, json, re, threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import requests

OUT=Path('lbx_official_superfast_output'); OUT.mkdir(exist_ok=True)
ADMIN='https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/xzqh_with_amap_coordinates.json'
API='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
PROVS={'湖南省','江苏省','安徽省','甘肃省','陕西省','广西壮族自治区','内蒙古自治区','天津市','湖北省','浙江省','山西省','河南省','山东省','上海市','宁夏回族自治区','贵州省','广东省','江西省','北京市'}
TLS=threading.local()
def sess():
    s=getattr(TLS,'s',None)
    if s is None:
        s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 Chrome/131','Accept':'application/json,text/plain,*/*','Referer':'https://yx.lbxcn.com/h5/springgame/index.html','Origin':'https://yx.lbxcn.com'}); TLS.s=s
    return s
def fl(v):
    try:return float(v)
    except:return None
def walk(tree):
    out=[]
    def rec(n,prov='',city=''):
        nonlocal out
        level=str(n.get('level') or ''); code=str(n.get('code') or ''); name=str(n.get('name') or '')
        if level=='province':prov=name
        elif level=='prefecture':city=name
        c=n.get('center') or {}; lon=fl(c.get('longitude')); lat=fl(c.get('latitude'))
        if prov in PROVS and level in {'prefecture','county'} and lon is not None and lat is not None:
            out.append({'province':prov,'city':city,'seed':name,'lat':round(lat,6),'lon':round(lon,6)})
        for ch in n.get('children') or []: rec(ch,prov,city)
    for n in tree:rec(n)
    return out
def ask(p):
    try:
        r=sess().get(API,params={'Latitude':p['lat'],'Longitude':p['lon']},timeout=(2.5,4.5)); r.raise_for_status(); rows=r.json().get('data',{}).get('data',[])
        return p, rows if isinstance(rows,list) else [], ''
    except Exception as e:return p,[],repr(e)
def key(r):
    for k in ('shop_id','sap_id','org_code'):
        v=str(r.get(k) or '').strip()
        if v:return k+':'+v
    return 'f:'+re.sub(r'\s+','',str(r.get('deptName') or ''))+'|'+re.sub(r'\s+','',str(r.get('deptAddr') or ''))
def mask(v):
    s=str(v or '').strip(); d=re.sub(r'\D','',s)
    return d[:3]+'****'+d[-4:] if len(d)==11 and d.startswith('1') else s
def main():
    tree=requests.get(ADMIN,timeout=30).json(); points=walk(tree); print('points',len(points),flush=True)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as ex:
        for i,res in enumerate(ex.map(ask,points),1):
            results.append(res)
            if i%500==0:print('done',i,flush=True)
    stores={}; meta={}
    for p,rows,err in results:
        for r in rows:
            k=key(r); stores.setdefault(k,r); meta.setdefault(k,p)
    now=datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'); out=[]
    for k,r in stores.items():
        p=meta[k]
        def ff(x):
            try:return float(x)
            except:return ''
        out.append({'官方门店键':k,'门店名称':str(r.get('deptName') or '').strip(),'上级公司':str(r.get('parentName') or '').strip(),'省份_查询归属':p['province'],'城市_接口':str(r.get('city') or '').strip(),'城市_查询归属':p['city'],'区县_最近查询点':p['seed'],'详细地址':str(r.get('deptAddr') or '').strip(),'联系电话_脱敏':mask(r.get('phone')),'门店标签':str(r.get('shopLabels') or '').strip(),'门店规模分类':str(r.get('sales_scan_name') or '').strip(),'冬季营业时间':'-'.join(x for x in [str(r.get('winter_start_hours') or ''),str(r.get('winter_closing_hours') or '')] if x),'夏季营业时间':'-'.join(x for x in [str(r.get('summer_start_hours') or ''),str(r.get('summer_closing_hours') or '')] if x),'配送时间':'-'.join(x for x in [str(r.get('shipStartTime') or ''),str(r.get('shipEndTime') or '')] if x),'经度_GCJ02':ff(r.get('lngGd') or r.get('lng')),'纬度_GCJ02':ff(r.get('latGd') or r.get('lat')),'百度经度_BD09':ff(r.get('lngBd')),'百度纬度_BD09':ff(r.get('latBd')),'shop_id':str(r.get('shop_id') or '').strip(),'sap_id':str(r.get('sap_id') or '').strip(),'companyCode':str(r.get('companyCode') or '').strip(),'org_code':str(r.get('org_code') or '').strip(),'org_name':str(r.get('org_name') or '').strip(),'third_org_code':str(r.get('third_org_code') or '').strip(),'third_org_name':str(r.get('third_org_name') or '').strip(),'is_m_shop':str(r.get('is_m_shop') or '').strip(),'is_close':str(r.get('is_close') or '').strip(),'数据源':'老百姓自有H5公开附近门店接口','来源URL':API,'抓取时间':now})
    out.sort(key=lambda x:(x['省份_查询归属'],x['城市_接口'],x['门店名称']))
    fields=list(out[0]) if out else ['门店名称']
    with (OUT/'lbx_official_quick_stores.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
    summary={'generated_at':now,'query_point_count':len(points),'success_count':sum(not e for _,_,e in results),'failure_count':sum(bool(e) for _,_,e in results),'unique_store_count':len(out),'province_counts':dict(Counter(x['省份_查询归属'] for x in out))}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
