#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter

OUT = Path("lbx_nationwide_output")
OUT.mkdir(exist_ok=True)
ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
ABOUT_URL = "https://www.lbxdrugs.com/about.html"
WORKERS = max(2, min(int(os.getenv("LBX_WORKERS", "8")), 12))
MAX_REQUESTS = int(os.getenv("LBX_MAX_REQUESTS", "40000"))
TIMEOUT = float(os.getenv("LBX_REQUEST_TIMEOUT", "12"))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
}
SAFE_FIELDS = [
    "third_org_name", "deptName", "latGd", "city", "lngGd", "winter_start_hours",
    "shopLabels", "shipStartTime", "sap_id", "pdeptId", "third_org_code", "org_name",
    "winter_closing_hours", "lat", "latBd", "companyCode", "summer_closing_hours", "lngBd",
    "lng", "is_m_shop", "is_close", "deptType", "summer_start_hours", "shop_id", "parentName",
    "phone", "sales_scan_name", "deptAddr", "org_code", "sales_scan_id", "shipEndTime",
]
PROVINCES = [
    "北京市", "天津市", "上海市", "重庆市", "河北省", "山西省", "辽宁省", "吉林省", "黑龙江省",
    "江苏省", "浙江省", "安徽省", "福建省", "江西省", "山东省", "河南省", "湖北省", "湖南省",
    "广东省", "海南省", "四川省", "贵州省", "云南省", "陕西省", "甘肃省", "青海省", "台湾省",
    "内蒙古自治区", "广西壮族自治区", "西藏自治区", "宁夏回族自治区", "新疆维吾尔自治区",
    "香港特别行政区", "澳门特别行政区",
]
ALIASES = {
    "北京":"北京市", "天津":"天津市", "上海":"上海市", "重庆":"重庆市", "河北":"河北省",
    "山西":"山西省", "辽宁":"辽宁省", "吉林":"吉林省", "黑龙江":"黑龙江省", "江苏":"江苏省",
    "浙江":"浙江省", "安徽":"安徽省", "福建":"福建省", "江西":"江西省", "山东":"山东省",
    "河南":"河南省", "湖北":"湖北省", "湖南":"湖南省", "广东":"广东省", "海南":"海南省",
    "四川":"四川省", "贵州":"贵州省", "云南":"云南省", "陕西":"陕西省", "甘肃":"甘肃省",
    "青海":"青海省", "内蒙古":"内蒙古自治区", "广西":"广西壮族自治区", "西藏":"西藏自治区",
    "宁夏":"宁夏回族自治区", "新疆":"新疆维吾尔自治区", "香港":"香港特别行政区", "澳门":"澳门特别行政区",
}
CITY_HINTS = {
    "长沙市":"湖南省", "株洲市":"湖南省", "湘潭市":"湖南省", "衡阳市":"湖南省", "邵阳市":"湖南省",
    "岳阳市":"湖南省", "常德市":"湖南省", "益阳市":"湖南省", "郴州市":"湖南省", "永州市":"湖南省",
    "怀化市":"湖南省", "娄底市":"湖南省", "西安市":"陕西省", "武汉市":"湖北省", "郑州市":"河南省",
    "杭州市":"浙江省", "宁波市":"浙江省", "温州市":"浙江省", "南京市":"江苏省", "无锡市":"江苏省",
    "苏州市":"江苏省", "常州市":"江苏省", "南昌市":"江西省", "合肥市":"安徽省", "济南市":"山东省",
    "青岛市":"山东省", "广州市":"广东省", "深圳市":"广东省", "南宁市":"广西壮族自治区",
    "石家庄市":"河北省", "太原市":"山西省", "兰州市":"甘肃省", "银川市":"宁夏回族自治区",
    "呼和浩特市":"内蒙古自治区", "北京市":"北京市", "天津市":"天津市", "上海市":"上海市", "重庆市":"重庆市",
}
_thread_local = threading.local()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def number(v: Any) -> float | None:
    try:
        n = float(text(v))
        return n if math.isfinite(n) else None
    except Exception:
        return None


def valid(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and 15 <= lat <= 56 and 70 <= lon <= 140


def store_coord(row: dict[str, Any]) -> tuple[float, float] | None:
    for a, b in (("latGd", "lngGd"), ("lat", "lng"), ("latBd", "lngBd")):
        lat, lon = number(row.get(a)), number(row.get(b))
        if valid(lat, lon):
            return float(lat), float(lon)
    return None


def ckey(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 5), round(lon, 5)


def skey(row: dict[str, Any]) -> str:
    for prefix, field in (("shop", "shop_id"), ("org", "org_code"), ("sap", "sap_id")):
        value = text(row.get(field))
        if value:
            return f"{prefix}:{value}"
    raw = "|".join(text(row.get(k)) for k in ("deptName", "deptAddr", "latGd", "lngGd", "phone"))
    return "hash:" + hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def province(row: dict[str, Any]) -> str:
    city = text(row.get("city"))
    if city in CITY_HINTS:
        return CITY_HINTS[city]
    blob = " ".join(text(row.get(k)) for k in ("deptAddr", "deptName", "org_name", "parentName", "third_org_name"))
    for p in PROVINCES:
        if p in blob:
            return p
    for a, p in sorted(ALIASES.items(), key=lambda x: -len(x[0])):
        if a in blob:
            return p
    return ""


def record_class(row: dict[str, Any]) -> str:
    blob = " ".join(text(row.get(k)) for k in ("deptName", "org_name", "parentName", "deptAddr"))
    if any(x in blob for x in ("诊所", "医院", "门诊部", "体检", "物流", "仓库", "总部", "办公室", "培训中心")):
        return "非药房机构/待核验"
    if any(x in blob for x in ("大药房", "药房", "药店", "医药连锁")) or text(row.get("deptName")).endswith("店"):
        return "药房门店"
    return "门店记录/待核验"


def get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        s.mount("https://", HTTPAdapter(pool_connections=2, pool_maxsize=2, max_retries=0))
        _thread_local.session = s
    return s


def extract_rows(obj: Any) -> list[dict[str, Any]]:
    try:
        rows = obj.get("data", {}).get("data")
        return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    except Exception:
        return []


def fetch(point: tuple[float, float, str]) -> dict[str, Any]:
    lat, lon, label = point
    error = ""
    for attempt in range(1, 4):
        try:
            time.sleep(random.uniform(0.015, 0.055))
            r = get_session().get(ENDPOINT, params={"Latitude": f"{lat:.6f}", "Longitude": f"{lon:.6f}"}, timeout=TIMEOUT)
            if r.status_code != 200:
                error = f"HTTP {r.status_code}: {r.text[:160]}"
                if r.status_code in (408, 429, 500, 502, 503, 504):
                    time.sleep(0.35 * attempt)
                    continue
                return {"ok": False, "lat": lat, "lon": lon, "label": label, "error": error}
            return {"ok": True, "lat": lat, "lon": lon, "label": label, "rows": extract_rows(r.json())}
        except Exception as exc:
            error = repr(exc)
            time.sleep(0.35 * attempt)
    return {"ok": False, "lat": lat, "lon": lon, "label": label, "error": error}


def grid(lat0: float, lat1: float, lon0: float, lon1: float, step: float, label: str) -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    lat = lat0
    while lat <= lat1 + 1e-9:
        lon = lon0
        while lon <= lon1 + 1e-9:
            out.append((round(lat, 6), round(lon, 6), label))
            lon += step
        lat += step
    return out


def clean(raw: dict[str, Any], phase: str) -> dict[str, Any]:
    row = {k: text(raw.get(k)) for k in SAFE_FIELDS}
    row.update({
        "record_key": skey(raw),
        "province_inferred": province(raw),
        "record_class": record_class(raw),
        "franchise_label": "加盟门店（按接口标识）" if text(raw.get("is_m_shop")) == "1" else (
            "非加盟门店（按接口标识）" if text(raw.get("is_m_shop")) == "0" else "其他/待核验（按接口标识）"
        ),
        "status_label": "未关闭/营业中（按接口标识）" if text(raw.get("is_close")) == "0" else "状态待核验",
        "first_seen_phase": phase,
        "sightings": 1,
    })
    return row


def merge(stores: dict[str, dict[str, Any]], raw: dict[str, Any], phase: str) -> bool:
    row = clean(raw, phase)
    key = row["record_key"]
    old = stores.get(key)
    if old is None:
        stores[key] = row
        return True
    old["sightings"] = int(old.get("sightings") or 1) + 1
    for k, v in row.items():
        if k not in ("first_seen_phase", "sightings") and not text(old.get(k)) and text(v):
            old[k] = v
    return False


def official_count() -> tuple[int | None, str]:
    try:
        r = get_session().get(ABOUT_URL, timeout=20)
        r.raise_for_status()
        plain = re.sub(r"<[^>]+>", " ", r.text)
        values = []
        for pat in (r"([0-9][0-9,]{3,})\s*家门店", r"门店[^0-9]{0,20}([0-9][0-9,]{3,})"):
            values += [int(m.group(1).replace(",", "")) for m in re.finditer(pat, plain)]
        values = [x for x in values if 1000 <= x <= 100000]
        return (max(values) if values else None), ""
    except Exception as exc:
        return None, repr(exc)


def main() -> None:
    started = time.time()
    stores: dict[str, dict[str, Any]] = {}
    queried: set[tuple[float, float]] = set()
    errors: list[dict[str, Any]] = []
    phases: list[dict[str, Any]] = []
    requests_done = 0
    company_count, count_error = official_count()
    pool = ThreadPoolExecutor(max_workers=WORKERS)

    def save(status: str, current_phase: str = "") -> None:
        rows = sorted(stores.values(), key=lambda r: (text(r.get("province_inferred")), text(r.get("city")), text(r.get("deptName"))))
        (OUT / "stores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "phase_stats.json").write_text(json.dumps(phases, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "errors.json").write_text(json.dumps(errors[-2000:], ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "checkpoint.json").write_text(json.dumps({
            "status": status, "current_phase": current_phase, "store_count": len(rows),
            "request_total": requests_done, "official_reported_store_count": company_count, "updated_at": now_iso(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def phase(name: str, points: Iterable[tuple[float, float, str]]) -> dict[str, Any]:
        nonlocal requests_done
        todo: list[tuple[float, float, str]] = []
        for lat, lon, label in points:
            if requests_done + len(todo) >= MAX_REQUESTS:
                break
            key = ckey(lat, lon)
            if valid(lat, lon) and key not in queried:
                queried.add(key)
                todo.append((lat, lon, label))
        stat = {"phase": name, "requested": len(todo), "success": 0, "no_data": 0, "error": 0,
                "new_stores": 0, "stores_before": len(stores), "started_at": now_iso()}
        t0 = time.time()
        for start in range(0, len(todo), 600):
            futures = [pool.submit(fetch, p) for p in todo[start:start + 600]]
            for fut in as_completed(futures):
                result = fut.result()
                requests_done += 1
                if result.get("ok"):
                    stat["success"] += 1
                    rows = result.get("rows") or []
                    stat["no_data"] += int(not rows)
                    for raw in rows:
                        stat["new_stores"] += int(merge(stores, raw, name))
                else:
                    stat["error"] += 1
                    errors.append({"phase": name, "lat": result.get("lat"), "lon": result.get("lon"), "error": result.get("error")})
                if requests_done % 250 == 0:
                    print(json.dumps({"event":"progress", "phase":name, "requests":requests_done,
                                      "stores":len(stores), "errors":len(errors),
                                      "elapsed_seconds":round(time.time()-started,1)}, ensure_ascii=False), flush=True)
            if start and start % 1800 == 0:
                save("running", name)
        stat.update({"stores_after": len(stores), "finished_at": now_iso(), "elapsed_seconds": round(time.time()-t0,1)})
        phases.append(stat)
        print(json.dumps({"event":"phase_complete", **stat}, ensure_ascii=False), flush=True)
        save("running", name)
        return stat

    def expand(prefix: str, max_rounds: int = 20) -> None:
        for i in range(1, max_rounds + 1):
            points = []
            for row in list(stores.values()):
                c = store_coord(row)
                if c and ckey(*c) not in queried:
                    points.append((c[0], c[1], prefix))
            if not points or requests_done >= MAX_REQUESTS:
                break
            if phase(f"{prefix}_round_{i}", points)["new_stores"] == 0:
                break

    print(json.dumps({"event":"start", "workers":WORKERS, "max_requests":MAX_REQUESTS,
                      "official_reported_store_count":company_count, "time":now_iso()}, ensure_ascii=False), flush=True)
    phase("national_grid_1deg", grid(18, 54, 73, 135, 1, "grid1"))
    expand("graph_after_grid1")
    phase("national_grid_1deg_shifted", grid(18.5, 53.5, 73.5, 134.5, 1, "grid1_shifted"))
    expand("graph_after_shifted")

    tiles: dict[tuple[int, int], int] = defaultdict(int)
    for row in stores.values():
        c = store_coord(row)
        if c:
            tiles[(math.floor(c[0] / .1), math.floor(c[1] / .1))] += 1
    dense = []
    for (i, j), count in tiles.items():
        if count >= 8:
            for dy, dx in ((.05,.05),(.025,.025),(.025,.075),(.075,.025),(.075,.075)):
                dense.append((i*.1+dy, j*.1+dx, "dense"))
    phase("dense_tile_refinement", dense)
    expand("graph_after_dense")

    threshold = int(company_count * .90) if company_count else 13000
    if len(stores) < threshold and requests_done < MAX_REQUESTS:
        fine = grid(20, 44.5, 97, 126.5, .5, "fine_east_central") + grid(44.5, 53.5, 110, 135, .5, "fine_northeast")
        phase("targeted_grid_0_5deg", fine)
        expand("graph_after_fine")
    pool.shutdown(wait=True)

    fetched_at = now_iso()
    rows = sorted(stores.values(), key=lambda r: (text(r.get("province_inferred")), text(r.get("city")), text(r.get("deptName")), text(r.get("shop_id"))))
    for row in rows:
        row["data_source"] = ENDPOINT
        row["fetched_at"] = fetched_at
    (OUT / "stores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["record_key","shop_id","deptName","org_name","parentName","third_org_name","province_inferred","city",
              "deptAddr","phone","latGd","lngGd","latBd","lngBd","lat","lng","shopLabels","is_m_shop",
              "franchise_label","is_close","status_label","sales_scan_name","summer_start_hours","summer_closing_hours",
              "winter_start_hours","winter_closing_hours","shipStartTime","shipEndTime","sap_id","org_code","third_org_code",
              "companyCode","pdeptId","sales_scan_id","deptType","record_class","first_seen_phase","sightings","data_source","fetched_at"]
    with (OUT / "stores.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    counts = lambda key, empty: dict(Counter(text(r.get(key)) or empty for r in rows).most_common())
    shop_ids = [text(r.get("shop_id")) for r in rows if text(r.get("shop_id"))]
    unqueried = sum(1 for r in rows if store_coord(r) and ckey(*store_coord(r)) not in queried)
    summary = {
        "status":"completed", "started_at":datetime.fromtimestamp(started, tz=timezone.utc).astimezone().isoformat(timespec="seconds"),
        "finished_at":fetched_at, "elapsed_seconds":round(time.time()-started,1), "endpoint":ENDPOINT,
        "official_about_url":ABOUT_URL, "official_reported_store_count":company_count, "official_count_fetch_error":count_error,
        "unique_records":len(rows), "unique_shop_ids":len(set(shop_ids)), "records_without_shop_id":len(rows)-len(shop_ids),
        "request_total":requests_done, "unique_query_coordinates":len(queried), "request_errors":len(errors),
        "unqueried_discovered_store_coordinates":unqueried, "workers":WORKERS, "max_requests":MAX_REQUESTS,
        "phase_stats":phases, "record_class_counts":counts("record_class","未分类"),
        "franchise_counts":counts("franchise_label","未提供"), "province_counts":counts("province_inferred","未识别"),
        "city_counts":counts("city","未识别"), "top_parent_entities":dict(Counter(text(r.get("parentName")) or "未提供" for r in rows).most_common(100)),
        "coverage_method":["1-degree national grid", "shifted 1-degree national grid", "recursive store-coordinate expansion",
                           "dense 0.1-degree tile refinement", "conditional 0.5-degree regional refinement"],
        "coverage_note":"Deduplicated records discoverable from the public LBX nearby-store endpoint at crawl time; the endpoint has no documented full-export/count API, so exact identity with the company-reported total cannot be guaranteed."
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    save("completed", "done")
    print(json.dumps({"event":"complete", **summary}, ensure_ascii=False)[:12000], flush=True)

if __name__ == "__main__":
    main()
