#!/usr/bin/env python3
"""Probe Baidu mobile-map search pagination and embedded POI schema."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path("mobile_pagination_probe_output")
OUT.mkdir(exist_ok=True)
UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)


def build_url(city: str, keyword: str, extra: str = "") -> str:
    suffix = f"qt=s&wd={quote(keyword)}&c={city}"
    if extra:
        suffix += "&" + extra
    return "https://map.baidu.com/mobile/webapp/search/search/" + suffix


def extract_widget_json(text: str) -> dict:
    markers = [
        'require("place:widget/mixlist/mixlist.js").createWidget(',
        "require('place:widget/mixlist/mixlist.js').createWidget(",
        "mixlist.js\").createWidget(",
    ]
    starts = []
    for marker in markers:
        idx = text.find(marker)
        if idx >= 0:
            starts.append(idx + len(marker))
    if not starts:
        # Fallback: locate the JSON object starting with place_info/content.
        for pat in [r'createWidget\s*\(\s*(\{\"place_info\")', r'createWidget\s*\(\s*(\{\"content\")']:
            m = re.search(pat, text)
            if m:
                starts.append(m.start(1))
                break
    if not starts:
        raise ValueError("mixlist createWidget JSON marker not found")
    start = min(starts)
    while start < len(text) and text[start].isspace():
        start += 1
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    return value


def summarize_item(item: dict) -> dict:
    admin = item.get("admin_info") or {}
    ext = item.get("ext") or {}
    detail = ext.get("detail_info") or {}
    bt = item.get("business_time") or detail.get("business_time") or {}
    return {
        "uid": item.get("uid"),
        "name": item.get("name") or detail.get("name"),
        "province": admin.get("province_name"),
        "city": admin.get("city_name") or item.get("city_name"),
        "area": admin.get("area_name"),
        "addr": item.get("addr") or item.get("poi_address"),
        "phone": item.get("phone") or detail.get("phone"),
        "x": item.get("x") or item.get("diPointX"),
        "y": item.get("y") or item.get("diPointY"),
        "std_tag": item.get("std_tag") or item.get("di_tag"),
        "business_time": bt,
    }


def main() -> None:
    tests = [
        ("base", ""),
        ("pn1", "pn=1"),
        ("pn2", "pn=2"),
        ("page2", "page=2"),
        ("nn10", "nn=10"),
        ("pn1_nn10", "pn=1&nn=10"),
        ("pn10", "pn=10"),
        ("page_num1", "page_num=1"),
        ("page_index1", "page_index=1"),
    ]
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "Referer": "https://map.baidu.com/",
    })
    report = []
    for name, extra in tests:
        url = build_url("158", "老百姓大药房", extra)
        row = {"test": name, "extra": extra, "url": url}
        try:
            response = session.get(url, timeout=45)
            text = response.text
            (OUT / f"{name}.html").write_text(text, encoding="utf-8")
            row.update({
                "status": response.status_code,
                "final_url": response.url,
                "content_type": response.headers.get("content-type"),
                "length": len(text),
                "cookie_names": sorted(session.cookies.keys()),
            })
            try:
                obj = extract_widget_json(text)
                content = obj.get("content") or []
                row["widget_keys"] = sorted(obj.keys())
                row["place_info_keys"] = sorted((obj.get("place_info") or {}).keys())
                row["count"] = len(content)
                row["uids"] = [x.get("uid") for x in content]
                row["names"] = [x.get("name") for x in content]
                row["items"] = [summarize_item(x) for x in content]
                # Keep any scalar top-level pagination-like fields.
                row["pagination_fields"] = {
                    k: v for k, v in obj.items()
                    if isinstance(v, (str, int, float, bool, type(None)))
                    and re.search(r"page|total|count|num|pn|nn", k, re.I)
                }
            except Exception as exc:  # noqa: BLE001
                row["parse_error"] = repr(exc)
            hrefs = sorted(set(re.findall(r'href=[\"\']([^\"\']+)[\"\']', text, re.I)))
            row["pagination_hrefs"] = [h for h in hrefs if re.search(r"pn=|page=|nn=|next|上一页|下一页", h, re.I)][:100]
            row["term_counts"] = {
                "老百姓大药房": text.count("老百姓大药房"),
                "mixlist": text.count("mixlist"),
                "pn=": text.count("pn="),
                "page=": text.count("page="),
                "nn=": text.count("nn="),
            }
        except Exception as exc:  # noqa: BLE001
            row["error"] = repr(exc)
        report.append(row)
        print(json.dumps(row, ensure_ascii=False)[:5000], flush=True)
        time.sleep(1.5)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
