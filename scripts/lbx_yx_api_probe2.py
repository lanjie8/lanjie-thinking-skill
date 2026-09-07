#!/usr/bin/env python3
from __future__ import annotations
import json, time
from pathlib import Path
import requests

OUT=Path('yx_api_probe_output'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
    'Accept':'application/json,text/plain,*/*',
    'Referer':'https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4',
})
coords={
    'changsha_center':(28.2282,112.9388),
    'changsha_east':(28.1960,113.0820),
    'beijing':(39.9042,116.4074),
    'xian':(34.3416,108.9398),
    'nanjing':(32.0603,118.7969),
    'hangzhou':(30.2741,120.1551),
    'lanzhou':(36.0611,103.8343),
    'hohhot':(40.8426,111.7492),
    'nanning':(22.8170,108.3665),
    'remote_hunan':(27.55,110.0),
}
endpoints=['https://yx.lbxcn.com/out/2026api/getlbxStoreList','https://yx.lbxcn.com/out/2212sping/getlbxStoreList']
results=[]
for ep in endpoints:
    for name,(lat,lon) in coords.items():
        try:
            r=S.get(ep,params={'Latitude':lat,'Longitude':lon},timeout=30)
            text=r.text
            item={'endpoint':ep,'name':name,'request_url':r.url,'status':r.status_code,'content_type':r.headers.get('content-type'),'length':len(r.content),'text':text}
            try: item['json']=r.json()
            except Exception: pass
        except Exception as e:
            item={'endpoint':ep,'name':name,'error':repr(e)}
        results.append(item)
        print(json.dumps({k:v for k,v in item.items() if k not in ('text','json')},ensure_ascii=False),flush=True)
        if 'json' in item:
            print(json.dumps(item['json'],ensure_ascii=False)[:2500],flush=True)
        time.sleep(.4)
(OUT/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
