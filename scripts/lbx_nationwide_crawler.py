#!/usr/bin/env python3
"""Nationwide crawl of public LBX nearby-store API.

Method
------
1. Cover the company's 18 announced provincial markets, plus provinces where the
   public endpoint returned stores in probes, with a ~20 km grid.
2. Recursively subdivide cells where returned-store distances do not cover the
   whole cell. This handles the endpoint's small top-N response in dense cities.
3. Deduplicate by public shop_id and preserve all source fields.

The crawler is read-only, rate-limited by worker count, retries transient
failures, and records every query for reproducibility.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import os
import random
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union
from shapely.prepared import prep

API_URL = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
BOUNDARY_URL = "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json"
INITIAL_CELL_KM = 20.0
EMPTY_SAFE_RADIUS_KM = 18.0
MIN_CELL_RADIUS_KM = 0.22
MAX_DEPTH = 8
API_TOP_N = 10
THREADS = int(os.getenv("LBX_THREADS", "8"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
    "Origin": "https://yx.lbxcn.com",
    "X-Requested-With": "XMLHttpRequest",
}

# 18 provincial markets publicly announced by LBX, plus Jilin/Beijing/Sichuan,
# where the public nearby-store endpoint returned records in probes.
PROVINCES = {
    "beijing": ("110000", "北京市"),
    "tianjin": ("120000", "天津市"),
    "shanxi": ("140000", "山西省"),
    "inner_mongolia": ("150000", "内蒙古自治区"),
    "jilin": ("220000", "吉林省"),
    "shanghai": ("310000", "上海市"),
    "jiangsu": ("320000", "江苏省"),
    "zhejiang": ("330000", "浙江省"),
    "anhui": ("340000", "安徽省"),
    "jiangxi": ("360000", "江西省"),
    "shandong": ("370000", "山东省"),
    "henan": ("410000", "河南省"),
    "hubei": ("420000", "湖北省"),
    "hunan": ("430000", "湖南省"),
    "guangdong": ("440000", "广东省"),
    "guangxi": ("450000", "广西壮族自治区"),
    "sichuan": ("510000", "四川省"),
    "guizhou": ("520000", "贵州省"),
    "shaanxi": ("610000", "陕西省"),
    "gansu": ("620000", "甘肃省"),
    "ningxia": ("640000", "宁夏回族自治区"),
}

GROUPS = {
    "south_central": ["hunan", "hubei", "jiangxi"],
    "east_coast": ["jiangsu", "anhui", "shanghai", "zhejiang"],
    "north_central": ["henan", "shandong", "shanxi", "beijing", "tianjin"],
    "southwest_south": ["guangdong", "guangxi", "guizhou", "sichuan"],
    "northwest": ["shaanxi", "gansu", "ningxia"],
    "north_northeast": ["inner_mongolia", "jilin"],
}

# Fallback bounding boxes (west, south, east, north), used only if public
# boundary data is temporarily unavailable. They intentionally over-cover.
FALLBACK_BOUNDS = {
    "110000": (115.4, 39.4, 117.6, 41.1), "120000": (116.7, 38.5, 118.1, 40.3),
    "140000": (110.2, 34.3, 114.6, 40.8), "150000": (97.0, 37.4, 126.1, 53.4),
    "220000": (121.6, 40.8, 131.3, 46.3), "310000": (120.8, 30.6, 122.1, 31.9),
    "320000": (116.3, 30.7, 121.9, 35.2), "330000": (118.0, 27.0, 123.0, 31.5),
    "340000": (114.8, 29.4, 119.7, 34.7), "360000": (113.5, 24.4, 118.5, 30.1),
    "370000": (114.5, 34.3, 122.8, 38.5), "410000": (110.3, 31.3, 116.7, 36.4),
    "420000": (108.3, 29.0, 116.3, 33.3), "430000": (108.8, 24.6, 114.3, 30.2),
    "440000": (109.5, 20.1, 117.6, 25.6), "450000": (104.4, 20.9, 112.1, 26.4),
    "510000": (97.3, 26.0, 108.6, 34.3), "520000": (103.6, 24.6, 109.6, 29.2),
    "610000": (105.5, 31.7, 111.3, 37.6), "620000": (92.3, 32.5, 108.8, 42.8),
    "640000": (104.2, 35.2, 107.7, 39.4),
}

_thread_local = threading.local()


def session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session(); s.headers.update(HEADERS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=THREADS * 2, pool_maxsize=THREADS * 2)
        s.mount("https://", adapter)
        _thread_local.session = s
    return s


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def to_float(v: Any) -> float | None:
    try:
        x = float(v)
        if math.isfinite(x): return x
    except Exception:
        return None
    return None


def store_coords(store: dict[str, Any]) -> tuple[float, float] | None:
    for lat_key, lon_key in (("latGd", "lngGd"), ("lat", "lng"), ("latBd", "lngBd")):
        lat, lon = to_float(store.get(lat_key)), to_float(store.get(lon_key))
        if lat is not None and lon is not None and 15 <= lat <= 55 and 70 <= lon <= 140:
            return lat, lon
    return None


def extract_stores(obj: Any) -> list[dict[str, Any]]:
    try:
        value = obj["data"]["data"]
        return value if isinstance(value, list) else []
    except Exception:
        return []


def fetch_stores(lat: float, lon: float) -> dict[str, Any]:
    params = {"Latitude": f"{lat:.7f}", "Longitude": f"{lon:.7f}"}
    errors = []
    for attempt in range(4):
        started = time.time()
        try:
            resp = session().get(API_URL, params=params, timeout=(8, 28))
            elapsed = round(time.time() - started, 3)
            try: obj = resp.json()
            except Exception as exc:
                errors.append(f"json:{type(exc).__name__}:{resp.text[:150]}")
                obj = None
            stores = extract_stores(obj)
            if resp.status_code == 200 and obj is not None:
                return {
                    "ok": True, "status": resp.status_code, "elapsed": elapsed,
                    "stores": stores, "response_code": obj.get("code") if isinstance(obj, dict) else None,
                    "message": obj.get("message") if isinstance(obj, dict) else None,
                    "attempts": attempt + 1,
                }
            errors.append(f"http:{resp.status_code}:{resp.text[:160]}")
        except Exception as exc:  # noqa: BLE001
            elapsed = round(time.time() - started, 3)
            errors.append(f"{type(exc).__name__}:{exc}")
        time.sleep(0.45 * (attempt + 1) + random.random() * 0.2)
    return {"ok": False, "status": None, "elapsed": elapsed, "stores": [], "errors": errors, "attempts": 4}


@dataclass(frozen=True)
class Cell:
    province_key: str
    west: float
    south: float
    east: float
    north: float
    depth: int = 0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.south + self.north) / 2, (self.west + self.east) / 2)

    def radius_km(self) -> float:
        lat, lon = self.center
        return max(haversine_km(lat, lon, y, x) for x, y in (
            (self.west, self.south), (self.west, self.north),
            (self.east, self.south), (self.east, self.north),
        ))

    def split(self) -> list["Cell"]:
        mx = (self.west + self.east) / 2; my = (self.south + self.north) / 2
        d = self.depth + 1; p = self.province_key
        return [
            Cell(p, self.west, self.south, mx, my, d),
            Cell(p, mx, self.south, self.east, my, d),
            Cell(p, self.west, my, mx, self.north, d),
            Cell(p, mx, my, self.east, self.north, d),
        ]


def load_boundaries() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (geom_by_adcode, prepared_by_adcode, raw_geojson)."""
    try:
        r = requests.get(BOUNDARY_URL, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=40)
        r.raise_for_status(); geo = r.json()
        geom_by = {}
        for feat in geo.get("features", []):
            prop = feat.get("properties") or {}
            code = str(prop.get("adcode") or prop.get("code") or "")
            if code:
                geom_by[code] = shape(feat["geometry"])
        if not geom_by: raise ValueError("no province geometries")
        return geom_by, {k: prep(v) for k, v in geom_by.items()}, geo
    except Exception as exc:  # noqa: BLE001
        print(f"Boundary download failed, using bounding boxes: {exc}", flush=True)
        geom_by = {code: box(*bounds) for code, bounds in FALLBACK_BOUNDS.items()}
        geo = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"adcode": code}, "geometry": geom.__geo_interface__}
            for code, geom in geom_by.items()
        ]}
        return geom_by, {k: prep(v) for k, v in geom_by.items()}, geo


def initial_cells(province_key: str, geom: Any) -> list[Cell]:
    minx, miny, maxx, maxy = geom.bounds
    lat_step = INITIAL_CELL_KM / 111.0
    cells = []
    y0 = math.floor(miny / lat_step) * lat_step
    y = y0 + lat_step / 2
    while y - lat_step / 2 < maxy:
        cos_lat = max(0.25, math.cos(math.radians(y)))
        lon_step = INITIAL_CELL_KM / (111.0 * cos_lat)
        x0 = math.floor(minx / lon_step) * lon_step
        x = x0 + lon_step / 2
        while x - lon_step / 2 < maxx:
            c = Cell(province_key, x - lon_step / 2, y - lat_step / 2,
                     x + lon_step / 2, y + lat_step / 2, 0)
            if geom.intersects(box(c.west, c.south, c.east, c.north)):
                cells.append(c)
            x += lon_step
        y += lat_step
    return cells


def query_cell(cell: Cell) -> tuple[Cell, dict[str, Any]]:
    lat, lon = cell.center
    result = fetch_stores(lat, lon)
    return cell, result


def safe_id(store: dict[str, Any]) -> str:
    for k in ("shop_id", "sap_id", "org_code", "deptId", "id"):
        v = str(store.get(k) or "").strip()
        if v: return f"{k}:{v}"
    coords = store_coords(store)
    base = "|".join(str(store.get(k) or "") for k in ("deptName", "deptAddr", "phone"))
    return "fallback:" + re.sub(r"\W+", "", base)[:120] + (f"|{coords[0]:.6f},{coords[1]:.6f}" if coords else "")


def crawl_group(group: str, output_root: Path) -> None:
    if group not in GROUPS: raise SystemExit(f"Unknown group: {group}")
    geom_by, _, geo = load_boundaries()
    selected = GROUPS[group]
    geoms: dict[str, Any] = {}
    for key in selected:
        code, _ = PROVINCES[key]
        if code not in geom_by:
            if code in FALLBACK_BOUNDS: geom_by[code] = box(*FALLBACK_BOUNDS[code])
            else: raise RuntimeError(f"Missing geometry for {key}/{code}")
        geoms[key] = geom_by[code]

    out = output_root; out.mkdir(parents=True, exist_ok=True)
    queue: deque[Cell] = deque()
    for key in selected:
        cells = initial_cells(key, geoms[key]); queue.extend(cells)
        print(f"{group}: {key} initial cells={len(cells)}", flush=True)

    seen_query: set[tuple[str, int, int]] = set()
    stores_by_id: dict[str, dict[str, Any]] = {}
    occurrences: defaultdict[str, int] = defaultdict(int)
    source_provinces: defaultdict[str, set[str]] = defaultdict(set)
    query_log: list[dict[str, Any]] = []
    error_count = 0; processed = 0; subdivided = 0; start = time.time()

    while queue:
        batch: list[Cell] = []
        while queue and len(batch) < THREADS * 8:
            c = queue.popleft(); lat, lon = c.center
            qkey = (c.province_key, round(lat * 10_000_000), round(lon * 10_000_000))
            if qkey in seen_query: continue
            seen_query.add(qkey); batch.append(c)
        if not batch: continue
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as pool:
            results = list(pool.map(query_cell, batch))
        for cell, result in results:
            processed += 1
            lat, lon = cell.center; ss = result.get("stores", []) if result.get("ok") else []
            if not result.get("ok"): error_count += 1
            dists = []
            new_ids = 0
            for store in ss:
                sid = safe_id(store); occurrences[sid] += 1; source_provinces[sid].add(cell.province_key)
                if sid not in stores_by_id:
                    stores_by_id[sid] = dict(store); new_ids += 1
                coords = store_coords(store)
                if coords:
                    dists.append(haversine_km(lat, lon, coords[0], coords[1]))
            dmax = max(dists) if dists else None
            cell_radius = cell.radius_km()
            # Conservative coverage: empty responses use the empirically observed
            # >=18 km search reach; non-empty responses use only returned-store
            # distance, forcing refinement around every active cluster.
            coverage = EMPTY_SAFE_RADIUS_KM if not ss else max(0.35, dmax or 0.35)
            should_split = (
                result.get("ok") and coverage + 0.04 < cell_radius
                and cell.depth < MAX_DEPTH and cell_radius > MIN_CELL_RADIUS_KM
            )
            added_children = 0
            if should_split:
                pg = geoms[cell.province_key]
                for child in cell.split():
                    if pg.intersects(box(child.west, child.south, child.east, child.north)):
                        queue.append(child); added_children += 1
                subdivided += 1
            query_log.append({
                "province_key": cell.province_key, "query_lat": round(lat, 7), "query_lng": round(lon, 7),
                "depth": cell.depth, "cell_radius_km": round(cell_radius, 4),
                "coverage_km": round(coverage, 4), "store_count": len(ss),
                "new_store_count": new_ids, "max_store_distance_km": round(dmax, 4) if dmax is not None else "",
                "subdivided": int(should_split), "children": added_children,
                "ok": int(bool(result.get("ok"))), "status": result.get("status"),
                "elapsed": result.get("elapsed"), "attempts": result.get("attempts"),
                "error": " | ".join(result.get("errors", []))[:500],
            })
        if processed % 500 < len(batch):
            print(f"{group}: queries={processed}, queued={len(queue)}, unique={len(stores_by_id)}, errors={error_count}, depth={max((q['depth'] for q in query_log), default=0)}", flush=True)
            # Lightweight checkpoint in case a long group is interrupted.
            checkpoint = {"group": group, "queries": processed, "queued": len(queue), "unique_stores": len(stores_by_id), "errors": error_count, "elapsed_sec": round(time.time()-start,1)}
            (out / f"checkpoint_{group}.json").write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")

    # Enrich occurrence/source metadata without altering original API fields.
    rows = []
    for sid, store in stores_by_id.items():
        row = dict(store)
        row["_crawl_id"] = sid
        row["_occurrences"] = occurrences[sid]
        row["_source_province_keys"] = sorted(source_provinces[sid])
        rows.append(row)
    rows.sort(key=lambda r: (str(r.get("shop_id") or ""), str(r.get("deptName") or "")))
    with (out / f"stores_{group}.jsonl").open("w", encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    qcols = list(query_log[0]) if query_log else []
    with (out / f"queries_{group}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=qcols); w.writeheader(); w.writerows(query_log)
    summary = {
        "group": group, "province_keys": selected,
        "provinces": [PROVINCES[k][1] for k in selected],
        "api_url": API_URL, "started_at_utc": datetime.fromtimestamp(start, tz=timezone.utc).isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": round(time.time() - start, 1), "query_count": processed,
        "unique_store_record_count": len(rows), "error_count": error_count,
        "subdivided_cell_count": subdivided, "max_depth": max((q["depth"] for q in query_log), default=0),
        "initial_cell_km": INITIAL_CELL_KM, "empty_safe_radius_km": EMPTY_SAFE_RADIUS_KM,
        "min_cell_radius_km": MIN_CELL_RADIUS_KM, "max_depth_setting": MAX_DEPTH,
    }
    (out / f"summary_{group}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def normalize_phone(v: Any) -> str:
    return re.sub(r"\D+", "", str(v or ""))


def normalize_text(v: Any) -> str:
    return re.sub(r"[\s,，。.;；:：()（）\-—_/]+", "", str(v or "").lower())


def merge_parts(parts_root: Path, output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    all_records: dict[str, dict[str, Any]] = {}
    occurrences: defaultdict[str, int] = defaultdict(int)
    source_groups: defaultdict[str, set[str]] = defaultdict(set)
    source_provinces: defaultdict[str, set[str]] = defaultdict(set)
    summaries = []
    for p in sorted(parts_root.rglob("summary_*.json")):
        try: summaries.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception: pass
    for p in sorted(parts_root.rglob("stores_*.jsonl")):
        group = p.stem.removeprefix("stores_")
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            r = json.loads(line); sid = r.get("_crawl_id") or safe_id(r)
            occurrences[sid] += int(r.get("_occurrences") or 1)
            source_groups[sid].add(group)
            source_provinces[sid].update(r.get("_source_province_keys") or [])
            if sid not in all_records: all_records[sid] = r
            else:
                # Fill blanks with values observed in another query/group.
                base = all_records[sid]
                for k, v in r.items():
                    if (base.get(k) is None or str(base.get(k)).strip() == "") and v not in (None, "", []):
                        base[k] = v

    geom_by, _, raw_geo = load_boundaries()
    province_shapes = [(code, PROVINCES[key][1], geom_by.get(code)) for key, (code, _) in PROVINCES.items() if geom_by.get(code) is not None]
    rows = []
    for sid, r in all_records.items():
        coords = store_coords(r); province = ""; province_code = ""
        if coords:
            pt = Point(coords[1], coords[0])
            for code, name, geom in province_shapes:
                if geom.covers(pt): province_code, province = code, name; break
        row = dict(r)
        row["_crawl_id"] = sid; row["_occurrences"] = occurrences[sid]
        row["_source_groups"] = sorted(source_groups[sid]); row["_source_province_keys"] = sorted(source_provinces[sid])
        row["_province_code_spatial"] = province_code; row["_province_spatial"] = province
        rows.append(row)
    rows.sort(key=lambda r: (r.get("_province_code_spatial", ""), str(r.get("city") or ""), str(r.get("deptName") or ""), str(r.get("shop_id") or "")))

    # Physical-location grouping: retain every shop_id in raw data, but add a
    # conservative suspected-same-location group for the user-facing workbook.
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(i,j):
        a,b=find(i),find(j)
        if a!=b: parent[b]=a
    buckets: defaultdict[tuple[int,int], list[int]] = defaultdict(list)
    for i,r in enumerate(rows):
        c=store_coords(r)
        if c: buckets[(round(c[0]*100), round(c[1]*100))].append(i)
    for (a,b), idxs in list(buckets.items()):
        candidates=[]
        for da in (-1,0,1):
            for db in (-1,0,1): candidates.extend(buckets.get((a+da,b+db),[]))
        for i in idxs:
            ci=store_coords(rows[i]); pi=normalize_phone(rows[i].get("phone")); ai=normalize_text(rows[i].get("deptAddr")); oi=str(rows[i].get("org_code") or "")
            if not ci: continue
            for j in candidates:
                if j<=i: continue
                cj=store_coords(rows[j])
                if not cj or haversine_km(ci[0],ci[1],cj[0],cj[1])>0.08: continue
                pj=normalize_phone(rows[j].get("phone")); aj=normalize_text(rows[j].get("deptAddr")); oj=str(rows[j].get("org_code") or "")
                same_phone=bool(pi and pj and pi==pj); same_org=bool(oi and oj and oi==oj)
                addr_match=bool(ai and aj and (ai in aj or aj in ai or (len(set(ai)&set(aj))/max(1,len(set(ai)|set(aj)))>0.72)))
                if same_phone or same_org or addr_match: union(i,j)
    root_to_group={}; group_seq=0
    for i,r in enumerate(rows):
        root=find(i)
        if root not in root_to_group: group_seq+=1; root_to_group[root]=f"P{group_seq:06d}"
        r["_physical_group_id"]=root_to_group[root]
    group_sizes=defaultdict(int)
    for r in rows: group_sizes[r["_physical_group_id"]]+=1
    for r in rows: r["_physical_group_size"]=group_sizes[r["_physical_group_id"]]

    with (output_root/"stores_all.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+"\n")
    # Flatten to CSV with stable, useful fields first; retain all API fields.
    preferred=["shop_id","sap_id","org_code","deptName","parentName","deptAddr","phone","city","latGd","lngGd","latBd","lngBd","shopLabels","sales_scan_name","is_m_shop","is_close","summer_start_hours","summer_closing_hours","winter_start_hours","winter_closing_hours","shipStartTime","shipEndTime","companyCode","pdeptId","third_org_name","third_org_code","org_name","deptType","_province_code_spatial","_province_spatial","_physical_group_id","_physical_group_size","_occurrences","_source_groups","_source_province_keys","_crawl_id"]
    keys=set().union(*(r.keys() for r in rows)) if rows else set(); fields=preferred+[k for k in sorted(keys) if k not in preferred]
    with (output_root/"stores_all.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader()
        for r in rows:
            x={k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v) for k,v in r.items()};w.writerow(x)
    # Compact query log by concatenation.
    qfiles=sorted(parts_root.rglob("queries_*.csv")); qrows=[]
    for p in qfiles:
        with p.open(encoding="utf-8-sig",newline="") as f:qrows.extend(csv.DictReader(f))
    if qrows:
        with (output_root/"crawl_queries.csv").open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(qrows[0]));w.writeheader();w.writerows(qrows)
    counts=defaultdict(int); physical=defaultdict(set)
    for r in rows:
        p=r.get("_province_spatial") or "未识别";counts[p]+=1;physical[p].add(r["_physical_group_id"])
    manifest={
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),"api_url":API_URL,
        "raw_unique_shop_record_count":len(rows),"suspected_physical_location_count":len(group_sizes),
        "query_count":len(qrows),"part_summaries":summaries,
        "raw_count_by_province":dict(sorted(counts.items())),
        "physical_count_by_province":{k:len(v) for k,v in sorted(physical.items())},
        "method":{"initial_cell_km":INITIAL_CELL_KM,"empty_safe_radius_km":EMPTY_SAFE_RADIUS_KM,"min_cell_radius_km":MIN_CELL_RADIUS_KM,"max_depth":MAX_DEPTH,"api_top_n_observed":API_TOP_N},
        "scope_note":"Public LBX H5 nearby-store API records discoverable through adaptive geographic sampling; not an official corporate export.",
    }
    (output_root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (output_root/"province_boundaries_used.geojson").write_text(json.dumps(raw_geo,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2),flush=True)


def main() -> None:
    ap=argparse.ArgumentParser();ap.add_argument("--group",choices=sorted(GROUPS));ap.add_argument("--merge",type=Path);ap.add_argument("--output",type=Path,required=True);args=ap.parse_args()
    if args.merge: merge_parts(args.merge,args.output)
    elif args.group: crawl_group(args.group,args.output)
    else: ap.error("provide --group or --merge")

if __name__=="__main__":main()
