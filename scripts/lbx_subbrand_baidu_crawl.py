#!/usr/bin/env python3
"""Target Baidu POIs for LBX-affiliated regional pharmacy banners.

The keyword list is derived from parent-company names returned by LBX's public
nearby-store interface. Results are restricted to the matching provincial
market and require the regional banner token in the POI name/brand.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import re
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lbx_baidu_base", ROOT / "scripts/lbx_baidu_national_crawl.py")
base = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(base)

OUT = Path("lbx_subbrand_output")
OUT.mkdir(exist_ok=True)
ADMIN_URL = "https://raw.githubusercontent.com/simonkuang/cn-pcas-geo/main/xzqh_with_amap_coordinates.json"
CRAWL_TIME = datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0).isoformat()
MAX_WORKERS = 10
MAX_PAGES = 120

KEYWORDS_BY_PROVINCE = {
    "江苏省": ["普泽大药房", "海鹏医药", "三品堂大药房", "万仁大药房", "百佳惠苏禾大药房", "苏禾大药房", "新千秋大药房", "国医药业"],
    "安徽省": ["百姓缘大药房", "邻加医大药房"],
    "湖南省": ["怀仁大药房", "怀仁药房", "百高药房"],
    "陕西省": ["三秦济生堂", "济生堂大药房", "同鑫康泽医药"],
    "山东省": ["春天大药房"],
    "宁夏回族自治区": ["惠仁堂药房", "惠仁堂大药房", "同盛祥同济堂"],
    "甘肃省": ["惠仁堂药房", "惠仁堂大药房"],
    "广西壮族自治区": ["国人大药房", "湘湘医药"],
    "山西省": ["百汇医药", "百汇大药房"],
    "内蒙古自治区": ["泽强大药房"],
}


def text(v: Any) -> str:
    return base.stringify(v)


def normalize(v: Any) -> str:
    s = unicodedata.normalize("NFKC", text(v)).lower()
    return re.sub(r"[\s\-—_()（）【】\[\]·,，.。/\\]+", "", s)


def normalize_admin(name: str) -> str:
    s = normalize(name)
    for suffix in ("壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "自治州", "自治县", "地区", "盟", "省", "市"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    return s


def build_city_province() -> dict[str, str]:
    r = requests.get(ADMIN_URL, timeout=60, headers={"User-Agent": base.USER_AGENTS[0]})
    r.raise_for_status()
    tree = r.json()
    mapping: dict[str, str] = {}

    def walk(node: dict[str, Any], province: str = "") -> None:
        level = text(node.get("level"))
        name = text(node.get("name"))
        if level == "province":
            province = name
        elif level == "city" and name and province:
            mapping[normalize_admin(name)] = province
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, province)

    for root in tree:
        if isinstance(root, dict):
            walk(root)
    for municipality in ("北京市", "天津市", "上海市", "重庆市"):
        mapping[normalize_admin(municipality)] = municipality
    aliases = {
        "湘西": "湖南省", "恩施": "湖北省", "黔东南": "贵州省", "黔南": "贵州省",
        "黔西南": "贵州省", "桂西": "广西壮族自治区", "阿拉善": "内蒙古自治区",
        "锡林郭勒": "内蒙古自治区", "巴彦淖尔": "内蒙古自治区",
    }
    mapping.update(aliases)
    return mapping


def load_baidu_codes() -> dict[str, str]:
    r = requests.get(base.CITY_CODE_URL, timeout=45, headers={"User-Agent": base.USER_AGENTS[0]})
    r.raise_for_status()
    payload = r.json()
    result = {}
    for code, meta in payload.items():
        try:
            if int(code) <= 32:
                continue
        except (TypeError, ValueError):
            continue
        result[str(code)] = text(meta.get("zh")) if isinstance(meta, dict) else ""
    return result


def keyword_core(keyword: str) -> str:
    for suffix in ("健康大药房", "大药房", "健康药房", "药房", "医药", "药业"):
        if keyword.endswith(suffix):
            core = keyword[:-len(suffix)]
            if len(core) >= 2:
                return core
    return keyword


def matches_keyword(name: str, brand_name: str, keyword: str) -> bool:
    n = normalize(name + brand_name)
    k = normalize(keyword)
    core = normalize(keyword_core(keyword))
    return k in n or (len(core) >= 2 and core in n)


def extract(item: dict[str, Any], keyword: str, expected_province: str, city_code: str, page: int, current_city: dict[str, Any]) -> dict[str, Any] | None:
    admin = item.get("admin_info") or {}
    detail = ((item.get("ext") or {}).get("detail_info") or {})
    brand = item.get("brand_id") or detail.get("brand_id") or {}
    if not isinstance(brand, dict):
        brand = {}
    name = text(item.get("name"))
    brand_name = text(brand.get("name"))
    if not matches_keyword(name, brand_name, keyword):
        return None
    if any(x in name for x in ("总部", "办公楼", "总部大楼", "物流中心", "配送中心", "仓库", "培训中心")):
        return None
    tag = text(item.get("std_tag") or detail.get("tag"))
    if ("有限公司" in name or "股份公司" in name) and not any(x in tag for x in ("药店", "药房")):
        return None
    province = base.normalize_province(admin.get("province_name") or current_city.get("up_province_name"))
    if province != expected_province:
        return None
    city = text(admin.get("city_name") or current_city.get("name"))
    district = text(admin.get("area_name"))
    address = text(item.get("addr") or item.get("poi_address") or detail.get("address"))
    phone = text(detail.get("phone") or item.get("tel") or detail.get("tel"))
    hours = text(detail.get("shop_hours") or item.get("shop_hours") or detail.get("business_time") or item.get("business_time"))
    uid = text(item.get("uid"))
    x_raw = item.get("x") if item.get("x") is not None else item.get("diPointX")
    y_raw = item.get("y") if item.get("y") is not None else item.get("diPointY")
    bd_lon, bd_lat = base.bdmc_to_bd09(x_raw, y_raw)
    gcj_lon, gcj_lat = base.bd09_to_gcj02(bd_lon, bd_lat)
    wgs_lon, wgs_lat = base.gcj02_to_wgs84(gcj_lon, gcj_lat)
    return {
        "门店名称": name, "挂牌子品牌": keyword, "省份": province, "城市": city, "区县": district,
        "详细地址": address, "联系电话": phone, "营业时间": hours, "POI分类": tag,
        "火星经度_GCJ02": gcj_lon, "火星纬度_GCJ02": gcj_lat,
        "百度经度_BD09": bd_lon, "百度纬度_BD09": bd_lat,
        "WGS84经度_近似": wgs_lon, "WGS84纬度_近似": wgs_lat,
        "百度POI_UID": uid, "百度品牌ID": text(brand.get("id")), "百度品牌名": brand_name,
        "来源详情页": f"https://map.baidu.com/mobile/webapp/place/detail/qt=ninf&uid={uid}" if uid else "",
        "查询城市码": city_code, "查询页码": page, "数据源": "百度地图公开可检索POI",
        "关联依据": "关键词来自老百姓公开附近门店接口的经营主体/区域连锁名称；需结合集团口径复核",
        "抓取时间": CRAWL_TIME,
    }


def crawl(code: str, hint: str, expected_province: str, keyword: str):
    stats = {"城市码": code, "城市提示": hint, "省份": expected_province, "关键词": keyword, "状态": "", "检索总数": 0, "抓取页数": 0, "纳入数": 0, "错误": ""}
    rows = []
    try:
        first = base.fetch_page(code, keyword, 0)
        current_city = first.get("current_city") or {}
        actual_code = text(current_city.get("code"))
        province = base.normalize_province(current_city.get("up_province_name"))
        if actual_code and actual_code != code:
            stats["状态"] = "跳过：城市码重定向"; return rows, stats
        if province != expected_province:
            stats["状态"] = "跳过：省份不符"; return rows, stats
        total = base.safe_total(first)
        pages = min(MAX_PAGES, max(1, math.ceil(total / 10))) if total else 1
        stats["检索总数"] = total
        for page in range(pages):
            payload = first if page == 0 else base.fetch_page(code, keyword, page)
            content = payload.get("content") or []
            if not isinstance(content, list): content = []
            stats["抓取页数"] += 1
            for item in content:
                if isinstance(item, dict):
                    record = extract(item, keyword, expected_province, code, page, current_city)
                    if record: rows.append(record)
            if not content or (payload.get("pageInfo") or {}).get("isLast") is True:
                break
        stats["状态"] = "成功"; stats["纳入数"] = len(rows)
    except Exception as exc:  # noqa: BLE001
        stats["状态"] = "失败"; stats["错误"] = repr(exc)
    return rows, stats


def richness(row: dict[str, Any]) -> int:
    return sum(bool(row.get(k)) for k in ("详细地址", "联系电话", "营业时间", "火星经度_GCJ02", "百度品牌ID", "POI分类"))


def main() -> None:
    city_province = build_city_province()
    city_codes = load_baidu_codes()
    tasks = []
    for code, hint in city_codes.items():
        province = city_province.get(normalize_admin(hint), "")
        for keyword in KEYWORDS_BY_PROVINCE.get(province, []):
            tasks.append((code, hint, province, keyword))
    print(f"targeted tasks={len(tasks)} workers={MAX_WORKERS}", flush=True)
    raw, stats = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {pool.submit(crawl, *task): task for task in tasks}
        for i, fut in enumerate(as_completed(future_map), 1):
            rows, st = fut.result(); raw.extend(rows); stats.append(st)
            if i % 25 == 0:
                print(f"progress {i}/{len(tasks)} raw={len(raw)}", flush=True)
    merged: dict[str, dict[str, Any]] = {}
    for row in raw:
        key = row.get("百度POI_UID") or "|".join(normalize(row.get(k)) for k in ("省份", "城市", "门店名称", "详细地址"))
        if key not in merged or richness(row) > richness(merged[key]):
            merged[key] = row
        else:
            old = merged[key]
            for k, v in row.items():
                if not old.get(k) and v: old[k] = v
    rows = sorted(merged.values(), key=lambda r: (r.get("省份", ""), r.get("城市", ""), r.get("区县", ""), r.get("门店名称", "")))
    for i, row in enumerate(rows, 1): row["序号"] = i
    fields = ["序号", "门店名称", "挂牌子品牌", "省份", "城市", "区县", "详细地址", "联系电话", "营业时间", "POI分类", "火星经度_GCJ02", "火星纬度_GCJ02", "百度经度_BD09", "百度纬度_BD09", "WGS84经度_近似", "WGS84纬度_近似", "百度POI_UID", "百度品牌ID", "百度品牌名", "来源详情页", "查询城市码", "查询页码", "数据源", "关联依据", "抓取时间"]
    with (OUT / "lbx_subbrand_poi.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    with (OUT / "lbx_subbrand_poi.json").open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    stat_fields = ["城市码", "城市提示", "省份", "关键词", "状态", "检索总数", "抓取页数", "纳入数", "错误"]
    with (OUT / "task_stats.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=stat_fields, extrasaction="ignore"); w.writeheader(); w.writerows(sorted(stats, key=lambda x:(x["省份"],x["城市提示"],x["关键词"])))
    report = {
        "抓取时间": CRAWL_TIME, "任务数": len(tasks), "成功任务数": sum(s["状态"]=="成功" for s in stats),
        "失败任务数": sum(s["状态"]=="失败" for s in stats), "原始行数": len(raw), "去重后POI数": len(rows),
        "省份统计": Counter(r["省份"] for r in rows), "子品牌统计": Counter(r["挂牌子品牌"] for r in rows),
        "口径": "集团公开附近门店接口所示区域经营主体名称对应的地图POI候选；不等同于集团工商/财务口径全量台账",
    }
    (OUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

if __name__ == "__main__":
    main()
