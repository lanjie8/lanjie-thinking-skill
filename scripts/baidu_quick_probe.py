#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

OUT = Path("baidu_quick_output")
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://map.baidu.com/",
    "X-Requested-With": "XMLHttpRequest",
})


def url(city: str, page: int, keyword: str, extra: dict[str, str] | None = None) -> str:
    p = {
        "newmap": "1", "reqflag": "pcmap", "biz": "1", "from": "webmap",
        "da_par": "direct", "pcevaname": "pc4.1", "qt": "s",
        "da_src": "searchBox.button", "wd": keyword, "c": city,
        "src": "0", "pn": str(page), "nn": str(page * 10),
        "sug": "0", "l": "12", "ie": "utf-8", "oue": "1",
    }
    if extra:
        p.update(extra)
    return "https://map.baidu.com/?" + urlencode(p)


def fetch(name: str, u: str) -> dict:
    t = time.time()
    try:
        r = S.get(u, timeout=45, allow_redirects=True)
        text = r.text
        (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
        parsed = None
        try:
            parsed = r.json()
        except Exception:
            pass
        summary = {
            "name": name, "url": u, "status": r.status_code,
            "content_type": r.headers.get("content-type"), "length": len(r.content),
            "elapsed": round(time.time()-t, 3), "preview": text[:1200],
        }
        if isinstance(parsed, dict):
            summary["top_keys"] = sorted(parsed.keys())
            result = parsed.get("result")
            content = parsed.get("content")
            summary["result"] = result
            summary["content_count"] = len(content) if isinstance(content, list) else None
            if isinstance(content, list):
                summary["sample"] = content[:2]
        return summary
    except Exception as e:
        return {"name": name, "url": u, "status": None, "error": repr(e), "elapsed": round(time.time()-t, 3)}


def main() -> None:
    # Establish first-party cookies.
    try:
        S.get("https://map.baidu.com/", timeout=45)
    except Exception:
        pass
    tests = [
        ("changsha_p0", url("158", 0, "老百姓大药房")),
        ("changsha_p1", url("158", 1, "老百姓大药房")),
        ("beijing_p0", url("131", 0, "老百姓大药房")),
        ("xian_p0", url("233", 0, "老百姓大药房")),
        ("changsha_health_p0", url("158", 0, "老百姓健康药房")),
        ("changsha_simple", "https://map.baidu.com/?qt=s&wd=%E8%80%81%E7%99%BE%E5%A7%93%E5%A4%A7%E8%8D%AF%E6%88%BF&c=158&pn=0&nn=0"),
    ]
    report = []
    for name, u in tests:
        item = fetch(name, u)
        report.append(item)
        print(json.dumps(item, ensure_ascii=False, indent=2)[:5000], flush=True)
        time.sleep(1.2)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
