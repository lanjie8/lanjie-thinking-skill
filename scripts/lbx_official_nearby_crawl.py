#!/usr/bin/env python3
"""Collect LBX stores exposed by the public H5 nearby-store endpoint.

This is a coverage crawl, not an internal master-data export. It queries
administrative centres in the 18 markets disclosed by LBX and adds denser
sampling around urban districts and saturated query points. Personal contact
names are deliberately excluded from output.
"""
from __future__ import annotations

import concurrent.futures
import csv
import json
import math
import random
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

OUT = Path("lbx_official_nearby_output")
OUT.mkdir(exist_ok=True)
ADMIN_URL = "https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/xzqh_with_amap_coordinates.json"
ENDPOINT = "https://yx.lbxcn.com/out/2212sping/getlbxStoreList"
OFFICIAL_PROVINCES = {
    "湖南省", "江苏省", "安徽省", "甘肃省", "陕西省", "广西壮族自治区",
    "内蒙古自治区", "天津市", "湖北省", "浙江省", "山西省", "河南省",
    "山东省", "上海市", "宁夏回族自治区", "贵州省", "广东省", "江西省",
}
MAX_WORKERS = 24
TIMEOUT = 25
RETRIES = 3
_thread = threading.local()
_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def session() -> requests.Session:
    value = getattr(_thread, "session", None)
    if value is None:
        value = requests.Session()
        value.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4",
            "Origin": "https://yx.lbxcn.com",
        })
        _thread.session = value
    return value


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def center_of(node: dict[str, Any]) -> tuple[float | None, float | None]:
    c = node.get("center")
    if isinstance(c, dict):
        lon = as_float(c.get("longitude") or c.get("lng") or c.get("lon"))
        lat = as_float(c.get("latitude") or c.get("lat"))
        return lon, lat
    if isinstance(c, str) and "," in c:
        a, b = c.split(",", 1)
        return as_float(a), as_float(b)
    return None, None


def walk_admin(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    def walk(node: dict[str, Any], province: str = "", city: str = "") -> None:
        nonlocal rows
        level = str(node.get("level") or "")
        name = str(node.get("name") or "")
        code = str(node.get("code") or node.get("adcode") or "")
        if level == "province" or (len(code) == 6 and code.endswith("0000")):
            province = name
        elif level in {"city", "prefecture"} or (len(code) == 6 and code.endswith("00") and not code.endswith("0000")):
            city = name
        lon, lat = center_of(node)
        if province in OFFICIAL_PROVINCES and lon is not None and lat is not None:
            rows.append({
                "code": code,
                "name": name,
                "level": level,
                "province": province,
                "city": city,
                "longitude": lon,
                "latitude": lat,
            })
        children = node.get("children") or node.get("districts") or []
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    walk(child, province, city)
    for root in nodes:
        if isinstance(root, dict):
            walk(root)
    return rows


def quantize(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 5), round(lon, 5)


def make_points(admin: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: dict[tuple[float, float], dict[str, Any]] = {}
    for row in admin:
        code = row["code"]
        name = row["name"]
        level = row["level"]
        lon = row["longitude"]
        lat = row["latitude"]
        # Prefer district/county and city centres; province centres add little.
        is_city = level in {"city", "prefecture"} or (len(code) == 6 and code.endswith("00") and not code.endswith("0000"))
        is_district = level in {"district", "county", "area"} or (len(code) == 6 and not code.endswith("00"))
        if not (is_city or is_district):
            continue
        base = {
            "province": row["province"], "city": row["city"], "seed_name": name,
            "seed_code": code, "seed_level": level, "point_kind": "行政中心",
        }
        points[quantize(lat, lon)] = {**base, "latitude": lat, "longitude": lon}
        # Denser sampling for urban districts and municipality districts.
        urban = name.endswith("区") or row["province"] in {"天津市", "上海市"}
        if is_district and urban:
            for delta in (0.035, 0.075):
                for dlat, dlon, label in [
                    (delta, 0, "北"), (-delta, 0, "南"), (0, delta, "东"), (0, -delta, "西"),
                    (delta, delta, "东北"), (delta, -delta, "西北"), (-delta, delta, "东南"), (-delta, -delta, "西南"),
                ]:
                    p = quantize(lat + dlat, lon + dlon)
                    points[p] = {**base, "latitude": p[0], "longitude": p[1], "point_kind": f"城区偏移{label}{delta}"}
    return list(points.values())


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    try:
        rows = payload["data"]["data"]
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def request_point(point: dict[str, Any]) -> dict[str, Any]:
    params = {"Latitude": point["latitude"], "Longitude": point["longitude"]}
    last_error = ""
    for attempt in range(RETRIES):
        try:
            response = session().get(ENDPOINT, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            rows = extract_rows(payload)
            return {
                **point,
                "status": response.status_code,
                "row_count": len(rows),
                "rows": rows,
                "request_url": response.url,
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
            try:
                session().close()
            except Exception:
                pass
            _thread.session = None
            time.sleep((1.4 ** attempt) + random.uniform(0.05, 0.3))
    return {**point, "status": None, "row_count": 0, "rows": [], "request_url": "", "error": last_error}


def store_key(row: dict[str, Any]) -> str:
    for key in ("shop_id", "sap_id", "org_code"):
        value = str(row.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    name = re.sub(r"\s+", "", str(row.get("deptName") or ""))
    addr = re.sub(r"\s+", "", str(row.get("deptAddr") or ""))
    lat = str(row.get("latGd") or row.get("lat") or "")[:12]
    lon = str(row.get("lngGd") or row.get("lng") or "")[:13]
    return f"fallback:{name}|{addr}|{lat}|{lon}"


def phone_privacy(value: Any) -> str:
    text = str(value or "").strip()
    # The H5 endpoint sometimes exposes a staff mobile rather than a switchboard.
    # Preserve landlines; mask mainland mobile numbers in the deliverable.
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        return digits[:3] + "****" + digits[-4:]
    return text


def normalise(row: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
    lat = as_float(row.get("latGd") or row.get("lat"))
    lon = as_float(row.get("lngGd") or row.get("lng"))
    distance = as_float(row.get("distanceGd") or row.get("distance"))
    winter = "-".join(x for x in [str(row.get("winter_start_hours") or ""), str(row.get("winter_closing_hours") or "")] if x)
    summer = "-".join(x for x in [str(row.get("summer_start_hours") or ""), str(row.get("summer_closing_hours") or "")] if x)
    ship = "-".join(x for x in [str(row.get("shipStartTime") or ""), str(row.get("shipEndTime") or "")] if x)
    return {
        "官方门店键": store_key(row),
        "门店名称": str(row.get("deptName") or "").strip(),
        "上级公司": str(row.get("parentName") or "").strip(),
        "省份_查询归属": query.get("province", ""),
        "城市_接口": str(row.get("city") or "").strip(),
        "城市_查询归属": query.get("city", ""),
        "区县_最近查询点": query.get("seed_name", ""),
        "详细地址": str(row.get("deptAddr") or "").strip(),
        "联系电话_脱敏": phone_privacy(row.get("phone")),
        "门店标签": str(row.get("shopLabels") or "").strip(),
        "门店规模分类": str(row.get("sales_scan_name") or "").strip(),
        "冬季营业时间": winter,
        "夏季营业时间": summer,
        "配送时间": ship,
        "经度_GCJ02": lon,
        "纬度_GCJ02": lat,
        "百度经度_BD09": as_float(row.get("lngBd")),
        "百度纬度_BD09": as_float(row.get("latBd")),
        "shop_id": str(row.get("shop_id") or "").strip(),
        "sap_id": str(row.get("sap_id") or "").strip(),
        "companyCode": str(row.get("companyCode") or "").strip(),
        "org_code": str(row.get("org_code") or "").strip(),
        "org_name": str(row.get("org_name") or "").strip(),
        "third_org_code": str(row.get("third_org_code") or "").strip(),
        "third_org_name": str(row.get("third_org_name") or "").strip(),
        "is_m_shop": str(row.get("is_m_shop") or "").strip(),
        "is_close": str(row.get("is_close") or "").strip(),
        "查询距离_公里": distance,
        "数据源": "老百姓自有H5公开附近门店接口",
        "来源URL": ENDPOINT,
        "抓取时间": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def main() -> None:
    admin_response = requests.get(ADMIN_URL, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
    admin_response.raise_for_status()
    tree = admin_response.json()
    admin = walk_admin(tree)
    points = make_points(admin)
    log(f"admin rows={len(admin)} query points={len(points)}")

    query_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(request_point, point): point for point in points}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            query_results.append(result)
            done += 1
            if done % 250 == 0 or result.get("error"):
                log(f"[{done}/{len(points)}] stores={result.get('row_count')} error={bool(result.get('error'))}")

    # Add a small adaptive ring around saturated points only.
    existing = {quantize(p["latitude"], p["longitude"]) for p in points}
    adaptive: list[dict[str, Any]] = []
    for result in query_results:
        if result.get("row_count") != 10:
            continue
        lat = float(result["latitude"]); lon = float(result["longitude"])
        for dlat, dlon, label in [(0.12,0,"北"),(-0.12,0,"南"),(0,0.12,"东"),(0,-0.12,"西")]:
            q = quantize(lat+dlat, lon+dlon)
            if q in existing:
                continue
            existing.add(q)
            adaptive.append({
                "province": result.get("province", ""), "city": result.get("city", ""),
                "seed_name": result.get("seed_name", ""), "seed_code": result.get("seed_code", ""),
                "seed_level": result.get("seed_level", ""), "point_kind": f"饱和点扩展{label}",
                "latitude": q[0], "longitude": q[1],
            })
    if adaptive:
        log(f"adaptive points={len(adaptive)}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(request_point, point) for point in adaptive]
            for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                query_results.append(future.result())
                if i % 250 == 0:
                    log(f"adaptive [{i}/{len(adaptive)}]")

    stores: dict[str, dict[str, Any]] = {}
    occurrences: Counter[str] = Counter()
    for result in query_results:
        for raw in result.get("rows") or []:
            if not isinstance(raw, dict):
                continue
            row = normalise(raw, result)
            key = row["官方门店键"]
            occurrences[key] += 1
            current = stores.get(key)
            if current is None or (row.get("查询距离_公里") is not None and (current.get("查询距离_公里") is None or row["查询距离_公里"] < current["查询距离_公里"])):
                stores[key] = row
    rows = list(stores.values())
    rows.sort(key=lambda r: (r["省份_查询归属"], r["城市_接口"] or r["城市_查询归属"], r["门店名称"], r["官方门店键"]))
    for i, row in enumerate(rows, 1):
        row["序号"] = i
        row["被不同查询点发现次数"] = occurrences[row["官方门店键"]]

    fields = [
        "序号", "门店名称", "上级公司", "省份_查询归属", "城市_接口", "城市_查询归属", "区县_最近查询点",
        "详细地址", "联系电话_脱敏", "门店标签", "门店规模分类", "冬季营业时间", "夏季营业时间", "配送时间",
        "经度_GCJ02", "纬度_GCJ02", "百度经度_BD09", "百度纬度_BD09", "shop_id", "sap_id", "companyCode",
        "org_code", "org_name", "third_org_code", "third_org_name", "is_m_shop", "is_close", "查询距离_公里",
        "被不同查询点发现次数", "官方门店键", "数据源", "来源URL", "抓取时间",
    ]
    with (OUT / "official_nearby_stores.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)

    query_fields = [
        "province", "city", "seed_name", "seed_code", "seed_level", "point_kind", "latitude", "longitude",
        "status", "row_count", "request_url", "error",
    ]
    with (OUT / "query_log.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=query_fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(query_results)

    summary = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "admin_reference_url": ADMIN_URL,
        "endpoint": ENDPOINT,
        "official_markets": sorted(OFFICIAL_PROVINCES),
        "admin_rows_in_markets": len(admin),
        "query_points": len(query_results),
        "query_success": sum(1 for q in query_results if q.get("status") == 200),
        "query_failures": sum(1 for q in query_results if q.get("error")),
        "unique_stores": len(rows),
        "stores_by_seed_province": dict(Counter(r["省份_查询归属"] for r in rows)),
        "stores_with_address": sum(1 for r in rows if r.get("详细地址")),
        "stores_with_coords": sum(1 for r in rows if r.get("经度_GCJ02") is not None),
        "privacy_note": "contactPerson excluded; mainland mobile numbers in phone field masked",
        "coverage_note": "Public nearby-search coverage crawl; the endpoint returns a limited nearest-store set and ignores pagination parameters, so this is not guaranteed to equal LBX internal master data.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
