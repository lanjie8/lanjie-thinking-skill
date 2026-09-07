#!/usr/bin/env python3
"""Collect public static assets used by an LBX store-selection page."""
from __future__ import annotations
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests

OUT = Path("h5_asset_output")
OUT.mkdir(exist_ok=True)
PAGE = "https://yx.lbxcn.com/h5/springgame/index.html?gameCode=spring_251230_6&source=4"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
r = session.get(PAGE, timeout=40)
r.raise_for_status()
(OUT / "page.html").write_text(r.text, encoding="utf-8")
assets = set()
for value in re.findall(r"(?is)(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", r.text):
    url = urljoin(r.url, html.unescape(value.strip()))
    if urlparse(url).scheme in {"http", "https"} and urlparse(url).path.lower().endswith((".js", ".mjs", ".json")):
        assets.add(url)
manifest = []
for i, url in enumerate(sorted(assets)):
    try:
        a = session.get(url, headers={"Referer": r.url}, timeout=40)
        suffix = Path(urlparse(url).path).suffix or ".txt"
        name = f"asset_{i:03d}{suffix}"
        (OUT / name).write_bytes(a.content)
        manifest.append({"file": name, "url": url, "status": a.status_code, "length": len(a.content), "content_type": a.headers.get("content-type")})
    except Exception as exc:
        manifest.append({"url": url, "error": repr(exc)})
    time.sleep(0.2)
(OUT / "manifest.json").write_text(json.dumps({"page": PAGE, "status": r.status_code, "final_url": r.url, "assets": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"page_status": r.status_code, "asset_count": len(manifest)}, ensure_ascii=False))
