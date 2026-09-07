#!/usr/bin/env python3
from __future__ import annotations
import html, json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import requests

OUT=Path('yx_discovery_output'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'zh-CN,zh;q=0.9','Referer':'https://yx.lbxcn.com/'})
PAGE='https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4'
WORDS=['附近门店','预约门店','门店','store','shop','branch','nearby','location','longitude','latitude','lng','lat','address','api','dealer','org','pharmacy']

def get(url,timeout=30):
    try:
        r=S.get(url,timeout=timeout,allow_redirects=True)
        return {'url':url,'status':r.status_code,'final_url':r.url,'content_type':r.headers.get('content-type',''),'length':len(r.content),'text':r.text}
    except Exception as e: return {'url':url,'status':None,'error':repr(e),'text':'','length':0}

def snippets(text,limit=200,radius=220):
    out=[]; low=text.lower()
    for w in WORDS:
        start=0
        while len(out)<limit:
            i=low.find(w.lower(),start)
            if i<0: break
            s=text[max(0,i-radius):min(len(text),i+len(w)+radius)]
            s=re.sub(r'\s+',' ',html.unescape(s)).strip()
            if s not in out: out.append(s)
            start=i+max(1,len(w))
    return out

def candidates(text,base):
    vals=set()
    patterns=[r'https?://[^\s\"\'<>\\]+',r'[\"\'](/[^\"\']{2,250})[\"\']',r'[\"\']([^\"\']*(?:store|shop|branch|nearby|location|poi|门店|药房)[^\"\']*)[\"\']']
    for pat in patterns:
        for m in re.finditer(pat,text,re.I):
            v=m.group(1) if m.lastindex else m.group(0)
            v=html.unescape(v).strip().rstrip('),.;}')
            if any(w.lower() in v.lower() for w in WORDS):
                if v.startswith('/'): v=urljoin(base,v)
                vals.add(v)
                if len(vals)>=800: return sorted(vals)
    return sorted(vals)

def main():
    page=get(PAGE); text=page.get('text','')
    (OUT/'index.html').write_text(text,encoding='utf-8')
    scripts=[]
    for m in re.finditer(r'(?is)<script[^>]+src=["\']([^"\']+)["\']',text):
        u=urljoin(page.get('final_url',PAGE),html.unescape(m.group(1)))
        if u not in scripts: scripts.append(u)
    links=[]
    for m in re.finditer(r'(?is)<link[^>]+href=["\']([^"\']+)["\']',text):
        u=urljoin(page.get('final_url',PAGE),html.unescape(m.group(1)))
        if u not in links: links.append(u)
    report={'page':{k:v for k,v in page.items() if k!='text'},'page_snippets':snippets(text),'page_candidates':candidates(text,PAGE),'scripts':[],'links':links}
    for idx,u in enumerate(scripts[:100]):
        r=get(u,45); body=r.get('text','')
        rec={k:v for k,v in r.items() if k!='text'}
        rec['snippets']=snippets(body)
        rec['candidates']=candidates(body,u)
        rec['domains']=sorted(set(re.findall(r'https?://([A-Za-z0-9.-]+)',body)))[:200]
        report['scripts'].append(rec)
        if rec['snippets'] or rec['candidates']:
            (OUT/f'script_{idx:03d}.js').write_text(body,encoding='utf-8')
        time.sleep(.15)
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['PAGE '+json.dumps(report['page'],ensure_ascii=False),'SCRIPTS '+str(len(report['scripts']))]
    for rec in report['scripts']:
        if rec.get('snippets') or rec.get('candidates'):
            lines += ['',rec.get('final_url') or rec['url']]
            lines += ['CANDIDATE '+x for x in rec.get('candidates',[])[:100]]
            lines += ['SNIPPET '+x for x in rec.get('snippets',[])[:40]]
    (OUT/'summary.txt').write_text('\n'.join(lines),encoding='utf-8')
    print('\n'.join(lines[:500]))
if __name__=='__main__': main()
