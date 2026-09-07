#!/usr/bin/env python3
from __future__ import annotations
import json, itertools, requests, urllib3
urllib3.disable_warnings()
PATH='/sems-store/nearby/store/pageNearbyStore'
HOSTS=[
 'https://msapitest.lbxcn.com:31443',
 'https://msapitest.lbxcn.com',
 'https://msapi.lbxcn.com:31443',
 'https://msapi.lbxcn.com',
]
HEAD={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*','Content-Type':'application/json','Referer':'https://yx.lbxcn.com/','Origin':'https://yx.lbxcn.com'}
base={'latitude':'28.2282','longitude':'112.9388','page':1,'size':5,'formatIdList':['01','20','92'],'isClosed':0,'isParent':1,'radius':100}
variants=[
 ('exact',base),
 ('num_coord',{**base,'latitude':28.2282,'longitude':112.9388}),
 ('radius_5',{**base,'radius':5}),('radius_10',{**base,'radius':10}),('radius_50',{**base,'radius':50}),('radius_1000',{**base,'radius':1000}),
 ('parent0',{**base,'isParent':0}),('closed1',{**base,'isClosed':1}),
 ('no_formats',{k:v for k,v in base.items() if k!='formatIdList'}),
 ('formats_empty',{**base,'formatIdList':[]}),('formats_string',{**base,'formatIdList':'01,20,92'}),
 ('pageNum',{k:v for k,v in base.items() if k not in ('page','size')}|{'pageNum':1,'pageSize':5}),
 ('minimal',{'latitude':28.2282,'longitude':112.9388,'page':1,'size':5}),
 ('capital',{'Latitude':28.2282,'Longitude':112.9388,'page':1,'size':5,'radius':100}),
]
S=requests.Session(); S.headers.update(HEAD)
for host in HOSTS:
    url=host+PATH
    for name,payload in variants if 'msapitest.lbxcn.com:31443' in host else variants[:3]:
        try:
            r=S.post(url,json=payload,timeout=(8,20),verify=False,allow_redirects=True)
            print(json.dumps({'host':host,'case':name,'method':'POST_JSON','status':r.status_code,'url':r.url,'headers':dict(r.headers),'body':r.text[:10000]},ensure_ascii=False))
        except Exception as e:
            print(json.dumps({'host':host,'case':name,'method':'POST_JSON','error':repr(e)},ensure_ascii=False))
    try:
        r=S.get(url,params=base,timeout=(8,20),verify=False,allow_redirects=True)
        print(json.dumps({'host':host,'case':'get_base','method':'GET','status':r.status_code,'url':r.url,'headers':dict(r.headers),'body':r.text[:10000]},ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'host':host,'case':'get_base','method':'GET','error':repr(e)},ensure_ascii=False))
    try:
        h={k:v for k,v in HEAD.items() if k!='Content-Type'}
        r=requests.post(url,data=base,headers=h,timeout=(8,20),verify=False,allow_redirects=True)
        print(json.dumps({'host':host,'case':'form_base','method':'POST_FORM','status':r.status_code,'url':r.url,'headers':dict(r.headers),'body':r.text[:10000]},ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'host':host,'case':'form_base','method':'POST_FORM','error':repr(e)},ensure_ascii=False))
