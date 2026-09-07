#!/usr/bin/env python3
"""Crawl nationwide public Baidu Map POIs for LBX Pharmacy brands.

Scope: public-map POIs returned for exact brand keywords, not an internal LBX
master-data export.  The script queries every prefecture-level Baidu city code,
paginates the mobile search pages, de-duplicates by Baidu UID, and separates
pharmacy-store rows from ambiguous/non-store POIs.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import requests

OUT = Path("lbx_baidu_nationwide_output")
OUT.mkdir(exist_ok=True)

CITY_CODE_URL = (
    "https://gist.githubusercontent.com/CyanSalt/"
    "c533a5ae6217a9d1848bd652cee9cf72/raw/"
    "fae512225dc4e563dae79f15a54570c65045c403/baidu-city-code.json"
)
KEYWORDS = ["老百姓大药房", "老百姓健康药房"]
EXPECTED_BRANDS = {"老百姓大药房", "老百姓健康药房"}
EXPECTED_BRAND_IDS = {"2445", "72013877"}
PAGE_SIZE = 10
MAX_WORKERS = int(os.getenv("LBX_MAX_WORKERS", "6"))
MAX_PAGES_PER_QUERY = int(os.getenv("LBX_MAX_PAGES", "80"))
REQUEST_TIMEOUT = int(os.getenv("LBX_REQUEST_TIMEOUT", "45"))
MAX_RETRIES = int(os.getenv("LBX_MAX_RETRIES", "4"))

UA_POOL = [
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-G9910) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; V2309A) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
]

NON_STORE_RE = re.compile(
    r"(总部|集团\s*\(?总部|办公|写字楼|配送中心|物流中心|仓库|仓储|供应链|"
    r"培训中心|会议中心|制药|药业公司|医药公司|有限公司|股份公司|客服中心|"
    r"产业园|研发中心|数据中心|区域中心|分公司(?!.*店))"
)
PHARMACY_RE = re.compile(r"(大药房|健康药房|药房|药店)")

_thread_local = threading.local()
_print_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def compact(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit]


def session() -> requests.Session:
    current = getattr(_thread_local, "session", None)
    if current is None:
        current = requests.Session()
        current.headers.update(
            {
                "User-Agent": random.choice(UA_POOL),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                "Referer": "https://map.baidu.com/mobile/webapp/index/index/",
                "Connection": "keep-alive",
            }
        )
        _thread_local.session = current
    return current


def mobile_list_url(city_code: str, keyword: str, page: int) -> str:
    return (
        "https://map.baidu.com/mobile/webapp/place/list/"
        f"qt=s&wd={quote(keyword)}&c={city_code}&pn={page}&rn={PAGE_SIZE}"
        "&res_x=0.000000&res_y=0.000000/showall=1"
    )


def extract_widget(text: str) -> dict[str, Any]:
    markers = [
        'require("place:widget/mixlist/mixlist.js").createWidget(',
        "require('place:widget/mixlist/mixlist.js').createWidget(",
    ]
    for marker in markers:
        start = text.find(marker)
        if start >= 0:
            start += len(marker)
            while start < len(text) and text[start].isspace():
                start += 1
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
    # Tolerate small minification/quote variations.
    match = re.search(r"mixlist/mixlist\.js[^\n]{0,100}?createWidget\s*\(\s*", text)
    if match:
        obj, _ = json.JSONDecoder().raw_decode(text[match.end() :])
        if isinstance(obj, dict):
            return obj
    raise ValueError("Baidu mixlist widget payload not found")


def fetch_page(city_code: str, keyword: str, page: int) -> tuple[dict[str, Any], str, int]:
    url = mobile_list_url(city_code, keyword, page)
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session().get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            response.raise_for_status()
            obj = extract_widget(response.text)
            content = obj.get("content")
            if not isinstance(content, list):
                raise ValueError(f"Unexpected content type: {type(content).__name__}")
            return obj, response.url, len(response.content)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= MAX_RETRIES:
                break
            # Replace session after anti-bot or malformed-page failures.
            if hasattr(_thread_local, "session"):
                try:
                    _thread_local.session.close()
                except Exception:
                    pass
                delattr(_thread_local, "session")
            time.sleep((1.2 ** attempt) + random.uniform(0.35, 1.2))
    raise RuntimeError(f"Failed {url}: {last_error!r}")


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = compact(value)
        if text:
            return text
    return ""


def extract_business_hours(item: dict[str, Any], detail: dict[str, Any]) -> str:
    candidates: list[Any] = [
        item.get("shop_hours"),
        detail.get("shop_hours"),
        detail.get("business_hours"),
        detail.get("business_time"),
    ]
    business = item.get("business_time")
    if isinstance(business, dict):
        for entry in business.get("data") or []:
            if isinstance(entry, dict):
                text = entry.get("business_time_text")
                if isinstance(text, dict):
                    candidates.extend([text.get("common"), text.get("festival")])
                candidates.extend([entry.get("common"), entry.get("festival")])
    for value in candidates:
        text = compact(value, 600)
        if text and text not in {"[]", "{}"}:
            return text
    return ""


def extract_image(item: dict[str, Any], detail: dict[str, Any]) -> str:
    for value in [detail.get("image"), detail.get("default_image"), item.get("image")]:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return ""


def extract_row(
    item: dict[str, Any],
    *,
    keyword: str,
    query_city_code: str,
    query_city_name: str,
    page: int,
    page_url: str,
    query_total: int,
    crawl_time: str,
) -> dict[str, Any]:
    admin = item.get("admin_info") or {}
    api_admin = item.get("api_admin_info") or {}
    ext = item.get("ext") or {}
    detail = ext.get("detail_info") or {}
    brand = item.get("brand_id") or detail.get("brand_id") or {}
    if not isinstance(brand, dict):
        brand = {"name": brand}

    name = first_nonempty(item.get("name"), detail.get("name"))
    address = first_nonempty(item.get("addr"), item.get("poi_address"), detail.get("address"))
    brand_name = first_nonempty(brand.get("name"), detail.get("brand_name"))
    brand_id = first_nonempty(brand.get("id"), detail.get("brand_id"))
    phone = first_nonempty(
        item.get("phone"), detail.get("phone"), item.get("tel"), detail.get("telephone")
    )
    province = first_nonempty(admin.get("province_name"), api_admin.get("prov_name"))
    city = first_nonempty(admin.get("city_name"), api_admin.get("city_name"), item.get("city_name"))
    district = first_nonempty(admin.get("area_name"), api_admin.get("area_name"), item.get("area_name"))
    std_tag = first_nonempty(item.get("std_tag"), item.get("di_tag"), detail.get("tag"))
    uid = first_nonempty(item.get("uid"), detail.get("uid"))

    exact_brand = brand_name in EXPECTED_BRANDS or brand_id in EXPECTED_BRAND_IDS
    name_match = any(token in name for token in EXPECTED_BRANDS)
    pharmacy_like = bool(PHARMACY_RE.search(name) or "药店" in std_tag or "药房" in std_tag)
    non_store = bool(NON_STORE_RE.search(name))
    if exact_brand and pharmacy_like and not non_store:
        status = "品牌匹配-门店"
        confidence = "高"
    elif name_match and pharmacy_like and not non_store:
        status = "名称匹配-门店"
        confidence = "中"
    elif non_store:
        status = "非门店POI"
        confidence = "待核验"
    else:
        status = "疑似相关POI"
        confidence = "待核验"

    x = item.get("x")
    y = item.get("y")
    if x in (None, ""):
        x = item.get("diPointX")
    if y in (None, ""):
        y = item.get("diPointY")

    return {
        "uid": uid,
        "name": name,
        "brand_name": brand_name,
        "brand_id": brand_id,
        "province": province,
        "city": city,
        "district": district,
        "address": address,
        "phone": phone,
        "business_hours": extract_business_hours(item, detail),
        "std_tag": std_tag,
        "baidu_x": compact(x),
        "baidu_y": compact(y),
        "image_url": extract_image(item, detail),
        "query_keyword": keyword,
        "query_city_code": query_city_code,
        "query_city_name": query_city_name,
        "query_page": page,
        "query_total": query_total,
        "source_url": page_url,
        "crawl_time": crawl_time,
        "match_status": status,
        "confidence": confidence,
        "is_store": status.endswith("门店") and status != "非门店POI",
        "raw_brand": compact(brand, 800),
    }


@dataclass
class QueryResult:
    city_code: str
    city_label: str
    keyword: str
    response_city: str
    response_province: str
    total_reported: int
    pages_expected: int
    pages_fetched: int
    rows: list[dict[str, Any]]
    bytes_downloaded: int
    elapsed_seconds: float
    error: str = ""


def crawl_query(city_code: str, city_label: str, keyword: str) -> QueryResult:
    started = time.time()
    crawl_time = now_iso()
    rows: list[dict[str, Any]] = []
    bytes_downloaded = 0
    response_city = ""
    response_province = ""
    total = 0
    pages_expected = 1
    pages_fetched = 0
    error = ""
    try:
        first, final_url, size = fetch_page(city_code, keyword, 0)
        bytes_downloaded += size
        result = first.get("result") or {}
        page_info = first.get("pageInfo") or {}
        current_city = first.get("current_city") or {}
        response_city = compact(current_city.get("name"))
        response_province = compact(current_city.get("up_province_name"))
        total = int(result.get("total") or len(first.get("content") or []))
        pages_expected = max(1, math.ceil(total / PAGE_SIZE))
        pages_expected = min(pages_expected, MAX_PAGES_PER_QUERY)

        for item in first.get("content") or []:
            if isinstance(item, dict):
                rows.append(
                    extract_row(
                        item,
                        keyword=keyword,
                        query_city_code=city_code,
                        query_city_name=city_label,
                        page=0,
                        page_url=final_url,
                        query_total=total,
                        crawl_time=crawl_time,
                    )
                )
        pages_fetched = 1

        is_last = bool(page_info.get("isLast"))
        for page in range(1, pages_expected):
            if is_last:
                break
            time.sleep(random.uniform(0.08, 0.32))
            obj, final_url, size = fetch_page(city_code, keyword, page)
            bytes_downloaded += size
            content = obj.get("content") or []
            for item in content:
                if isinstance(item, dict):
                    rows.append(
                        extract_row(
                            item,
                            keyword=keyword,
                            query_city_code=city_code,
                            query_city_name=city_label,
                            page=page,
                            page_url=final_url,
                            query_total=total,
                            crawl_time=crawl_time,
                        )
                    )
            pages_fetched += 1
            info = obj.get("pageInfo") or {}
            is_last = bool(info.get("isLast")) or len(content) < PAGE_SIZE
            if not content:
                break
    except Exception as exc:  # noqa: BLE001
        error = repr(exc)

    result_obj = QueryResult(
        city_code=city_code,
        city_label=city_label,
        keyword=keyword,
        response_city=response_city,
        response_province=response_province,
        total_reported=total,
        pages_expected=pages_expected,
        pages_fetched=pages_fetched,
        rows=rows,
        bytes_downloaded=bytes_downloaded,
        elapsed_seconds=round(time.time() - started, 3),
        error=error,
    )
    with _print_lock:
        print(
            json.dumps(
                {
                    "city_code": city_code,
                    "city": city_label,
                    "keyword": keyword,
                    "total": total,
                    "pages": pages_fetched,
                    "rows": len(rows),
                    "seconds": result_obj.elapsed_seconds,
                    "error": error,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return result_obj


def load_city_codes() -> dict[str, dict[str, str]]:
    response = requests.get(CITY_CODE_URL, timeout=60)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("City-code payload is not an object")
    (OUT / "baidu_city_codes.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: compact(row.get(key, ""), 10000) for key in fields})


def normalized_key(row: dict[str, Any]) -> str:
    uid = compact(row.get("uid"))
    if uid:
        return "uid:" + uid
    name = re.sub(r"[\s()（）·,，.。-]", "", compact(row.get("name"))).lower()
    address = re.sub(r"[\s,，.。-]", "", compact(row.get("address"))).lower()
    return "fallback:" + name + "|" + address


def merge_rows(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in new.items():
        if not merged.get(key) and value not in (None, ""):
            merged[key] = value
    keywords = sorted(
        set(filter(None, compact(existing.get("query_keyword")).split(" | ")))
        | set(filter(None, compact(new.get("query_keyword")).split(" | ")))
    )
    city_codes = sorted(
        set(filter(None, compact(existing.get("query_city_code")).split(" | ")))
        | set(filter(None, compact(new.get("query_city_code")).split(" | ")))
    )
    source_urls = list(
        dict.fromkeys(
            filter(
                None,
                compact(existing.get("source_url"), 10000).split(" | ")
                + compact(new.get("source_url"), 10000).split(" | "),
            )
        )
    )
    merged["query_keyword"] = " | ".join(keywords)
    merged["query_city_code"] = " | ".join(city_codes)
    merged["source_url"] = " | ".join(source_urls[:5])

    # Prefer the strongest classification encountered.
    rank = {"品牌匹配-门店": 4, "名称匹配-门店": 3, "疑似相关POI": 2, "非门店POI": 1}
    if rank.get(compact(new.get("match_status")), 0) > rank.get(compact(existing.get("match_status")), 0):
        merged["match_status"] = new.get("match_status")
        merged["confidence"] = new.get("confidence")
        merged["is_store"] = new.get("is_store")
    return merged


def main() -> None:
    run_started = now_iso()
    city_map = load_city_codes()
    # Codes 1-32 are national/provincial scopes.  Query prefecture/county-level
    # city scopes only to minimize duplicates and cap issues.
    cities = [
        (str(code), compact(info.get("zh")))
        for code, info in city_map.items()
        if str(code).isdigit() and int(code) >= 33 and isinstance(info, dict) and info.get("zh")
    ]
    cities.sort(key=lambda pair: int(pair[0]))

    tasks = [(code, label, keyword) for code, label in cities for keyword in KEYWORDS]
    results: list[QueryResult] = []
    print(
        json.dumps(
            {
                "run_started": run_started,
                "city_count": len(cities),
                "query_count": len(tasks),
                "keywords": KEYWORDS,
                "workers": MAX_WORKERS,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(crawl_query, code, label, keyword): (code, label, keyword)
            for code, label, keyword in tasks
        }
        for future in as_completed(futures):
            code, label, keyword = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                results.append(
                    QueryResult(
                        city_code=code,
                        city_label=label,
                        keyword=keyword,
                        response_city="",
                        response_province="",
                        total_reported=0,
                        pages_expected=0,
                        pages_fetched=0,
                        rows=[],
                        bytes_downloaded=0,
                        elapsed_seconds=0,
                        error=repr(exc),
                    )
                )

    all_rows = [row for result in results for row in result.rows]
    dedup: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for row in all_rows:
        key = normalized_key(row)
        if key in dedup:
            duplicate_count += 1
            dedup[key] = merge_rows(dedup[key], row)
        else:
            dedup[key] = row
    dedup_rows = list(dedup.values())
    dedup_rows.sort(
        key=lambda r: (
            compact(r.get("province")),
            compact(r.get("city")),
            compact(r.get("district")),
            compact(r.get("name")),
            compact(r.get("address")),
        )
    )

    store_rows = [row for row in dedup_rows if bool(row.get("is_store"))]
    review_rows = [row for row in dedup_rows if not bool(row.get("is_store"))]

    fields = [
        "uid",
        "name",
        "brand_name",
        "brand_id",
        "province",
        "city",
        "district",
        "address",
        "phone",
        "business_hours",
        "std_tag",
        "baidu_x",
        "baidu_y",
        "image_url",
        "query_keyword",
        "query_city_code",
        "query_city_name",
        "query_page",
        "query_total",
        "source_url",
        "crawl_time",
        "match_status",
        "confidence",
        "is_store",
        "raw_brand",
    ]
    write_csv(OUT / "all_poi_deduplicated.csv", dedup_rows, fields)
    write_csv(OUT / "pharmacy_stores.csv", store_rows, fields)
    write_csv(OUT / "review_poi.csv", review_rows, fields)

    query_fields = [
        "city_code",
        "city_label",
        "keyword",
        "response_city",
        "response_province",
        "total_reported",
        "pages_expected",
        "pages_fetched",
        "row_count",
        "bytes_downloaded",
        "elapsed_seconds",
        "error",
    ]
    query_rows = [
        {
            "city_code": result.city_code,
            "city_label": result.city_label,
            "keyword": result.keyword,
            "response_city": result.response_city,
            "response_province": result.response_province,
            "total_reported": result.total_reported,
            "pages_expected": result.pages_expected,
            "pages_fetched": result.pages_fetched,
            "row_count": len(result.rows),
            "bytes_downloaded": result.bytes_downloaded,
            "elapsed_seconds": result.elapsed_seconds,
            "error": result.error,
        }
        for result in sorted(results, key=lambda r: (int(r.city_code), r.keyword))
    ]
    write_csv(OUT / "city_query_summary.csv", query_rows, query_fields)

    province_counts: dict[str, int] = {}
    city_counts: dict[str, int] = {}
    brand_counts: dict[str, int] = {}
    for row in store_rows:
        province = compact(row.get("province")) or "未知"
        city = compact(row.get("city")) or "未知"
        brand = compact(row.get("brand_name")) or (
            "老百姓健康药房" if "老百姓健康药房" in compact(row.get("name")) else "老百姓大药房"
        )
        province_counts[province] = province_counts.get(province, 0) + 1
        city_counts[f"{province}/{city}"] = city_counts.get(f"{province}/{city}", 0) + 1
        brand_counts[brand] = brand_counts.get(brand, 0) + 1

    summary = {
        "scope": "百度地图公开可检索POI；关键词为老百姓大药房、老百姓健康药房；非集团内部官方全量台账",
        "run_started": run_started,
        "run_finished": now_iso(),
        "keywords": KEYWORDS,
        "city_code_source": CITY_CODE_URL,
        "city_count": len(cities),
        "query_count": len(tasks),
        "successful_queries": sum(1 for result in results if not result.error),
        "failed_queries": sum(1 for result in results if result.error),
        "total_reported_sum_before_dedup": sum(result.total_reported for result in results),
        "rows_collected_before_dedup": len(all_rows),
        "duplicate_rows_merged": duplicate_count,
        "deduplicated_poi_count": len(dedup_rows),
        "classified_store_count": len(store_rows),
        "review_poi_count": len(review_rows),
        "brand_counts": dict(sorted(brand_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
        "province_counts": dict(sorted(province_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
        "city_counts": dict(sorted(city_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
        "failed_query_details": [row for row in query_rows if row.get("error")],
        "classification": {
            "store": "品牌ID/品牌名或门店名称匹配，且名称/类型呈现药房门店特征，并排除总部、配送中心等",
            "review": "总部、公司、物流/配送中心及其他模糊匹配POI",
        },
        "limitations": [
            "公开地图POI可能存在新开未收录、闭店未删除、名称或电话更新滞后",
            "官网约1.5万家门店的集团口径还包含联盟及其他子品牌，本次仅抓取两个明确品牌关键词",
            "百度坐标字段为地图原始坐标值，未转换为WGS84经纬度",
        ],
    }
    (OUT / "crawl_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
