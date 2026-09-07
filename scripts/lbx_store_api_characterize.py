#!/usr/bin/env python3
"""Characterize the public LBX nearby-store endpoint before nationwide crawl."""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any

import requests

OUT = Path("lbx_store_api_characterize_output")
OUT.mkdir(exist_ok=True)

OLD = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
NEW = "https://yx.lbxcn.com/out/2026api/getlbxStoreList"
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
    "Origin": "https://yx.lbxcn.com",
    "X-Requested-With": "XMLHttpRequest",
}
S = requests.Session(); S.headers.update(H)

POINTS = {
    "长沙": (28.228304, 112.938882), "株洲": (27.827433, 113.134002), "岳阳": (29.357104, 113.129191),
    "北京": (39.904179, 116.407387), "上海": (31.230525, 121.473667), "天津": (39.085318, 117.201509),
    "南京": (32.059344, 118.796624), "苏州": (31.299758, 120.585294), "杭州": (30.246026, 120.210792),
    "宁波": (29.868336, 121.543990), "合肥": (31.820567, 117.227267), "武汉": (30.593354, 114.304569),
    "郑州": (34.746303, 113.625351), "济南": (36.651216, 117.120098), "青岛": (36.066938, 120.382665),
    "西安": (34.343207, 108.939645), "兰州": (36.061089, 103.834303), "银川": (38.487194, 106.230909),
    "呼和浩特": (40.842585, 111.749180), "太原": (37.870590, 112.548879), "贵阳": (26.647661, 106.630153),
    "南宁": (22.817002, 108.366543), "广州": (23.130061, 113.264499), "深圳": (22.543527, 114.057939),
    "南昌": (28.682892, 115.858198), "沈阳": (41.677576, 123.464675), "白城": (45.619026, 122.838714),
    "成都": (30.572961, 104.066301), "重庆": (29.562680, 106.551787), "乌鲁木齐": (43.825592, 87.616848),
    "拉萨": (29.652491, 91.172110), "海口": (20.044220, 110.199890), "昆明": (25.038859, 102.718277),
    "三亚": (18.252847, 109.511909), "漠河": (52.972272, 122.538592), "东海": (30.0, 130.0),
}


def req_get(name: str, params: dict[str, Any], endpoint: str = OLD) -> dict[str, Any]:
    started = time.time()
    try:
        r = S.get(endpoint, params=params, timeout=40)
        try: obj = r.json()
        except Exception: obj = None
        rec = {"name": name, "method": "GET", "url": r.request.url, "status": r.status_code,
               "content_type": r.headers.get("content-type"), "length": len(r.content),
               "elapsed": round(time.time()-started,3), "text": r.text, "json": obj}
    except Exception as e:
        rec = {"name": name, "method": "GET", "url": endpoint, "params": params,
               "elapsed": round(time.time()-started,3), "error": repr(e)}
    return rec


def req_post(name: str, url: str, body: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    try:
        r = S.post(url, json=body, timeout=40, headers={**H, "Origin": "https://yx.lbxcn.com"})
        try: obj = r.json()
        except Exception: obj = None
        return {"name": name, "method": "POST", "url": url, "body": body, "status": r.status_code,
                "content_type": r.headers.get("content-type"), "length": len(r.content),
                "elapsed": round(time.time()-started,3), "text": r.text, "json": obj}
    except Exception as e:
        return {"name": name, "method": "POST", "url": url, "body": body,
                "elapsed": round(time.time()-started,3), "error": repr(e)}


def extract_stores(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, dict): return []
    candidates = [
        obj.get("data"),
        (obj.get("data") or {}).get("data") if isinstance(obj.get("data"), dict) else None,
        (obj.get("data") or {}).get("rows") if isinstance(obj.get("data"), dict) else None,
        obj.get("rows"), obj.get("records"), obj.get("list"),
    ]
    for v in candidates:
        if isinstance(v, list) and (not v or isinstance(v[0], dict)):
            return v
        if isinstance(v, dict):
            for k in ("rows","records","list","data","content"):
                x=v.get(k)
                if isinstance(x,list) and (not x or isinstance(x[0],dict)): return x
    return []


def summarize(rec: dict[str, Any]) -> dict[str, Any]:
    stores=extract_stores(rec.get("json"))
    distances=[]
    for x in stores:
        for k in ("distanceGd","distance","distanceBd"):
            try: distances.append(float(x.get(k)))
            except Exception: pass
            if distances: break
    return {k:rec.get(k) for k in ("name","method","url","status","content_type","length","elapsed","error")} | {
        "store_count":len(stores),
        "store_ids":[str(x.get("shop_id") or x.get("sap_id") or x.get("id") or "") for x in stores],
        "cities":sorted({str(x.get("city") or "") for x in stores}),
        "max_distance":max(distances) if distances else None,
        "sample":stores[:2],
        "json_preview":json.dumps(rec.get("json"),ensure_ascii=False)[:1200] if rec.get("json") is not None else None,
        "text_preview":rec.get("text","")[:800],
    }


def main() -> None:
    records=[]
    # Old public wrapper across markets and non-markets.
    for idx,(city,(lat,lng)) in enumerate(POINTS.items(),1):
        rec=req_get(f"old_{city}",{"Latitude":lat,"Longitude":lng})
        records.append(rec); print(json.dumps(summarize(rec),ensure_ascii=False),flush=True)
        time.sleep(.25)

    # Query-parameter behavior at Changsha.
    lat,lng=POINTS["长沙"]
    variants=[
        ("page1_size100", {"Latitude":lat,"Longitude":lng,"page":1,"size":100}),
        ("page2_size100", {"Latitude":lat,"Longitude":lng,"page":2,"size":100}),
        ("page1_pageSize100", {"Latitude":lat,"Longitude":lng,"page":1,"pageSize":100}),
        ("radius1", {"Latitude":lat,"Longitude":lng,"radius":1}),
        ("radius10", {"Latitude":lat,"Longitude":lng,"radius":10}),
        ("radius100", {"Latitude":lat,"Longitude":lng,"radius":100}),
        ("radius1000", {"Latitude":lat,"Longitude":lng,"radius":1000}),
        ("size1", {"Latitude":lat,"Longitude":lng,"size":1}),
        ("size50", {"Latitude":lat,"Longitude":lng,"size":50}),
        ("lower", {"latitude":lat,"longitude":lng}),
        ("latlng", {"lat":lat,"lng":lng}),
        ("missing_lat", {"Longitude":lng}),
        ("missing_lng", {"Latitude":lat}),
    ]
    for name,params in variants:
        rec=req_get("variant_"+name,params)
        records.append(rec); print(json.dumps(summarize(rec),ensure_ascii=False),flush=True); time.sleep(.25)

    # New wrapper and direct backend candidates.
    new_rec=req_get("new_wrapper_changsha",{"Latitude":lat,"Longitude":lng},NEW)
    records.append(new_rec); print(json.dumps(summarize(new_rec),ensure_ascii=False),flush=True)
    body={"latitude":str(lat),"longitude":str(lng),"page":1,"size":100,"formatIdList":["01","20","92"],"isClosed":0,"isParent":1,"radius":100}
    hosts=[
        "msapitest.lbxcn.com:31443","msapi.lbxcn.com:31443","msapi.lbxcn.com",
        "msapi-test.lbxcn.com:31443","msapi-prod.lbxcn.com:31443","msapiprod.lbxcn.com:31443",
        "api.lbxcn.com","gateway.lbxcn.com",
    ]
    path="/sems-store/nearby/store/pageNearbyStore"
    for host in hosts:
        try: ips=sorted(set(socket.gethostbyname_ex(host.split(':')[0])[2]))
        except Exception as e: ips=[]
        rec=req_post("direct_"+host.replace(':','_'),"https://"+host+path,body)
        rec["dns_ips"]=ips
        records.append(rec); print(json.dumps(summarize(rec)|{"dns_ips":ips},ensure_ascii=False),flush=True); time.sleep(.25)

    summaries=[summarize(r) | ({"dns_ips":r.get("dns_ips")} if "dns_ips" in r else {}) for r in records]
    (OUT/"full_report.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"summary.json").write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding="utf-8")
    # TSV is convenient to inspect via GitHub text tools.
    cols=["name","status","store_count","max_distance","cities","store_ids","url","error"]
    lines=["\t".join(cols)]
    for r in summaries:
        vals=[]
        for c in cols:
            v=r.get(c)
            if isinstance(v,(list,dict)): v=json.dumps(v,ensure_ascii=False)
            vals.append(str(v if v is not None else "").replace("\t"," ").replace("\n"," "))
        lines.append("\t".join(vals))
    (OUT/"summary.tsv").write_text("\n".join(lines),encoding="utf-8")

if __name__=="__main__": main()
