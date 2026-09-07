#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote

import requests

OUT=Path('jina_poi86_probe_output'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'

def fetch(name,url,headers=None):
    h={'User-Agent':UA,'Accept':'application/json','X-Timeout':'45'}
    if headers: h.update(headers)
    t=time.time()
    try:
        r=requests.get(url,headers=h,timeout=75,allow_redirects=True)
        text=r.text
        (OUT/f'{name}.txt').write_text(text,encoding='utf-8')
        out={'name':name,'url':url,'status':r.status_code,'content_type':r.headers.get('content-type'),'length':len(r.content),'elapsed':round(time.time()-t,3),'preview':text[:4000]}
        try:
            data=r.json(); out['json_type']=type(data).__name__
            if isinstance(data,dict): out['top_keys']=list(data)[:30]
            elif isinstance(data,list): out['list_count']=len(data); out['first']=data[:2]
        except Exception: pass
        return out
    except Exception as e:
        return {'name':name,'url':url,'status':None,'error':repr(e),'elapsed':round(time.time()-t,3)}

def main():
    q1=quote('老百姓大药房 site:poi86.com/poi/amap/',safe='')
    q2=quote('老百姓大药房',safe='')
    q3=quote('老百姓健康药房 site:poi86.com/poi/amap/',safe='')
    tests=[
      ('read_known_json','https://r.jina.ai/http://www.poi86.com/poi/amap/1426957.html',None),
      ('read_known_markdown','https://r.jina.ai/http://www.poi86.com/poi/amap/1426957.html',{'Accept':'text/plain'}),
      ('read_sitemap_json','https://r.jina.ai/http://www.poi86.com/sitemap.xml',None),
      ('read_robots_json','https://r.jina.ai/http://www.poi86.com/robots.txt',None),
      ('search_site_operator',f'https://s.jina.ai/{q1}',None),
      ('search_site_param',f'https://s.jina.ai/{q2}?site=poi86.com',None),
      ('search_health',f'https://s.jina.ai/{q3}',None),
    ]
    report=[]
    for name,url,h in tests:
        item=fetch(name,url,h); report.append(item)
        print(json.dumps(item,ensure_ascii=False,indent=2)[:8000],flush=True)
        time.sleep(1)
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
