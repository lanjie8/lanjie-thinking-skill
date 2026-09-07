#!/usr/bin/env python3
from __future__ import annotations
import asyncio, json, time
from pathlib import Path
from urllib.parse import urlencode
import requests
from playwright.async_api import async_playwright

OUT=Path('fast_map_probe_output'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

def b_url(c='158',pn=0,kw='老百姓大药房'):
    return 'https://map.baidu.com/?'+urlencode({'newmap':'1','reqflag':'pcmap','biz':'1','from':'webmap','qt':'s','da_src':'searchBox.button','wd':kw,'c':c,'pn':str(pn),'nn':str(pn*10),'sug':'0','l':'12','ie':'utf-8','oue':'1'})

def a_url(city='430100',p=1,kw='老百姓大药房'):
    return 'https://www.amap.com/service/poiInfo?'+urlencode({'query_type':'TQUERY','pagesize':'20','pagenum':str(p),'qii':'true','cluster_state':'5','need_utd':'true','utd_sceneid':'1000','div':'PC1000','addr_poi_merge':'true','is_classify':'true','zoom':'10','city':city,'keywords':kw})

def save(name,text): (OUT/name).write_text(text,encoding='utf-8')

def direct(name,url,ref):
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Referer':ref,'Accept':'application/json,text/plain,*/*'},timeout=30)
        save(name+'.txt',r.text)
        return {'name':name,'status':r.status_code,'length':len(r.content),'preview':r.text[:1800]}
    except Exception as e: return {'name':name,'error':repr(e)}

async def main():
    report=[]
    report.append(direct('baidu_direct',b_url(),'https://map.baidu.com/'))
    report.append(direct('baidu_national_direct',b_url('1'),'https://map.baidu.com/'))
    report.append(direct('amap_direct',a_url(),'https://www.amap.com/'))
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        ctx=await browser.new_context(user_agent=UA,locale='zh-CN',viewport={'width':1440,'height':1000})
        page=await ctx.new_page()
        for provider,home,url in [('baidu','https://map.baidu.com/',b_url()),('amap','https://www.amap.com/',a_url())]:
            try:
                await page.goto(home,wait_until='domcontentloaded',timeout=60000)
                await page.wait_for_timeout(5000)
                result=await page.evaluate("""async u=>{const r=await fetch(u,{credentials:'include'});return {status:r.status,url:r.url,body:await r.text(),cookies:document.cookie};}""",url)
                save(provider+'_browser.json',json.dumps(result,ensure_ascii=False,indent=2))
                report.append({'name':provider+'_browser','status':result['status'],'length':len(result['body']),'preview':result['body'][:1800],'cookies_len':len(result.get('cookies',''))})
            except Exception as e:
                report.append({'name':provider+'_browser','error':repr(e)})
        await browser.close()
    save('report.json',json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': asyncio.run(main())
