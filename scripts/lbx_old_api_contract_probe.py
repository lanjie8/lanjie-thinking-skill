#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

OUT = Path("lbx_old_api_contract_output")
OUT.mkdir(exist_ok=True)
URL = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
    "X-Requested-With": "XMLHttpRequest",
})

POINTS = {
    "长沙": (28.2282,112.9388), "株洲":(27.8274,113.1339), "衡阳":(26.8932,112.5719),
    "北京":(39.9042,116.4074), "天津":(39.0842,117.2009), "上海":(31.2304,121.4737),
    "杭州":(30.2741,120.1551), "南京":(32.0603,118.7969), "合肥":(31.8206,117.2272),
    "武汉":(30.5928,114.3055), "南昌":(28.6820,115.8579), "郑州":(34.7466,113.6254),
    "西安":(34.3416,108.9398), "成都":(30.5728,104.0668), "重庆":(29.5630,106.5516),
    "广州":(23.1291,113.2644), "深圳":(22.5431,114.0579), "南宁":(22.8170,108.3665),
    "昆明":(25.0389,102.7183), "贵阳":(26.6470,106.6302), "兰州":(36.0611,103.8343),
    "沈阳":(41.8057,123.4315), "哈尔滨":(45.8038,126.5349), "济南":(36.6512,117.1201),
    "石家庄":(38.0428,114.5149), "太原":(37.8706,112.5489), "呼和浩特":(40.8426,111.7492),
    "乌鲁木齐":(43.8256,87.6168), "拉萨":(29.6520,91.1721), "海口":(20.0440,110.1999),
    "三沙附近":(16.83,112.33), "东海":(29.0,125.0), "西部荒漠":(39.0,82.0),
}

def extract_rows(obj):
    try:
        rows=obj["data"]["data"]
        return rows if isinstance(rows,list) else []
    except Exception:
        return []

def do_get(name, params):
    t=time.time()
    try:
        r=S.get(URL,params=params,timeout=45)
        try: data=r.json()
        except Exception: data=None
        rows=extract_rows(data)
        return {
            "name":name,"params":params,"url":r.url,"status":r.status_code,"content_type":r.headers.get("content-type"),
            "elapsed":round(time.time()-t,3),"length":len(r.content),"code":data.get("code") if isinstance(data,dict) else None,
            "message":data.get("message") if isinstance(data,dict) else None,"count":len(rows),
            "distances":[x.get("distance") for x in rows],"shop_ids":[x.get("shop_id") for x in rows],
            "cities":[x.get("city") for x in rows],"sample":rows[:1],"body":data if data is not None else r.text[:3000]
        }
    except Exception as e:
        return {"name":name,"params":params,"status":None,"elapsed":round(time.time()-t,3),"error":repr(e)}

def main():
    report=[]
    for name,(lat,lng) in POINTS.items():
        rec=do_get(name,{"Latitude":lat,"Longitude":lng}); report.append(rec)
        print(json.dumps({k:rec.get(k) for k in ["name","status","count","distances","cities","error"]},ensure_ascii=False),flush=True)
        time.sleep(.35)
    special=[
      ("no_params",{}),
      ("zero",{"Latitude":0,"Longitude":0}),
      ("null_strings",{"Latitude":"","Longitude":""}),
      ("changsha_limit_100",{"Latitude":28.2282,"Longitude":112.9388,"limit":100}),
      ("changsha_pageSize_100",{"Latitude":28.2282,"Longitude":112.9388,"pageSize":100}),
      ("changsha_rows_100",{"Latitude":28.2282,"Longitude":112.9388,"rows":100}),
      ("changsha_size_100",{"Latitude":28.2282,"Longitude":112.9388,"size":100}),
      ("changsha_radius_100",{"Latitude":28.2282,"Longitude":112.9388,"radius":100}),
      ("changsha_page_2",{"Latitude":28.2282,"Longitude":112.9388,"page":2}),
      ("changsha_pn_2",{"Latitude":28.2282,"Longitude":112.9388,"pn":2}),
      ("changsha_city",{"Latitude":28.2282,"Longitude":112.9388,"city":"长沙市"}),
    ]
    for name,params in special:
        rec=do_get(name,params); report.append(rec)
        print(json.dumps({k:rec.get(k) for k in ["name","status","count","distances","cities","error","message"]},ensure_ascii=False),flush=True)
        time.sleep(.5)
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    rows=[]
    for rec in report:
        for row in extract_rows(rec.get("body")):
            rows.append({"query":rec["name"],**row})
    (OUT/"rows.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__": main()
