#!/usr/bin/env python3
"""Resume/expand a prior LBX public nearby-store crawl.

The input artifact is a previous crawl snapshot. This pass prioritizes the
coordinates of stores first discovered through the graph, then all known store
coordinates, then cardinal offsets around county centers. Newly found store
coordinates are inserted at the front of the queue so the graph frontier keeps
expanding. No authentication or access-control bypass is used.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lbx_national_crawl as base  # noqa: E402

INPUT = Path(os.environ.get("LBX_INPUT_DIR", "input"))
OUT = Path(os.environ.get("LBX_OUT_DIR", "lbx_resume_output"))
OUT.mkdir(parents=True, exist_ok=True)
MAX_RUNTIME = int(os.environ.get("LBX_MAX_RUNTIME", "780"))
BATCH_SIZE = int(os.environ.get("LBX_BATCH_SIZE", "800"))


def read_jsonl_gz(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def find_input(name: str) -> Path:
    matches = list(INPUT.rglob(name))
    if not matches:
        raise FileNotFoundError(f"Cannot find {name} under {INPUT}")
    return matches[0]


def main() -> None:
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    raw_path = find_input("stores_raw.jsonl.gz")
    prior_stats_path = find_input("crawl_stats.json")
    prior_rows = read_jsonl_gz(raw_path)
    prior_stats = json.loads(prior_stats_path.read_text("utf-8"))
    stores = {base.store_key(r): dict(r) for r in prior_rows}

    admin_tree = base.fetch_json(base.ADMIN_URL)
    nodes, city_to_province = base.flatten_admin(admin_tree)
    _, target_counties = base.initial_seeds(nodes)

    scheduled: set[str] = set()
    queried: set[str] = set()
    queue: deque[base.QueryPoint] = deque()

    def enqueue(lat: float, lng: float, source: str, province_hint: str = "", admin_code: str = "", admin_name: str = "", left: bool = False) -> None:
        p = base.QueryPoint(lat=lat, lng=lng, source=source, province_hint=province_hint, admin_code=admin_code, admin_name=admin_name)
        if p.coord_key in scheduled:
            return
        scheduled.add(p.coord_key)
        if left:
            queue.appendleft(p)
        else:
            queue.append(p)

    # Likely frontier rows first.
    for first_source in ("store_graph", "admin_county", "admin_prefecture", "admin_province", ""):
        for row in prior_rows:
            if str(row.get("_first_seen_source") or "") != first_source:
                continue
            c = base.row_coord(row)
            if c:
                enqueue(c[0], c[1], "resume_known_store", str(row.get("_first_seen_province_hint") or ""), admin_name=str(row.get("deptName") or ""))

    # Cardinal offsets around all county centers in known/current markets.
    for node in target_counties:
        for dlat, dlng in ((0.15, 0.0), (-0.15, 0.0), (0.0, 0.18), (0.0, -0.18)):
            enqueue(
                float(node["lat"]) + dlat,
                float(node["lng"]) + dlng,
                "resume_county_offset",
                str(node.get("province") or ""),
                str(node.get("code") or ""),
                str(node.get("name") or ""),
            )

    requests_done = 0
    successful = 0
    failures: list[dict[str, Any]] = []
    query_sources = Counter()
    first_seen_sources = Counter(str(r.get("_first_seen_source") or "prior") for r in stores.values())
    initial_count = len(stores)

    def add_row(row: dict[str, Any], point: base.QueryPoint) -> bool:
        key = base.store_key(row)
        if key in stores:
            return False
        enriched = dict(row)
        enriched["_store_key"] = key
        enriched["_first_seen_source"] = point.source
        enriched["_first_seen_province_hint"] = point.province_hint
        enriched["_first_seen_admin_code"] = point.admin_code
        enriched["_first_seen_admin_name"] = point.admin_name
        enriched["_first_seen_query_lat"] = point.lat
        enriched["_first_seen_query_lng"] = point.lng
        stores[key] = enriched
        first_seen_sources[point.source] += 1
        c = base.row_coord(enriched)
        if c:
            enqueue(c[0], c[1], "resume_new_store_graph", point.province_hint, admin_name=str(enriched.get("deptName") or ""), left=True)
        return True

    with ThreadPoolExecutor(max_workers=base.MAX_WORKERS) as executor:
        while queue and time.monotonic() - started <= MAX_RUNTIME:
            batch: list[base.QueryPoint] = []
            while queue and len(batch) < BATCH_SIZE:
                p = queue.popleft()
                if p.coord_key in queried:
                    continue
                queried.add(p.coord_key)
                batch.append(p)
            if not batch:
                continue
            future_map = {executor.submit(base.query_endpoint, p): p for p in batch}
            newly_discovered = 0
            for future in as_completed(future_map):
                p = future_map[future]
                requests_done += 1
                query_sources[p.source] += 1
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    result = {"ok": False, "rows": [], "error": repr(exc)}
                if not result.get("ok"):
                    failures.append({"lat": p.lat, "lng": p.lng, "source": p.source, "province_hint": p.province_hint, "error": result.get("error", "unknown")})
                    continue
                successful += 1
                for row in result.get("rows") or []:
                    if add_row(row, p):
                        newly_discovered += 1
            if requests_done % 400 < len(batch):
                pharmacy_count = sum(1 for r in stores.values() if base.is_pharmacy(r))
                print(json.dumps({
                    "requests": requests_done,
                    "successful": successful,
                    "failures": len(failures),
                    "all_records": len(stores),
                    "pharmacies": pharmacy_count,
                    "new_in_batch": newly_discovered,
                    "queue": len(queue),
                    "elapsed": round(time.monotonic() - started, 1),
                }, ensure_ascii=False), flush=True)

    all_rows = sorted(stores.values(), key=lambda r: (str(r.get("city") or ""), str(r.get("parentName") or ""), str(r.get("deptName") or r.get("org_name") or ""), str(r.get("shop_id") or "")))
    pharmacy_rows = [r for r in all_rows if base.is_pharmacy(r)]
    non_pharmacy_rows = [r for r in all_rows if not base.is_pharmacy(r)]
    base.write_jsonl_gz(OUT / "stores_raw.jsonl.gz", all_rows)
    base.write_jsonl_gz(OUT / "stores_pharmacy.jsonl.gz", pharmacy_rows)
    base.write_jsonl_gz(OUT / "stores_non_pharmacy.jsonl.gz", non_pharmacy_rows)
    base.write_csv_gz(OUT / "stores_pharmacy.csv.gz", pharmacy_rows)
    with (OUT / "query_failures.jsonl").open("w", encoding="utf-8") as f:
        for row in failures:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    finished_at = datetime.now(timezone.utc).isoformat()
    parent_counts = Counter(str(r.get("parentName") or "(空)") for r in pharmacy_rows)
    city_counts = Counter(str(r.get("city") or "(空)") for r in pharmacy_rows)
    stats = {
        "endpoint": base.ENDPOINT,
        "admin_source": base.ADMIN_URL,
        "resume_source_artifact": "lbx-fast-national-output / run 34109189392",
        "prior_stats": prior_stats,
        "crawl_started_at_utc": started_at,
        "crawl_finished_at_utc": finished_at,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "complete_queue_exhausted": not bool(queue),
        "runtime_ceiling_seconds": MAX_RUNTIME,
        "requests_per_second_limit": base.REQUESTS_PER_SECOND,
        "max_workers": base.MAX_WORKERS,
        "initial_linked_records": initial_count,
        "query_points_scheduled": len(scheduled),
        "query_points_queried": len(queried),
        "requests_done": requests_done,
        "successful_queries": successful,
        "failed_queries": len(failures),
        "all_linked_records": len(all_rows),
        "pharmacy_records": len(pharmacy_rows),
        "non_pharmacy_records": len(non_pharmacy_rows),
        "new_linked_records": len(all_rows) - initial_count,
        "distinct_valid_store_coordinates": len({f"{c[0]:.6f},{c[1]:.6f}" for r in all_rows if (c := base.row_coord(r))}),
        "query_source_counts": dict(query_sources),
        "first_seen_source_counts": dict(first_seen_sources),
        "top_100_parent_companies": parent_counts.most_common(100),
        "top_200_api_cities": city_counts.most_common(200),
        "city_to_province_map": city_to_province,
        "notes": [
            "Resume pass over a prior public nearby-store crawl snapshot.",
            "Known store coordinates and county-offset seeds are traversed; no authentication or access-control bypass is used.",
            "This remains a crawl snapshot rather than an official corporate master-data export.",
        ],
    }
    (OUT / "crawl_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("elapsed_seconds", "complete_queue_exhausted", "requests_done", "failed_queries", "all_linked_records", "pharmacy_records", "new_linked_records", "distinct_valid_store_coordinates")}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
