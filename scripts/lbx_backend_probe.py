#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import ssl
import time
from pathlib import Path

import requests

OUT = Path("lbx_backend_probe_output")
OUT.mkdir(exist_ok=True)
PATH = "/sems-store/nearby/store/pageNearbyStore"
HOSTS = [
    "msapitest.lbxcn.com:31443",
    "msapi.lbxcn.com:31443",
    "msapiprod.lbxcn.com:31443",
    "msapi-prod.lbxcn.com:31443",
    "msapi-pro.lbxcn.com:31443",
    "msapi-pre.lbxcn.com:31443",
    "msapi-uat.lbxcn.com:31443",
    "msapi-test.lbxcn.com:31443",
    "msapi-dev.lbxcn.com:31443",
    "api.lbxcn.com:31443",
    "gateway.lbxcn.com:31443",
    "msapitest.lbxcn.com",
    "msapi.lbxcn.com",
    "api.lbxcn.com",
]
S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://yx.lbxcn.com/",
    "Origin": "https://yx.lbxcn.com",
})

BASE = {
    "latitude": 28.2282,
    "longitude": 112.9388,
    "page": 1,
    "size": 5,
    "formatIdList": ["01", "20", "92"],
    "isClosed": 0,
    "isParent": 1,
    "radius": 100,
}


def fetch(method, url, *, params=None, payload=None, verify=True):
    t=time.time()
    try:
        r=S.request(method,url,params=params,json=payload,timeout=35,allow_redirects=True,verify=verify)
        try: data=r.json()
        except Exception: data=None
        return {"method":method,"url":r.url,"status":r.status_code,"elapsed":round(time.time()-t,3),
                "content_type":r.headers.get("content-type"),"length":len(r.content),"headers":dict(r.headers),
                "json":data,"text":r.text[:8000]}
    except Exception as e:
        return {"method":method,"url":url,"status":None,"elapsed":round(time.time()-t,3),"error":repr(e)}


def dns(hostport):
    h=hostport.split(':')[0]
    try: return socket.getaddrinfo(h,None)
    except Exception as e: return repr(e)


def main():
    report=[]
    # Force old wrapper errors to expose its upstream production URL/config.
    wrapper="https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
    for name,params in [
        ("wrapper_no_params",{}),
        ("wrapper_invalid",{"Latitude":"abc","Longitude":"xyz"}),
        ("wrapper_nan",{"Latitude":"NaN","Longitude":"NaN"}),
        ("wrapper_huge",{"Latitude":999,"Longitude":999}),
    ]:
        rec={"name":name,**fetch("GET",wrapper,params=params)}; report.append(rec)
        print(json.dumps(rec,ensure_ascii=False,indent=2)[:12000],flush=True)
        time.sleep(.5)

    # Probe candidate upstream hosts with the production request schema.
    for host in HOSTS:
        url=f"https://{host}{PATH}"
        rec={"name":host,"dns":str(dns(host))[:1000],**fetch("POST",url,payload=BASE)}
        report.append(rec)
        print(json.dumps({k:rec.get(k) for k in ["name","dns","status","elapsed","content_type","length","json","text","error"]},ensure_ascii=False,indent=2)[:12000],flush=True)
        time.sleep(.5)

    # Payload contract variations on the known test host.
    url=f"https://msapitest.lbxcn.com:31443{PATH}"
    variants={
        "test_numeric":BASE,
        "test_strings":{**BASE,"latitude":str(BASE["latitude"]),"longitude":str(BASE["longitude"])},
        "test_no_formats":{k:v for k,v in BASE.items() if k!="formatIdList"},
        "test_empty_formats":{**BASE,"formatIdList":[]},
        "test_parent0":{**BASE,"isParent":0},
        "test_size100":{**BASE,"size":100},
        "test_radius100000":{**BASE,"radius":100000},
        "test_minimal":{"latitude":28.2282,"longitude":112.9388,"page":1,"size":5},
        "test_capitalized":{"Latitude":28.2282,"Longitude":112.9388,"Page":1,"Size":5},
    }
    for name,payload in variants.items():
        rec={"name":name,"payload":payload,**fetch("POST",url,payload=payload)}; report.append(rec)
        print(json.dumps({k:rec.get(k) for k in ["name","status","elapsed","content_type","length","json","text","error"]},ensure_ascii=False,indent=2)[:12000],flush=True)
        time.sleep(.5)

    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__": main()
