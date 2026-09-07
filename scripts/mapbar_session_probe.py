#!/usr/bin/env python3
from __future__ import annotations
import json, time
from pathlib import Path
import requests

OUT=Path('mapbar_session_probe_output'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'
SLUGS=['aba','akesu','alaer','alashanmeng','aletai','ali','ankang','anqing','anshan','anshun','anyang','baicheng','baise','baishan','baiyin','baoding','baoji','baoshan','baotou','beihai','beijing','bengbu','changsha']

def get(url, session=None):
    fn=session.get if session else requests.get
    try:
        r=fn(url,headers={'User-Agent':UA,'Connection':'close','Accept':'text/html,*/*'},timeout=20,allow_redirects=True)
        return {'requested':url,'status':r.status_code,'final':r.url,'len':len(r.content),'history':[{'status':x.status_code,'url':x.url,'location':x.headers.get('location')} for x in r.history],'cookies':dict(r.cookies),'set_cookie':r.headers.get('set-cookie'),'title':r.text[:120]}
    except Exception as e: return {'requested':url,'error':repr(e)}

def main():
    out={'same_session':[],'fresh_session':[],'plain':[],'https_fresh':[]}
    s=requests.Session()
    for slug in SLUGS[:8]:
        out['same_session'].append(get(f'http://poi.mapbar.com/{slug}/D30/',s)); time.sleep(.4)
    for slug in SLUGS:
        s=requests.Session()
        out['fresh_session'].append(get(f'http://poi.mapbar.com/{slug}/D30/',s)); s.close(); time.sleep(.4)
    for slug in SLUGS:
        out['plain'].append(get(f'http://poi.mapbar.com/{slug}/D30/')); time.sleep(.4)
    for slug in SLUGS:
        s=requests.Session()
        out['https_fresh'].append(get(f'https://poi.mapbar.com/{slug}/D30/',s)); s.close(); time.sleep(.4)
    (OUT/'report.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={k:[x.get('status') for x in v] for k,v in out.items()}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
