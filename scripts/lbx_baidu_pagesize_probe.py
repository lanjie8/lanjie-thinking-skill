#!/usr/bin/env python3
from __future__ import annotations
import json,re,time
from pathlib import Path
from urllib.parse import quote
import requests
OUT=Path('lbx_baidu_pagesize_probe'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'zh-CN,zh;q=0.9','Referer':'https://map.baidu.com/mobile/webapp/index/index/'})

def extract(text):
    m=re.search(r'createWidget\s*\(\s*',text)
    if not m: raise RuntimeError('no widget')
    return json.JSONDecoder().raw_decode(text[m.end():])[0]

def count_content(p):
    c=p.get('content') or []
    return len(c) if isinstance(c,list) else -1

def total(p):
    vals=[]
    for path in [('result','total'),('pageInfo','total'),('page_info','total'),('result','totalNum')]:
        cur=p
        for k in path:
            cur=cur.get(k) if isinstance(cur,dict) else None
        if cur not in (None,''):
            vals.append((path,cur))
    return vals

def main():
    cases=[('changsha','158'),('shanghai','289'),('wuhan','218')]
    out=[]
    for name,c in cases:
        for rn in [10,20,30,50,100]:
            for page in [0,1]:
                url=('https://map.baidu.com/mobile/webapp/place/list/'
                     f'qt=s&wd={quote("老百姓大药房")}&c={c}&pn={page}&rn={rn}'
                     '&res_x=0.000000&res_y=0.000000/showall=1')
                t=time.time()
                try:
                    r=S.get(url,timeout=30); p=extract(r.text)
                    rec={'case':name,'c':c,'rn':rn,'page':page,'status':r.status_code,'length':len(r.content),'content_count':count_content(p),'totals':total(p),'pageInfo':p.get('pageInfo'),'result':p.get('result'),'elapsed':round(time.time()-t,2)}
                except Exception as e: rec={'case':name,'c':c,'rn':rn,'page':page,'error':repr(e),'elapsed':round(time.time()-t,2)}
                out.append(rec); print(json.dumps(rec,ensure_ascii=False),flush=True)
                time.sleep(.15)
    (OUT/'report.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
