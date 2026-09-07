#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.parse, urllib.request, urllib.error, http.cookiejar, ssl
from pathlib import Path

OUT=Path('baidu_quick_output'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
CJ=http.cookiejar.CookieJar()
OPENER=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ), urllib.request.HTTPSHandler(context=ssl.create_default_context()))

def req(url, accept='application/json,text/plain,*/*'):
    r=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':accept,'Accept-Language':'zh-CN,zh;q=0.9','Referer':'https://map.baidu.com/','X-Requested-With':'XMLHttpRequest'})
    try:
        with OPENER.open(r,timeout=25) as f:
            raw=f.read(); text=raw.decode('utf-8','replace')
            return {'status':f.status,'final_url':f.geturl(),'headers':dict(f.headers),'length':len(raw),'body':text}
    except urllib.error.HTTPError as e:
        text=e.read().decode('utf-8','replace')
        return {'status':e.code,'final_url':e.geturl(),'headers':dict(e.headers),'length':len(text.encode()),'body':text,'error':str(e)}
    except Exception as e: return {'status':None,'body':'','error':repr(e)}

def search_url(city='158',page=0,kw='老百姓大药房',variant=0):
    base={'qt':'s','wd':kw,'c':city,'pn':str(page),'nn':str(page*10),'ie':'utf-8','oue':'1'}
    if variant==1: base.update({'newmap':'1','reqflag':'pcmap','biz':'1','from':'webmap','da_par':'direct','pcevaname':'pc4.1','da_src':'searchBox.button','src':'0','sug':'0','l':'12','tn':'B_NORMAL_MAP'})
    if variant==2: base.update({'newmap':'1','reqflag':'pcmap','biz':'1','from':'webmap','da_src':'searchBox.button','src':'7','sug':'0','l':'12','gr':'3','on_gel':'1'})
    return 'https://map.baidu.com/?'+urllib.parse.urlencode(base)

def summary(body):
    s={'preview':body[:3000],'contains_keyword':'老百姓' in body}
    try:
        d=json.loads(body); s.update({'json':True,'type':type(d).__name__})
        if isinstance(d,dict):
            s['keys']=list(d)[:60]
            for k in ['result','content','total','current_city','place_info','poi_list','more_city']:
                if k in d:
                    v=d[k]; s[k]={'type':type(v).__name__,'length':len(v) if hasattr(v,'__len__') else None,'keys':list(v)[:30] if isinstance(v,dict) else None}
            s['json_preview']=json.dumps(d,ensure_ascii=False)[:8000]
    except Exception as e: s.update({'json':False,'parse_error':repr(e)})
    return s

def main():
    home=req('https://map.baidu.com/','text/html,*/*')
    results=[{'name':'home','status':home.get('status'),'length':home.get('length'),'error':home.get('error'),'summary':summary(home.get('body',''))}]
    for city in ['158','131','233','75','1']:
        for variant in [0,1,2]:
            u=search_url(city,0,'老百姓大药房',variant)
            r=req(u)
            results.append({'name':f'city{city}_v{variant}','request_url':u,'status':r.get('status'),'final_url':r.get('final_url'),'content_type':r.get('headers',{}).get('Content-Type'),'length':r.get('length'),'error':r.get('error'),'summary':summary(r.get('body',''))})
    (OUT/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
