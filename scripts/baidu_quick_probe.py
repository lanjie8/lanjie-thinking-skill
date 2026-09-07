#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path("baidu_quick_output")
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://map.baidu.com/mobile/webapp/index/index/",
})


def mobile_search(city: str, keyword: str) -> str:
    return f"https://map.baidu.com/mobile/webapp/search/search/qt=s&wd={quote(keyword)}&c={city}"


def mobile_list(city: str, keyword: str, page: int) -> str:
    return (
        "https://map.baidu.com/mobile/webapp/place/list/"
        f"qt=s&wd={quote(keyword)}&c={city}&pn={page}&rn=10"
        "&res_x=0.000000&res_y=0.000000/showall=1"
    )


def extract_widget(text: str) -> dict:
    markers = [
        'require("place:widget/mixlist/mixlist.js").createWidget(',
        "require('place:widget/mixlist/mixlist.js').createWidget(",
    ]
    start = -1
    marker = ""
    for candidate in markers:
        start = text.find(candidate)
        if start >= 0:
            marker = candidate
            break
    if start < 0:
        # Fall back to locating the first object after createWidget.
        m = re.search(r"createWidget\s*\(\s*", text)
        if not m:
            raise ValueError("mixlist widget JSON marker not found")
        start = m.end()
    else:
        start += len(marker)
    while start < len(text) and text[start].isspace():
        start += 1
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("widget payload is not an object")
    return obj


def fetch(name: str, url: str) -> dict:
    started = time.time()
    try:
        r = S.get(url, timeout=45, allow_redirects=True)
        text = r.text
        (OUT / f"{name}.html").write_text(text, encoding="utf-8")
        summary = {
            "name": name,
            "url": url,
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("content-type"),
            "length": len(r.content),
            "elapsed": round(time.time() - started, 3),
        }
        try:
            data = extract_widget(text)
            (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            result = data.get("result") or {}
            content = data.get("content") or []
            page_info = data.get("pageInfo") or {}
            summary.update({
                "parsed": True,
                "total": result.get("total"),
                "content_count": len(content) if isinstance(content, list) else None,
                "page_num": page_info.get("pageNum"),
                "is_first": page_info.get("isFirst"),
                "is_last": page_info.get("isLast"),
                "next_url": page_info.get("nextPageUrl"),
                "current_city": data.get("current_city"),
                "sample": [
                    {
                        "name": item.get("name"),
                        "uid": item.get("uid"),
                        "addr": item.get("addr"),
                        "province": (item.get("admin_info") or {}).get("province_name"),
                        "city": (item.get("admin_info") or {}).get("city_name"),
                        "area": (item.get("admin_info") or {}).get("area_name"),
                        "phone": ((item.get("ext") or {}).get("detail_info") or {}).get("phone") or item.get("tel"),
                        "brand": item.get("brand_id"),
                    }
                    for item in content[:3]
                ] if isinstance(content, list) else [],
            })
        except Exception as exc:  # noqa: BLE001
            summary.update({"parsed": False, "parse_error": repr(exc), "preview": text[:1500]})
        return summary
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "url": url, "error": repr(exc), "elapsed": round(time.time() - started, 3)}


def main() -> None:
    tests = [
        ("changsha_search_p0", mobile_search("158", "老百姓大药房")),
        ("changsha_list_p0", mobile_list("158", "老百姓大药房", 0)),
        ("changsha_list_p1", mobile_list("158", "老百姓大药房", 1)),
        ("changsha_list_p9", mobile_list("158", "老百姓大药房", 9)),
        ("beijing_search_p0", mobile_search("131", "老百姓大药房")),
        ("xian_search_p0", mobile_search("233", "老百姓大药房")),
        ("changsha_health_p0", mobile_search("158", "老百姓健康药房")),
    ]
    report = []
    for name, url in tests:
        item = fetch(name, url)
        report.append(item)
        print(json.dumps(item, ensure_ascii=False, indent=2)[:5000], flush=True)
        time.sleep(0.8)

    gist_url = "https://gist.githubusercontent.com/CyanSalt/c533a5ae6217a9d1848bd652cee9cf72/raw/baidu-city-code.json"
    try:
        r = S.get(gist_url, timeout=45)
        city_map = r.json()
        (OUT / "baidu_city_codes.json").write_text(json.dumps(city_map, ensure_ascii=False, indent=2), encoding="utf-8")
        report.append({
            "name": "city_codes",
            "status": r.status_code,
            "count": len(city_map),
            "changsha": city_map.get("158"),
            "sample_keys": list(city_map)[:10],
        })
    except Exception as exc:  # noqa: BLE001
        report.append({"name": "city_codes", "error": repr(exc)})

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
