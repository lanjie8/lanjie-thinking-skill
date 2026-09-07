#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHARMACY_POSITIVE = ("药房", "药店", "医药", "药业", "药品", "药行", "老百姓", "百姓平安", "百杏堂")
PHARMACY_NEGATIVE = ("诊所", "医院", "门诊部", "体检", "健康管理", "医疗器械公司", "电子商务公司", "物流", "仓库", "配送中心")


def compact(value: Any) -> str:
    return re.sub(r"[\s\u3000\-—_（）()【】\[\]·,，.。]", "", str(value or "")).lower()


def valid_coord(lat: Any, lng: Any) -> tuple[float, float] | None:
    try:
        a, b = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    return (a, b) if 15 <= a <= 55.5 and 72 <= b <= 136 else None


def row_coord(row: dict[str, Any]) -> tuple[float, float] | None:
    for a, b in (("latGd", "lngGd"), ("lat", "lng"), ("latitude", "longitude"), ("latBd", "lngBd")):
        value = valid_coord(row.get(a), row.get(b))
        if value:
            return value
    return None


def store_key(row: dict[str, Any]) -> str:
    for field in ("shop_id", "sap_id", "org_code", "_store_key"):
        value = str(row.get(field) or "").strip()
        if value and value not in {"0", "None", "null"}:
            return f"{field}:{value}"
    coord = row_coord(row)
    name = compact(row.get("deptName") or row.get("org_name"))
    address = compact(row.get("deptAddr"))
    if coord:
        return f"fallback:{name}:{coord[0]:.6f}:{coord[1]:.6f}:{address}"
    return f"fallback:{name}:{address}:{compact(row.get('phone'))}"


def is_pharmacy(row: dict[str, Any]) -> bool:
    text = "|".join(str(row.get(k) or "") for k in ("deptName", "org_name", "parentName", "third_org_name", "deptAddr"))
    if any(word in text for word in PHARMACY_NEGATIVE):
        own = str(row.get("deptName") or "") + str(row.get("org_name") or "")
        if not any(word in own for word in ("药房", "药店", "医药", "药业")):
            return False
    if any(word in text for word in PHARMACY_POSITIVE):
        return True
    parent = str(row.get("parentName") or "")
    own = str(row.get("deptName") or "")
    return bool("老百姓大药房" in parent and own and not any(x in own for x in PHARMACY_NEGATIVE))


def load_jsonl_gz(path: Path, stores: dict[str, dict[str, Any]]) -> int:
    added = 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            key = store_key(row)
            if key not in stores:
                stores[key] = row
                added += 1
    return added


def write_jsonl_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    preferred = ["shop_id", "sap_id", "org_code", "deptName", "org_name", "parentName", "third_org_name", "city", "deptAddr", "phone", "latGd", "lngGd", "latBd", "lngBd", "shopLabels", "is_m_shop", "is_close", "sales_scan_name", "summer_start_hours", "summer_closing_hours", "winter_start_hours", "winter_closing_hours", "shipStartTime", "shipEndTime", "_first_seen_source", "_first_seen_province_hint", "_first_seen_admin_name", "_first_seen_query_lat", "_first_seen_query_lng"]
    ordered = [x for x in preferred if x in fields] + [x for x in fields if x not in preferred]
    with gzip.open(path, "wt", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--parts-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    parts_dir = Path(args.parts_dir)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    stores: dict[str, dict[str, Any]] = {}
    base_file = next(iter(base_dir.rglob("stores_raw.jsonl.gz")))
    load_jsonl_gz(base_file, stores)
    base_count = len(stores)
    part_files = sorted(parts_dir.rglob("stores_raw.jsonl.gz"))
    part_stats = []
    additions = []
    for path in part_files:
        additions.append({"path": str(path), "new_union_records": load_jsonl_gz(path, stores)})
        stat_path = path.with_name("stats.json")
        if stat_path.exists():
            part_stats.append(read_json(stat_path))

    all_rows = sorted(stores.values(), key=lambda r: (str(r.get("city") or ""), str(r.get("parentName") or ""), str(r.get("deptName") or r.get("org_name") or ""), str(r.get("shop_id") or "")))
    pharmacy = [row for row in all_rows if is_pharmacy(row)]
    non_pharmacy = [row for row in all_rows if not is_pharmacy(row)]
    write_jsonl_gz(output / "stores_raw.jsonl.gz", all_rows)
    write_jsonl_gz(output / "stores_pharmacy.jsonl.gz", pharmacy)
    write_jsonl_gz(output / "stores_non_pharmacy.jsonl.gz", non_pharmacy)
    write_csv_gz(output / "stores_pharmacy.csv.gz", pharmacy)

    base_stats_path = next(iter(base_dir.rglob("crawl_stats.json")), None)
    base_stats = read_json(base_stats_path) if base_stats_path else {}
    parent_counts = Counter(str(row.get("parentName") or "(空)") for row in pharmacy)
    city_counts = Counter(str(row.get("city") or "(空)") for row in pharmacy)
    aggregate = {
        "endpoint": base_stats.get("endpoint") or "https://yx.lbxcn.com/out/2212sping/getlbxStoreList",
        "admin_source": base_stats.get("admin_source"),
        "crawl_started_at_utc": base_stats.get("crawl_started_at_utc"),
        "crawl_finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete_queue_exhausted": bool(part_stats) and all(int(x.get("remaining_queue") or 0) == 0 for x in part_stats),
        "base_all_linked_records": base_count,
        "all_linked_records": len(all_rows),
        "pharmacy_records": len(pharmacy),
        "non_pharmacy_records": len(non_pharmacy),
        "distinct_valid_store_coordinates": len({f"{c[0]:.6f},{c[1]:.6f}" for row in all_rows if (c := row_coord(row))}),
        "query_points_queried": int(base_stats.get("query_points_queried") or 0) + sum(int(x.get("queried_points") or 0) for x in part_stats),
        "successful_queries": int(base_stats.get("successful_queries") or 0) + sum(int(x.get("successful_queries") or 0) for x in part_stats),
        "failed_queries": int(base_stats.get("failed_queries") or 0) + sum(int(x.get("failed_queries") or 0) for x in part_stats),
        "part_count": len(part_files),
        "part_stats": part_stats,
        "merge_additions": additions,
        "top_100_parent_companies": parent_counts.most_common(100),
        "top_200_api_cities": city_counts.most_common(200),
        "city_to_province_map": base_stats.get("city_to_province_map") or {},
        "notes": [
            "Public nearby-store interface crawl; not an official bulk export.",
            "Union of administrative-center first pass and four parallel county-offset/store-graph continuation partitions.",
            "Named contact-person fields remain only in raw JSON and should not be surfaced by default.",
        ],
    }
    (output / "crawl_stats.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: aggregate[k] for k in ("base_all_linked_records", "all_linked_records", "pharmacy_records", "non_pharmacy_records", "query_points_queried", "successful_queries", "failed_queries", "complete_queue_exhausted", "part_count")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
