#!/usr/bin/env python3
"""Fast supplementary crawl of LBX's public nearby-store endpoint.

Uses city/county centres and one urban offset ring. It prioritizes timely
coverage and privacy-safe output; it is not an internal master-data export.
"""
from __future__ import annotations
import concurrent.futures, csv, json, re, threading, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

OUT=Path('lbx_official_quick_output'); OUT.mkdir(exist_ok=True)
ADMIN_URL='https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/xzqh_with_amap_coordinates.json'
ENDPOINT='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'
PROVINCES={'湖南省','江苏省','安徽省','甘肃省','陕西省','广西壮族自治区','内蒙古自治区','天津市','湖北省','浙江省','山西省','河南省','山东省','上海市','宁夏回族自治区','贵州省','广东省','江西省'}
_tls=threading.local()

def ses():
    s=getattr(_tls,'s',None)
    if s is None:
        s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 Chrome/131','Accept':'application/json,text/plain,*/*','Referer':'https://yx.lbxcn.com/h5/springgame/index.html','Origin':'https://yx.lbxcn.com'})
        _tls.s=s
    return s

def f(v):
    try:return float(v)
    except:return None

def center(n):
    c=n.get('center')
    if isinstance(c,dict): return f(c.get('longitude') or c.get('lng')),f(c.get('latitude') or c.get('lat'))
    if isinstance(c,str) and ',' in c:
        a,b=c.split(',',1); return f(a),f(b)
    return None,None

def admin_rows(nodes):
    out=[]
    def walk(n,prov='',city=''):
        nonlocal out
        lv=str(n.get('level') or ''); name=str(n.get('name') or ''); code=str(n.get('code') or n.get('adcode') or '')
        if lv=='province' or (len(code)==6 and code.endswith('0000')): prov=name
        elif lv in {'city','prefecture'} or (len(code)==6 and code.endswith('00') and not code.endswith('0000')): city=name
        lon,lat=center(n)
        if prov in PROVINCES and lon is not None and lat is not None: out.append({'code':code,'name':name,'level':lv,'province':prov,'city':city,'lon':lon,'lat':lat})
        ch=n.get('children') or n.get('districts') or []
        if isinstance(ch,list):
            for x in ch:
                if isinstance(x,dict): walk(x,prov,city)
    for n in nodes:
        if isinstance(n,dict):walk(n)
    return out

def points(rows):
    d={}
    for r in rows:
        code=r['code']; lv=r['level']; city=lv in {'city','prefecture'} or (len(code)==6 and code.endswith('00') and not code.endswith('0000')); county=lv in {'district','county','area'} or (len(code)==6 and not code.endswith('00'))
        if not (city or county):continue
        base={'province':r['province'],'city':r['city'],'seed':r['name'],'code':code,'kind':'行政中心'}
        key=(round(r['lat'],5),round(r['lon'],5)); d[key]={**base,'lat':key[0],'lon':key[1]}
        if county and (r['name'].endswith('区') or r['province'] in {'天津市','上海市'}):
            q=.045
            for a,b,label in [(q,0,'北'),(-q,0,'南'),(0,q,'东'),(0,-q,'西'),(q,q,'东北'),(q,-q,'西北'),(-q,q,'东南'),(-q,-q,'西南')]:
                key=(round(r['lat']+a,5),round(r['lon']+b,5)); d[key]={**base,'lat':key[0],'lon':key[1],'kind':'城区偏移'+label}
    return list(d.values())

def ask(p):
    try:
        rr=ses().get(ENDPOINT,params={'Latitude':p['lat'],'Longitude':p['lon']},timeout=9); rr.raise_for_status(); js=rr.json(); rows=js.get('data',{}).get('data',[])
        return {**p,'status':rr.status_code,'rows':rows if isinstance(rows,list) else [],'error':''}
    except Exception as e:return {**p,'status':None,'rows':[],'error':repr(e)}

def key(r):
    for k in ('shop_id','sap_id','org_code'):
        v=str(r.get(k) or '').strip()
        if v:return k+':'+v
    return 'f:'+re.sub(r'\s+','',str(r.get('deptName') or ''))+'|'+re.sub(r'\s+','',str(r.get('deptAddr') or ''))

def mask(v):
    s=str(v or '').strip(); x=re.sub(r'\D','',s)
    return x[:3]+'****'+x[-4:] if len(x)==11 and x.startswith('1') else s

def main():
    tree=requests.get(ADMIN_URL,timeout=45).json(); pts=points(admin_rows(tree)); print('points',len(pts),flush=True)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        fs=[ex.submit(ask,p) for p in pts]
        for i,fu in enumerate(concurrent.futures.as_completed(fs),1):
            results.append(fu.result())
            if i%500==0: print('done',i,'stores',len({key(s) for q in results for s in q['rows']}),flush=True)
    seen={}; meta={}
    for q in results:
        for r in q['rows']:
            k=key(r); seen.setdefault(k,r); m=meta.setdefault(k,{'count':0,'province':q['province'],'city':q['city'],'seed':q['seed'],'kind':q['kind']}); m['count']+=1
    now=datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'); rows=[]
    for k,r in seen.items():
        m=meta[k]; rows.append({'官方门店键':k,'门店名称':str(r.get('deptName') or '').strip(),'上级公司':str(r.get('parentName') or '').strip(),'省份_查询归属':m['province'],'城市_接口':str(r.get('city') or '').strip(),'城市_查询归属':m['city'],'区县_最近查询点':m['seed'],'详细地址':str(r.get('deptAddr') or '').strip(),'联系电话_脱敏':mask(r.get('phone')),'门店标签':str(r.get('shopLabels') or '').strip(),'门店规模分类':str(r.get('sales_scan_name') or '').strip(),'冬季营业时间':'-'.join(x for x in [str(r.get('winter_start_hours') or ''),str(r.get('winter_closing_hours') or '')] if x),'夏季营业时间':'-'.join(x for x in [str(r.get('summer_start_hours') or ''),str(r.get('summer_closing_hours') or '')] if x),'配送时间':'-'.join(x for x in [str(r.get('shipStartTime') or ''),str(r.get('shipEndTime') or '')] if x),'经度_GCJ02':f(r.get('lngGd') or r.get('lng')),'纬度_GCJ02':f(r.get('latGd') or r.get('lat')),'百度经度_BD09':f(r.get('lngBd')),'百度纬度_BD09':f(r.get('latBd')),'shop_id':str(r.get('shop_id') or '').strip(),'sap_id':str(r.get('sap_id') or '').strip(),'companyCode':str(r.get('companyCode') or '').strip(),'org_code':str(r.get('org_code') or '').strip(),'org_name':str(r.get('org_name') or '').strip(),'third_org_code':str(r.get('third_org_code') or '').strip(),'third_org_name':str(r.get('third_org_name') or '').strip(),'is_m_shop':str(r.get('is_m_shop') or '').strip(),'is_close':str(r.get('is_close') or '').strip(),'查询距离_公里':f(r.get('distanceGd') or r.get('distance')),'被发现次数':m['count'],'数据源':'老百姓自有H5公开附近门店接口','来源URL':ENDPOINT,'抓取时间':now})
    rows.sort(key=lambda x:(x['省份_查询归属'],x['城市_接口'] or x['城市_查询归属'],x['门店名称'],x['shop_id']))
    fields=list(rows[0]) if rows else ['门店名称']
    with (OUT/'lbx_official_quick_stores.csv').open('w',encoding='utf-8-sig',newline='') as f0:
        w=csv.DictWriter(f0,fieldnames=fields);w.writeheader();w.writerows(rows)
    (OUT/'lbx_official_quick_stores.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'generated_at':now,'query_point_count':len(pts),'success_count':sum(not q['error'] for q in results),'failure_count':sum(bool(q['error']) for q in results),'unique_store_count':len(rows),'province_counts':dict(Counter(r['省份_查询归属'] for r in rows))}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
