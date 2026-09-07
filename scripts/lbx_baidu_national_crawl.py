#!/usr/bin/env python3
"""Collect publicly searchable LBX pharmacy POIs from Baidu Maps mobile pages.

Scope:
- Signboard/query name "老百姓大药房"
- Signboard/query name "老百姓健康药房"
- Only the 18 provincial markets disclosed by LBX

The script uses a small number of concurrent workers, retries transient failures,
and stores both normalized rows and crawl diagnostics. It does not attempt to
bypass login, CAPTCHA, or access controls.
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

OUT = Path("lbx_crawl_output")
OUT.mkdir(exist_ok=True)

KEYWORDS = ("老百姓大药房", "老百姓健康药房")
BRAND_IDS = {
    "2445": "老百姓大药房",
    "72013877": "老百姓健康药房",
}
OFFICIAL_PROVINCES = {
    "湖南省", "江苏省", "安徽省", "甘肃省", "陕西省", "广西壮族自治区",
    "内蒙古自治区", "天津市", "湖北省", "浙江省", "山西省", "河南省",
    "山东省", "上海市", "宁夏回族自治区", "贵州省", "广东省", "江西省",
}
PROVINCE_ORDER = [
    "湖南省", "江苏省", "安徽省", "甘肃省", "陕西省", "广西壮族自治区",
    "内蒙古自治区", "天津市", "湖北省", "浙江省", "山西省", "河南省",
    "山东省", "上海市", "宁夏回族自治区", "贵州省", "广东省", "江西省",
]
PROVINCE_RANK = {name: idx for idx, name in enumerate(PROVINCE_ORDER)}

CITY_CODE_URL = (
    "https://gist.githubusercontent.com/CyanSalt/"
    "c533a5ae6217a9d1848bd652cee9cf72/raw/baidu-city-code.json"
)
MAX_WORKERS = 6
MAX_PAGES_PER_CITY_KEYWORD = 200
REQUEST_TIMEOUT = 35
RETRIES = 5
CRAWL_TZ = timezone(timedelta(hours=8))
CRAWL_TIME = datetime.now(CRAWL_TZ).replace(microsecond=0).isoformat()

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S9180) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
]

_thread_local = threading.local()
_print_lock = threading.Lock()

# Baidu Mercator -> BD-09 coefficients used by Baidu web map clients.
MCBAND = [12890594.86, 8362377.87, 5591021.0, 3481989.83, 1678043.12, 0.0]
MC2LL = [
    [1.410526172116255e-8, 0.00000898305509648872, -1.9939833816331,
     200.9824383106796, -187.2403703815547, 91.6087516669843,
     -23.38765649603339, 2.57121317296198, -0.03801003308653, 17337981.2],
    [-7.435856389565537e-9, 0.000008983055097726239, -0.78625201886289,
     96.32687599759846, -1.85204757529826, -59.36935905485877,
     47.40033549296737, -16.50741931063887, 2.28786674699375, 10260144.86],
    [-3.030883460898826e-8, 0.00000898305509983578, 0.30071316287616,
     59.74293618442277, 7.357984074871, -25.38371002664745,
     13.45380521110908, -3.29883767235584, 0.32710905363475, 6856817.37],
    [-1.981981304930552e-8, 0.000008983055099779535, 0.03278182852591,
     40.31678527705744, 0.65659298677277, -4.44255534477492,
     0.85341911805263, 0.12923347998204, -0.04625736007561, 4482777.06],
    [3.09191371068437e-9, 0.000008983055096812155, 0.00006995724062,
     23.10934304144901, -0.00023663490511, -0.6321817810242,
     -0.00663494467273, 0.03430082397953, -0.00466043876332, 2555164.4],
    [2.890871144776878e-9, 0.000008983055095805407, -0.00000003068298,
     7.47137025468032, -0.00000353937994, -0.02145144861037,
     -0.00001234426596, 0.00010322952773, -0.00000323890364, 826088.5],
]


def log(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


def session() -> requests.Session:
    value = getattr(_thread_local, "session", None)
    if value is None:
        value = requests.Session()
        value.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://map.baidu.com/mobile/webapp/index/index/",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        })
        _thread_local.session = value
    return value


def mobile_url(city_code: str, keyword: str, page: int) -> str:
    return (
        "https://map.baidu.com/mobile/webapp/place/list/"
        f"qt=s&wd={quote(keyword)}&c={city_code}&pn={page}&rn=10"
        "&res_x=0.000000&res_y=0.000000/showall=1"
    )


def extract_widget(text: str) -> dict[str, Any]:
    markers = [
        'require("place:widget/mixlist/mixlist.js").createWidget(',
        "require('place:widget/mixlist/mixlist.js').createWidget(",
    ]
    start = -1
    for marker in markers:
        start = text.find(marker)
        if start >= 0:
            start += len(marker)
            break
    if start < 0:
        match = re.search(r"createWidget\s*\(\s*", text)
        if not match:
            raise ValueError("mixlist widget JSON marker not found")
        start = match.end()
    while start < len(text) and text[start].isspace():
        start += 1
    result, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(result, dict):
        raise ValueError("widget payload is not an object")
    return result


def fetch_page(city_code: str, keyword: str, page: int) -> dict[str, Any]:
    url = mobile_url(city_code, keyword, page)
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            if attempt:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)) + random.random())
            response = session().get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"HTTP {response.status_code}")
            response.raise_for_status()
            text = response.text
            if "请输入验证码" in text or "安全验证" in text:
                raise RuntimeError("verification page returned")
            payload = extract_widget(text)
            # Keep the cadence gentle while multiple workers are active.
            time.sleep(random.uniform(0.10, 0.28))
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            # A fresh connection can recover from a poisoned/cached session.
            try:
                session().close()
            except Exception:
                pass
            _thread_local.session = None
    raise RuntimeError(
        f"failed after {RETRIES} attempts city={city_code} keyword={keyword} page={page}: {last_error!r}"
    )


def normalize_province(value: Any) -> str:
    text = str(value or "").strip()
    aliases = {
        "湖南": "湖南省", "江苏": "江苏省", "安徽": "安徽省", "甘肃": "甘肃省",
        "陕西": "陕西省", "广西": "广西壮族自治区", "内蒙古": "内蒙古自治区",
        "天津": "天津市", "湖北": "湖北省", "浙江": "浙江省", "山西": "山西省",
        "河南": "河南省", "山东": "山东省", "上海": "上海市",
        "宁夏": "宁夏回族自治区", "贵州": "贵州省", "广东": "广东省",
        "江西": "江西省",
    }
    return aliases.get(text, text)


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "; ".join(stringify(item) for item in value if stringify(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def bdmc_to_bd09(x_value: Any, y_value: Any) -> tuple[float | None, float | None]:
    try:
        x = float(x_value)
        y = float(y_value)
    except (TypeError, ValueError):
        return None, None
    if abs(x) > 100_000_000:
        x /= 100.0
    if abs(y) > 100_000_000:
        y /= 100.0
    coeff = MC2LL[-1]
    for band, candidate in zip(MCBAND, MC2LL):
        if abs(y) >= band:
            coeff = candidate
            break
    lon = coeff[0] + coeff[1] * abs(x)
    c = abs(y) / coeff[9]
    lat = (
        coeff[2] + coeff[3] * c + coeff[4] * c ** 2 + coeff[5] * c ** 3
        + coeff[6] * c ** 4 + coeff[7] * c ** 5 + coeff[8] * c ** 6
    )
    if x < 0:
        lon = -lon
    if y < 0:
        lat = -lat
    if not (70 <= lon <= 140 and 0 <= lat <= 60):
        return None, None
    return round(lon, 7), round(lat, 7)


def bd09_to_gcj02(lon: float | None, lat: float | None) -> tuple[float | None, float | None]:
    if lon is None or lat is None:
        return None, None
    x_pi = math.pi * 3000.0 / 180.0
    x = lon - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    return round(z * math.cos(theta), 7), round(z * math.sin(theta), 7)


def out_of_china(lon: float, lat: float) -> bool:
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def transform_lat(x: float, y: float) -> float:
    value = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    value += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    value += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    value += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return value


def transform_lon(x: float, y: float) -> float:
    value = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    value += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    value += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    value += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return value


def gcj02_to_wgs84(lon: float | None, lat: float | None) -> tuple[float | None, float | None]:
    if lon is None or lat is None:
        return None, None
    if out_of_china(lon, lat):
        return lon, lat
    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = transform_lat(lon - 105.0, lat - 35.0)
    dlon = transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrt_magic * math.cos(radlat) * math.pi)
    return round(lon * 2 - (lon + dlon), 7), round(lat * 2 - (lat + dlat), 7)


def classify_brand(name: str, brand_id: str, brand_name: str) -> tuple[str, str]:
    if "老百姓健康药房" in name or brand_id == "72013877" or brand_name == "老百姓健康药房":
        return "老百姓健康药房", "加盟品牌标识；不等同于逐店工商性质核验"
    return "老百姓大药房", "挂牌品牌；公开POI无法区分直营与加盟"


def is_store(item: dict[str, Any]) -> tuple[bool, str]:
    name = stringify(item.get("name"))
    detail = ((item.get("ext") or {}).get("detail_info") or {})
    brand = item.get("brand_id") or detail.get("brand_id") or {}
    if not isinstance(brand, dict):
        brand = {}
    brand_id = stringify(brand.get("id"))
    brand_name = stringify(brand.get("name"))
    tag = stringify(item.get("std_tag") or detail.get("tag"))
    has_name = "老百姓大药房" in name or "老百姓健康药房" in name
    has_brand = brand_id in BRAND_IDS or brand_name in BRAND_IDS.values()
    if not (has_name or has_brand):
        return False, "品牌名称/ID不匹配"
    hard_excludes = ("总部", "办公楼", "总部大楼", "物流中心", "配送中心", "仓库", "培训中心")
    if any(term in name for term in hard_excludes):
        return False, "非零售门店名称"
    if ("有限公司" in name or "股份公司" in name or "药业公司" in name) and not ("药店" in tag or "药房" in tag):
        return False, "公司机构而非药房"
    return True, ""


def extract_record(
    item: dict[str, Any],
    keyword: str,
    query_city_code: str,
    query_page: int,
    fallback_city: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    keep, reason = is_store(item)
    if not keep:
        return None, reason
    admin = item.get("admin_info") or {}
    detail = ((item.get("ext") or {}).get("detail_info") or {})
    brand = item.get("brand_id") or detail.get("brand_id") or {}
    if not isinstance(brand, dict):
        brand = {}
    name = stringify(item.get("name"))
    brand_id = stringify(brand.get("id"))
    brand_name_raw = stringify(brand.get("name"))
    sign_brand, nature_note = classify_brand(name, brand_id, brand_name_raw)
    province = normalize_province(admin.get("province_name") or fallback_city.get("up_province_name"))
    if province not in OFFICIAL_PROVINCES:
        return None, "不在官方18个省级市场"
    city = stringify(admin.get("city_name") or fallback_city.get("name"))
    district = stringify(admin.get("area_name"))
    address = stringify(item.get("addr") or item.get("poi_address") or detail.get("address"))
    phone = stringify(detail.get("phone") or item.get("tel") or detail.get("tel"))
    shop_hours = stringify(detail.get("shop_hours") or item.get("shop_hours"))
    business_time = stringify(detail.get("business_time") or item.get("business_time"))
    if not shop_hours and business_time:
        shop_hours = business_time
    tag = stringify(item.get("std_tag") or detail.get("tag"))
    uid = stringify(item.get("uid"))
    x_raw = item.get("x") if item.get("x") is not None else item.get("diPointX")
    y_raw = item.get("y") if item.get("y") is not None else item.get("diPointY")
    bd_lon, bd_lat = bdmc_to_bd09(x_raw, y_raw)
    gcj_lon, gcj_lat = bd09_to_gcj02(bd_lon, bd_lat)
    wgs_lon, wgs_lat = gcj02_to_wgs84(gcj_lon, gcj_lat)
    status = stringify(detail.get("status_name") or item.get("status_name") or item.get("status"))
    image = stringify(detail.get("image") or detail.get("image_url"))
    detail_url = f"https://map.baidu.com/mobile/webapp/place/detail/qt=ninf&uid={uid}" if uid else ""
    record = {
        "门店名称": name,
        "挂牌品牌": sign_brand,
        "门店性质口径": nature_note,
        "省份": province,
        "城市": city,
        "区县": district,
        "详细地址": address,
        "联系电话": phone,
        "营业时间": shop_hours,
        "经营状态_公开POI": status,
        "POI分类": tag,
        "百度经度_BD09": bd_lon,
        "百度纬度_BD09": bd_lat,
        "火星经度_GCJ02": gcj_lon,
        "火星纬度_GCJ02": gcj_lat,
        "WGS84经度_近似": wgs_lon,
        "WGS84纬度_近似": wgs_lat,
        "百度墨卡托X_原始": stringify(x_raw),
        "百度墨卡托Y_原始": stringify(y_raw),
        "百度POI_UID": uid,
        "百度品牌ID": brand_id,
        "百度品牌名": brand_name_raw,
        "门店图片": image,
        "来源详情页": detail_url,
        "查询关键词": keyword,
        "查询城市码": query_city_code,
        "查询页码": query_page,
        "数据源": "百度地图公开可检索POI",
        "抓取时间": CRAWL_TIME,
        "备注": "",
    }
    return record, ""


def safe_total(payload: dict[str, Any]) -> int:
    value = (payload.get("result") or {}).get("total")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        content = payload.get("content") or []
        return len(content) if isinstance(content, list) else 0


def crawl_city_keyword(city_code: str, city_hint: str, keyword: str) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    started = time.time()
    stats: dict[str, Any] = {
        "查询城市码": city_code,
        "城市提示": city_hint,
        "查询关键词": keyword,
        "状态": "",
        "实际城市码": "",
        "省份": "",
        "城市": "",
        "检索总数": 0,
        "计划页数": 0,
        "实际页数": 0,
        "原始POI数": 0,
        "纳入数_去重前": 0,
        "排除数": 0,
        "耗时秒": 0,
        "错误": "",
    }
    exclusions: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    try:
        first = fetch_page(city_code, keyword, 0)
        current_city = first.get("current_city") or {}
        actual_code = stringify(current_city.get("code"))
        province = normalize_province(current_city.get("up_province_name"))
        city_name = stringify(current_city.get("name"))
        stats.update({"实际城市码": actual_code, "省份": province, "城市": city_name})
        if actual_code and actual_code != city_code:
            stats["状态"] = "跳过：城市码重定向"
            return records, stats, exclusions
        if province not in OFFICIAL_PROVINCES:
            stats["状态"] = "跳过：非官方市场"
            return records, stats, exclusions
        total = safe_total(first)
        planned_pages = min(MAX_PAGES_PER_CITY_KEYWORD, max(1, math.ceil(total / 10))) if total else 1
        stats["检索总数"] = total
        stats["计划页数"] = planned_pages
        for page in range(planned_pages):
            payload = first if page == 0 else fetch_page(city_code, keyword, page)
            content = payload.get("content") or []
            if not isinstance(content, list):
                content = []
            stats["实际页数"] += 1
            stats["原始POI数"] += len(content)
            for item in content:
                if not isinstance(item, dict):
                    continue
                record, reason = extract_record(item, keyword, city_code, page, current_city)
                if record is not None:
                    records.append(record)
                else:
                    stats["排除数"] += 1
                    if len(exclusions) < 30:
                        exclusions.append({
                            "查询城市码": city_code,
                            "城市": city_name,
                            "查询关键词": keyword,
                            "查询页码": page,
                            "POI名称": stringify(item.get("name")),
                            "POI_UID": stringify(item.get("uid")),
                            "排除原因": reason,
                            "POI分类": stringify(item.get("std_tag")),
                        })
            page_info = payload.get("pageInfo") or {}
            if page_info.get("isLast") is True:
                break
            if not content:
                break
        stats["纳入数_去重前"] = len(records)
        stats["状态"] = "成功"
    except Exception as exc:  # noqa: BLE001
        stats["状态"] = "失败"
        stats["错误"] = repr(exc)
    finally:
        stats["耗时秒"] = round(time.time() - started, 2)
    return records, stats, exclusions


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", stringify(value)).lower()
    return re.sub(r"[\s\-—_()（）【】\[\]·,，.。/\\]+", "", text)


def richness(record: dict[str, Any]) -> int:
    important = [
        "详细地址", "联系电话", "营业时间", "百度经度_BD09", "百度纬度_BD09",
        "百度品牌ID", "POI分类", "来源详情页", "门店图片",
    ]
    return sum(1 for key in important if record.get(key) not in (None, ""))


def merge_records(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if richness(candidate) > richness(base):
        base, candidate = candidate, base
    for key, value in candidate.items():
        if base.get(key) in (None, "") and value not in (None, ""):
            base[key] = value
    keywords = sorted({part for source in (base.get("查询关键词"), candidate.get("查询关键词")) for part in stringify(source).split(";") if part})
    base["查询关键词"] = ";".join(keywords)
    return base


def deduplicate(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_uid: dict[str, dict[str, Any]] = {}
    no_uid: list[dict[str, Any]] = []
    uid_merges = 0
    for record in records:
        uid = stringify(record.get("百度POI_UID"))
        if not uid:
            no_uid.append(record)
            continue
        if uid in by_uid:
            by_uid[uid] = merge_records(by_uid[uid], record)
            uid_merges += 1
        else:
            by_uid[uid] = record
    stage = list(by_uid.values()) + no_uid
    by_signature: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    signature_merges = 0
    for record in stage:
        signature = (
            normalize_key(record.get("省份")),
            normalize_key(record.get("城市")),
            normalize_key(record.get("门店名称")),
            normalize_key(record.get("详细地址")),
        )
        # Avoid collapsing records whose address is absent.
        if not signature[3]:
            signature = signature[:-1] + (normalize_key(record.get("百度POI_UID")) or str(id(record)),)
        if signature in by_signature:
            by_signature[signature] = merge_records(by_signature[signature], record)
            signature_merges += 1
        else:
            by_signature[signature] = record
    result = list(by_signature.values())
    result.sort(key=lambda row: (
        PROVINCE_RANK.get(stringify(row.get("省份")), 999),
        stringify(row.get("城市")), stringify(row.get("区县")), stringify(row.get("门店名称")),
    ))
    for index, row in enumerate(result, 1):
        row["序号"] = index
    return result, {"UID合并数": uid_merges, "名称地址合并数": signature_merges}


def load_city_codes() -> dict[str, str]:
    response = requests.get(CITY_CODE_URL, timeout=45, headers={"User-Agent": USER_AGENTS[0]})
    response.raise_for_status()
    payload = response.json()
    result: dict[str, str] = {}
    for code, meta in payload.items():
        try:
            numeric = int(code)
        except (TypeError, ValueError):
            continue
        if numeric <= 32:
            continue
        name = stringify(meta.get("zh")) if isinstance(meta, dict) else ""
        result[str(numeric)] = name
    return result


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    city_codes = load_city_codes()
    (OUT / "baidu_city_codes_used.json").write_text(
        json.dumps(city_codes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tasks = [(code, hint, keyword) for code, hint in city_codes.items() for keyword in KEYWORDS]
    log(f"Starting {len(tasks)} city-keyword tasks with {MAX_WORKERS} workers")

    all_records: list[dict[str, Any]] = []
    all_stats: list[dict[str, Any]] = []
    all_exclusions: list[dict[str, Any]] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(crawl_city_keyword, code, hint, keyword): (code, hint, keyword)
            for code, hint, keyword in tasks
        }
        for future in as_completed(future_map):
            code, hint, keyword = future_map[future]
            completed += 1
            try:
                records, stats, exclusions = future.result()
            except Exception as exc:  # noqa: BLE001
                records, exclusions = [], []
                stats = {
                    "查询城市码": code, "城市提示": hint, "查询关键词": keyword,
                    "状态": "任务异常", "错误": repr(exc), "耗时秒": 0,
                }
            all_records.extend(records)
            all_stats.append(stats)
            all_exclusions.extend(exclusions)
            if completed % 20 == 0 or records or stats.get("状态") == "失败":
                log(
                    f"[{completed}/{len(tasks)}] {code} {hint} {keyword}: "
                    f"{stats.get('状态')} total={stats.get('检索总数', 0)} included={len(records)}"
                )

    unique_records, dedup_stats = deduplicate(all_records)
    province_counts = Counter(row["省份"] for row in unique_records)
    city_counts = Counter((row["省份"], row["城市"]) for row in unique_records)
    brand_counts = Counter(row["挂牌品牌"] for row in unique_records)
    with_phone = sum(1 for row in unique_records if row.get("联系电话"))
    with_hours = sum(1 for row in unique_records if row.get("营业时间"))
    with_coords = sum(1 for row in unique_records if row.get("百度经度_BD09") is not None)
    failed_tasks = [row for row in all_stats if row.get("状态") in {"失败", "任务异常"}]
    successful_market_tasks = [row for row in all_stats if row.get("状态") == "成功"]

    store_fields = [
        "序号", "门店名称", "挂牌品牌", "门店性质口径", "省份", "城市", "区县",
        "详细地址", "联系电话", "营业时间", "经营状态_公开POI", "POI分类",
        "百度经度_BD09", "百度纬度_BD09", "火星经度_GCJ02", "火星纬度_GCJ02",
        "WGS84经度_近似", "WGS84纬度_近似", "百度墨卡托X_原始", "百度墨卡托Y_原始",
        "百度POI_UID", "百度品牌ID", "百度品牌名", "门店图片", "来源详情页",
        "查询关键词", "查询城市码", "查询页码", "数据源", "抓取时间", "备注",
    ]
    stats_fields = [
        "查询城市码", "城市提示", "查询关键词", "状态", "实际城市码", "省份", "城市",
        "检索总数", "计划页数", "实际页数", "原始POI数", "纳入数_去重前", "排除数",
        "耗时秒", "错误",
    ]
    exclusion_fields = ["查询城市码", "城市", "查询关键词", "查询页码", "POI名称", "POI_UID", "排除原因", "POI分类"]
    write_csv(OUT / "老百姓大药房全国公开POI清单.csv", unique_records, store_fields)
    write_csv(OUT / "城市抓取覆盖.csv", sorted(all_stats, key=lambda row: (str(row.get("省份", "")), str(row.get("城市", "")), str(row.get("查询关键词", "")))), stats_fields)
    write_csv(OUT / "抽样排除项.csv", all_exclusions, exclusion_fields)
    (OUT / "老百姓大药房全国公开POI清单.json").write_text(
        json.dumps(unique_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    province_rows = [
        {"省份": province, "门店数": province_counts.get(province, 0)}
        for province in PROVINCE_ORDER
    ]
    city_rows = [
        {"省份": province, "城市": city, "门店数": count}
        for (province, city), count in sorted(city_counts.items(), key=lambda item: (PROVINCE_RANK.get(item[0][0], 999), item[0][1]))
    ]
    write_csv(OUT / "省份统计.csv", province_rows, ["省份", "门店数"])
    write_csv(OUT / "城市统计.csv", city_rows, ["省份", "城市", "门店数"])

    summary = {
        "抓取时间": CRAWL_TIME,
        "公开数据源": "百度地图移动端公开可检索POI页面",
        "查询关键词": list(KEYWORDS),
        "官方市场省份": PROVINCE_ORDER,
        "百度城市码数量": len(city_codes),
        "城市关键词任务数": len(tasks),
        "官方市场成功任务数": len(successful_market_tasks),
        "失败任务数": len(failed_tasks),
        "失败任务": failed_tasks,
        "检索原始POI总行数": sum(int(row.get("原始POI数") or 0) for row in all_stats),
        "纳入去重前行数": len(all_records),
        "去重后门店数": len(unique_records),
        "去重统计": dedup_stats,
        "挂牌品牌统计": dict(brand_counts),
        "省份统计": dict(province_counts),
        "城市数量": len(city_counts),
        "有电话门店数": with_phone,
        "有营业时间门店数": with_hours,
        "有坐标门店数": with_coords,
        "电话覆盖率": round(with_phone / len(unique_records), 4) if unique_records else 0,
        "营业时间覆盖率": round(with_hours / len(unique_records), 4) if unique_records else 0,
        "坐标覆盖率": round(with_coords / len(unique_records), 4) if unique_records else 0,
        "口径说明": [
            "本结果为公开地图可检索POI，不是老百姓大药房内部主数据或工商/药监许可全量名录。",
            "仅纳入以“老百姓大药房”或“老百姓健康药房”挂牌/标注的门店；集团其他收购品牌和药简单联盟门店不在本次关键词口径内。",
            "结果限定在公司公开披露的18个省级市场，并排除总部、办公楼、物流中心等明显非零售POI。",
            "百度地图POI可能存在新增滞后、闭店未及时删除、地址/区县不一致或电话缺失。",
            "BD-09坐标由页面中的百度墨卡托坐标换算；GCJ-02与WGS84列为算法换算近似值。",
        ],
    }
    (OUT / "crawl_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
