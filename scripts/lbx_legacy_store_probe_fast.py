#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

OUT = Path('lbx_legacy_store_probe_fast')
OUT.mkdir(exist_ok=True)
S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4',
})
BASE='https://yx.lbxcn.com/out/2212sping/getlbxStoreList'


def summarize(data):
    out={'type':type(data).__name__}
    if isinstance(data,dict):
        out['keys']=list(data.keys())
        for path in [('data',),('data','data'),('data','rows'),('rows',),('records',),('list',)]:
            cur=data
            ok=True
            for k in path:
                if isinstance(cur,dict) and k in cur: cur=cur[k]
                else: ok=False; break
            if ok:
                out['.'.join(path)]={'type':type(cur).__name__,'length':len(cur) if hasattr(cur,'__len__') else None,'sample':cur[:2] if isinstance(cur,list) else cur}
    return out


def request(name, method='GET', params=None, payload=None, timeout=15):
    rec={'name':name,'method':method,'params':params,'payload':payload}
    started=time.time()
    try:
        r=S.request(method,BASE,params=params,json=payload,timeout=timeout,allow_redirects=True)
        rec.update({'status':r.status_code,'url':r.url,'content_type':r.headers.get('content-type'),'length':len(r.content),'elapsed':round(time.time()-started,3)})
        (OUT/f'{name}.txt').write_bytes(r.content)
        try:
            data=r.json(); rec['json']=summarize(data)
            (OUT/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as e:
            rec['json_error']=repr(e); rec['preview']=r.text[:2000]
    except Exception as e:
        rec['error']=repr(e); rec['elapsed']=round(time.time()-started,3)
    print(json.dumps(rec,ensure_ascii=False,indent=2)[:20000],flush=True)
    return rec


def crawl_page_assets():
    result={'pages':[],'scripts':[]}
    urls=[
      'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4',
      'https://yx.lbxcn.com/h5/springgame/',
      'https://yx.lbxcn.com/h5/springgame/index.html',
    ]
    for url in urls:
        try:
            r=S.get(url,timeout=20)
            rec={'url':url,'status':r.status_code,'final_url':r.url,'length':len(r.content),'preview':r.text[:500]}
            result['pages'].append(rec)
            fn=OUT/('page_'+str(len(result['pages']))+'.html'); fn.write_bytes(r.content)
            for src in re.findall(r'<script[^>]+src=["\']([^"\']+)',r.text,re.I):
                full=urljoin(r.url,src)
                if any(x.get('url')==full for x in result['scripts']): continue
                try:
                    sr=S.get(full,timeout=20)
                    srec={'url':full,'status':sr.status_code,'length':len(sr.content)}
                    text=sr.text
                    hits=[]
                    for pat in ['getlbxStoreList','pageNearbyStore','sems-store','Latitude','Longitude','radius','formatIdList']:
                        if pat in text: hits.append(pat)
                    srec['hits']=hits
                    idx=min([text.find(h) for h in hits if text.find(h)>=0] or [-1])
                    if idx>=0: srec['context']=text[max(0,idx-3000):idx+8000]
                    result['scripts'].append(srec)
                    (OUT/f'asset_{len(result["scripts"]):03d}.js').write_bytes(sr.content)
                except Exception as e: result['scripts'].append({'url':full,'error':repr(e)})
        except Exception as e: result['pages'].append({'url':url,'error':repr(e)})
    return result


def main():
    report={'requests':[]}
    points={
      'shanghai':(31.2304,121.4737),
      'changsha':(28.2283,112.9389),
      'wuhan':(30.5928,114.3055),
      'xian':(34.3416,108.9398),
    }
    variants=[
      {},
      {'page':1,'size':5},
      {'page':1,'size':100},
      {'pageNo':1,'pageSize':100},
      {'page':1,'size':1000,'radius':1000},
      {'limit':1000,'radius':1000},
    ]
    for pname,(lat,lon) in points.items():
        for i,extra in enumerate(variants):
            params={'Latitude':lat,'Longitude':lon,**extra}
            report['requests'].append(request(f'{pname}_{i:02d}',params=params,timeout=15))
    report['assets']=crawl_page_assets()
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
