#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import socket
import urllib.parse
from pathlib import Path

import requests

OUT = Path("mall_focus_output")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*", "Accept-Language": "zh-CN,zh;q=0.9"}
SCRIPT_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.I)
LINK_RE = re.compile(r'<link[^>]+href=["\']([^"\']+)["\']', re.I)
URL_RE = re.compile(r'https?://[^\s"\'<>\\)]+', re.I)
DOMAIN_RE = re.compile(r'(?:[a-z0-9-]+\.)+(?:lbxcn|lbxdrugs)\.com', re.I)
PATH_RE = re.compile(r'["\']((?:/|https?://)[^"\']{1,260}(?:store|shop|branch|outlet|pharmacy|location|nearby|poi|merchant|organ|org|门店|药房)[^"\']{0,260})["\']', re.I)
KEYS = ("store", "shop", "branch", "outlet", "pharmacy", "location", "nearby", "longitude", "latitude", "lng", "lat", "门店", "药房", "药店", "距离", "自提")


def get(url: str, *, referer: str | None = None, timeout: int = 20, max_bytes: int = 8_000_000):
    headers = dict(H)
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        raw = r.content[:max_bytes]
        enc = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
        text = raw.decode(enc or "utf-8", errors="replace")
        return {"ok": True, "status": r.status_code, "url": url, "final_url": r.url, "content_type": r.headers.get("content-type"), "length": len(r.content), "text": text}
    except Exception as e:
        return {"ok": False, "url": url, "error": repr(e), "text": ""}


def contexts(text: str, max_hits: int = 100):
    hits = []
    lower = text.lower()
    for key in KEYS:
        start = 0
        needle = key.lower()
        while len(hits) < max_hits:
            i = lower.find(needle, start)
            if i < 0:
                break
            hits.append({"key": key, "context": re.sub(r"\s+", " ", text[max(0, i-180): min(len(text), i+420)])})
            start = i + len(needle)
        if len(hits) >= max_hits:
            break
    return hits


def analyze_text(base_url: str, text: str):
    scripts = [urllib.parse.urljoin(base_url, x) for x in SCRIPT_RE.findall(text)]
    links = [urllib.parse.urljoin(base_url, x) for x in LINK_RE.findall(text)]
    urls = sorted(set(x.rstrip(".,;)") for x in URL_RE.findall(text)))
    domains = sorted(set(x.lower() for x in DOMAIN_RE.findall(text)))
    paths = sorted(set(x for x in PATH_RE.findall(text)))
    return {"scripts": scripts, "links": links, "urls": urls[:500], "domains": domains, "paths": paths[:500], "contexts": contexts(text, 120)}


def main():
    report = {"pages": [], "assets": [], "host_probes": []}
    starts = [
        "https://mall.lbxcn.com/",
        "https://mall.lbxcn.com/mall",
        "https://mall.lbxcn.com/mall/",
        "https://jfsc.lbxcn.com/",
        "https://www.lbxdrugs.com/",
    ]
    all_assets = []
    for idx, url in enumerate(starts):
        res = get(url, referer=url)
        analysis = analyze_text(res.get("final_url") or url, res.get("text", ""))
        report["pages"].append({k: v for k, v in res.items() if k != "text"} | analysis)
        (OUT / f"page_{idx}.txt").write_text(res.get("text", ""), encoding="utf-8")
        all_assets.extend(analysis["scripts"])
        all_assets.extend([u for u in analysis["links"] if any(x in u.lower() for x in (".js", "manifest", "config"))])

    # prioritize mall/jfsc assets, then official-site assets
    seen = set()
    ordered_assets = []
    for asset in all_assets:
        if asset not in seen:
            seen.add(asset); ordered_assets.append(asset)
    ordered_assets.sort(key=lambda u: (0 if ("mall.lbxcn.com" in u or "jfsc.lbxcn.com" in u) else 1, len(u)))

    for i, asset in enumerate(ordered_assets[:80]):
        res = get(asset, referer="https://mall.lbxcn.com/mall", timeout=25)
        text = res.get("text", "")
        analysis = analyze_text(asset, text)
        finding = {k: v for k, v in res.items() if k != "text"} | analysis
        # keep only assets with useful strings, plus first few for diagnostics
        if i < 8 or analysis["domains"] or analysis["paths"] or analysis["contexts"]:
            report["assets"].append(finding)
        if text:
            (OUT / f"asset_{i:02d}.txt").write_text(text, encoding="utf-8")

    candidates = [
        "mall.lbxcn.com", "jfsc.lbxcn.com", "mall-photo.lbxcn.com",
        "o2o.lbxcn.com", "api.o2o.lbxcn.com", "h5.o2o.lbxcn.com", "m.o2o.lbxcn.com",
        "api.mall.lbxcn.com", "mall-api.lbxcn.com", "gateway.mall.lbxcn.com", "mall-gateway.lbxcn.com",
        "api.lbxcn.com", "gateway.lbxcn.com", "mp.lbxcn.com", "wx.lbxcn.com", "weixin.lbxcn.com",
        "admin.o2o.lbxcn.com",
    ]
    for host in candidates:
        item = {"host": host}
        try:
            item["ips"] = sorted(set(socket.gethostbyname_ex(host)[2]))
        except Exception as e:
            item["dns_error"] = repr(e)
        if item.get("ips"):
            res = get("https://" + host + "/", referer="https://www.lbxdrugs.com/", timeout=12, max_bytes=800_000)
            text = res.get("text", "")
            item.update({k: v for k, v in res.items() if k != "text"})
            title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            item["title"] = re.sub(r"\s+", " ", title.group(1)).strip() if title else ""
            item["analysis"] = analyze_text(res.get("final_url") or ("https://" + host + "/"), text)
        report["host_probes"].append(item)

    compact = {
        "page_summary": [
            {k: p.get(k) for k in ("url", "status", "final_url", "content_type", "length")} |
            {"script_count": len(p.get("scripts", [])), "domains": p.get("domains", []), "paths": p.get("paths", [])[:30], "context_count": len(p.get("contexts", []))}
            for p in report["pages"]
        ],
        "asset_findings": [
            {"url": a.get("url"), "status": a.get("status"), "length": a.get("length"), "domains": a.get("domains", []), "paths": a.get("paths", [])[:80], "contexts": a.get("contexts", [])[:25]}
            for a in report["assets"] if a.get("domains") or a.get("paths") or a.get("contexts")
        ],
        "host_probes": [
            {k: h.get(k) for k in ("host", "ips", "status", "final_url", "content_type", "length", "title", "dns_error")}
            for h in report["host_probes"]
        ],
    }
    (OUT / "full_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "compact_report.json").write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(compact, ensure_ascii=False, indent=2)[:100000])


if __name__ == "__main__":
    main()
