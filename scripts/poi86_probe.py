#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests

OUT = Path("poi86_probe_output")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.forms=[]; self.inputs=[]; self.scripts=[]; self.title=[]; self.in_title=False
    def handle_starttag(self, tag, attrs):
        d=dict(attrs); tag=tag.lower()
        if tag=='a' and d.get('href'): self.links.append(d['href'])
        if tag=='form': self.forms.append(d)
        if tag=='input': self.inputs.append(d)
        if tag=='script' and d.get('src'): self.scripts.append(d['src'])
        if tag=='title': self.in_title=True
    def handle_endtag(self, tag):
        if tag.lower()=='title': self.in_title=False
    def handle_data(self, data):
        if self.in_title: self.title.append(data)


def fetch(name, url, max_bytes=3_000_000):
    t=time.time()
    try:
        r=S.get(url,timeout=45,allow_redirects=True,stream=True,headers={"Referer":"https://www.poi86.com/"})
        chunks=[]; n=0
        for chunk in r.iter_content(65536):
            if not chunk: continue
            chunks.append(chunk); n+=len(chunk)
            if n>=max_bytes: break
        raw=b''.join(chunks)
        enc=r.encoding or 'utf-8'
        try: text=raw.decode(enc,errors='replace')
        except Exception: text=raw.decode('utf-8',errors='replace')
        (OUT/f"{name}.txt").write_text(text,encoding='utf-8')
        p=Parser()
        if '<html' in text[:5000].lower() or '<form' in text[:5000].lower():
            try: p.feed(text)
            except Exception: pass
        return {
            "name":name,"url":url,"status":r.status_code,"final_url":r.url,
            "content_type":r.headers.get('content-type'),"length_read":len(raw),
            "elapsed":round(time.time()-t,3),"title":' '.join(p.title).strip(),
            "forms":p.forms,"inputs":p.inputs[:50],
            "interesting_links":[urljoin(r.url,x) for x in p.links if any(k in x.lower() for k in ['search','sitemap','query','keyword','poi'])][:100],
            "scripts":[urljoin(r.url,x) for x in p.scripts[:60]],
            "preview":re.sub(r'\s+',' ',html.unescape(re.sub(r'(?s)<[^>]+>',' ',text)))[:1500]
        }
    except Exception as e:
        return {"name":name,"url":url,"status":None,"error":repr(e),"elapsed":round(time.time()-t,3)}


def main():
    q=quote_plus('老百姓大药房')
    urls=[
        ('home','https://www.poi86.com/'),
        ('robots','https://www.poi86.com/robots.txt'),
        ('sitemap','https://www.poi86.com/sitemap.xml'),
        ('sitemap_index','https://www.poi86.com/sitemap_index.xml'),
        ('sitemap_txt','https://www.poi86.com/sitemap.txt'),
        ('known','https://www.poi86.com/poi/amap/1426957.html'),
        ('search_q',f'https://www.poi86.com/search?q={q}'),
        ('search_keyword',f'https://www.poi86.com/search?keyword={q}'),
        ('search_html',f'https://www.poi86.com/search.html?keyword={q}'),
        ('amap_search',f'https://www.poi86.com/poi/amap/search?keyword={q}'),
        ('amap_search_html',f'https://www.poi86.com/poi/amap/search.html?keyword={q}'),
        ('so',f'https://www.poi86.com/so?keyword={q}'),
    ]
    report=[]
    for name,url in urls:
        item=fetch(name,url)
        report.append(item)
        print(json.dumps(item,ensure_ascii=False,indent=2)[:5000],flush=True)
        time.sleep(.8)
    # Parse all candidate JS from home for search/API endpoints.
    home_path=OUT/'home.txt'
    js_report=[]
    if home_path.exists():
        p=Parser(); p.feed(home_path.read_text(encoding='utf-8',errors='replace'))
        for i,src in enumerate(p.scripts[:40]):
            u=urljoin('https://www.poi86.com/',src)
            item=fetch(f'js_{i}',u,max_bytes=1_500_000)
            txt=(OUT/f'js_{i}.txt').read_text(encoding='utf-8',errors='replace') if (OUT/f'js_{i}.txt').exists() else ''
            contexts=[]
            for m in re.finditer(r'(?i)(search|query|keyword|sitemap|api|老百姓)',txt):
                contexts.append(txt[max(0,m.start()-180):m.end()+300])
                if len(contexts)>=40: break
            js_report.append({"url":u,"status":item.get('status'),"length":item.get('length_read'),"contexts":contexts})
            time.sleep(.3)
    (OUT/'report.json').write_text(json.dumps({"pages":report,"scripts":js_report},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
