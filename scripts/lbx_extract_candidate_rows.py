#!/usr/bin/env python3
"""Extract address/store-like rows from public LBX bidding spreadsheets already downloaded."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

SRC = Path("fast_output/candidate_attachments")
OUT = Path("candidate_extract_output")
OUT.mkdir(exist_ok=True)

STORE_TERMS = ["老百姓", "大药房", "健康药房", "门店", "药店", "药房", "店名", "店号", "门店编码", "网点"]
ADDRESS_TERMS = ["地址", "省", "市", "区", "县", "街道", "街", "路", "号", "镇", "乡", "村", "大道", "巷", "广场", "商场", "小区"]
HEADER_TERMS = ["门店名称", "店名", "门店", "地址", "省份", "省", "城市", "市", "区县", "区", "电话", "联系人", "经度", "纬度"]
ADDRESS_RE = re.compile(r"(?:省|自治区|特别行政区|市|区|县|旗|街道|街|路|大道|号|镇|乡|村|巷|小区|广场|商场)")
PHONE_RE = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}[-— ]?\d{7,8}|400[-— ]?\d{3}[-— ]?\d{4})(?!\d)")


def cell_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return re.sub(r"\s+", " ", s)


def row_score(vals: list[str]) -> tuple[int, list[str]]:
    joined = " | ".join(x for x in vals if x)
    hits: list[str] = []
    score = 0
    for t in STORE_TERMS:
        if t in joined:
            hits.append(t)
            score += 6 if t in {"老百姓", "大药房", "健康药房"} else 3
    for t in ADDRESS_TERMS:
        if t in joined:
            score += 1
    addr_n = len(ADDRESS_RE.findall(joined))
    score += min(addr_n, 6)
    if PHONE_RE.search(joined):
        hits.append("电话")
        score += 3
    if any(t in joined for t in HEADER_TERMS):
        hits.append("表头")
        score += 5
    if len([x for x in vals if x]) >= 3:
        score += 1
    return score, sorted(set(hits))


def main() -> None:
    inventory: list[dict[str, Any]] = []
    extracted: list[list[Any]] = []
    all_rows: list[list[Any]] = []

    for path in sorted(SRC.glob("*.xlsx")):
        rec: dict[str, Any] = {"file": path.name, "size": path.stat().st_size, "sheets": []}
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            rec["error"] = repr(exc)
            inventory.append(rec)
            continue
        for ws in wb.worksheets:
            sheet_rec: dict[str, Any] = {
                "sheet": ws.title,
                "max_row": ws.max_row or 0,
                "max_col": ws.max_column or 0,
                "nonempty_rows": 0,
                "store_like_rows": 0,
                "address_like_rows": 0,
                "header_candidates": [],
                "top_scored_rows": [],
            }
            scored: list[tuple[int, int, list[str], list[str]]] = []
            for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                vals = [cell_text(v) for v in row]
                # Trim trailing blanks but keep at least one field.
                while vals and not vals[-1]:
                    vals.pop()
                if not any(vals):
                    continue
                sheet_rec["nonempty_rows"] += 1
                joined = " | ".join(vals)
                score, hits = row_score(vals)
                if any(t in joined for t in STORE_TERMS):
                    sheet_rec["store_like_rows"] += 1
                if len(ADDRESS_RE.findall(joined)) >= 2 or "地址" in joined:
                    sheet_rec["address_like_rows"] += 1
                if row_idx <= 40 and any(t in joined for t in HEADER_TERMS):
                    sheet_rec["header_candidates"].append({"row": row_idx, "values": vals[:40]})
                if score >= 7:
                    extracted.append([path.name, ws.title, row_idx, score, ",".join(hits), *vals[:60]])
                    scored.append((score, row_idx, hits, vals[:40]))
                # Preserve every row for sheets that look like operational lists.
                if (ws.max_row or 0) >= 30:
                    all_rows.append([path.name, ws.title, row_idx, *vals[:80]])
                if row_idx >= 100000:
                    break
            scored.sort(key=lambda x: (-x[0], x[1]))
            sheet_rec["top_scored_rows"] = [
                {"score": s, "row": r, "hits": h, "values": v}
                for s, r, h, v in scored[:30]
            ]
            rec["sheets"].append(sheet_rec)
        wb.close()
        inventory.append(rec)

    (OUT / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    max_cols = max((len(r) for r in extracted), default=5)
    headers = ["源文件", "工作表", "行号", "评分", "命中"] + [f"字段{i}" for i in range(1, max_cols - 4)]
    with (OUT / "address_store_rows.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in extracted:
            w.writerow(r + [""] * (max_cols - len(r)))
    max_all_cols = max((len(r) for r in all_rows), default=3)
    all_headers = ["源文件", "工作表", "行号"] + [f"字段{i}" for i in range(1, max_all_cols - 2)]
    with (OUT / "all_rows.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(all_headers)
        for r in all_rows:
            w.writerow(r + [""] * (max_all_cols - len(r)))
    summary = {
        "files": len(inventory),
        "sheets": sum(len(x.get("sheets", [])) for x in inventory),
        "extracted_rows": len(extracted),
        "all_rows": len(all_rows),
        "largest_sheets": sorted(
            [
                {"file": x["file"], **s}
                for x in inventory
                for s in x.get("sheets", [])
            ],
            key=lambda z: (-(z.get("max_row") or 0), z["file"], z["sheet"]),
        )[:50],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
