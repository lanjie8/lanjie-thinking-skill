#!/usr/bin/env python3
"""Corrected runner for the LBX public nearby-store crawler.

The API returns is_close as a string. The original exploratory script treated
"0" as truthy and therefore discarded open stores. This runner patches that
status check, keeps the physical-store deduplication key headed by org_code,
and persists a usable snapshot at every crawl checkpoint.
"""
from __future__ import annotations

import json
from typing import Any

import lbx_fast_bfs_crawl as base


def is_closed(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "closed", "停业", "关闭"}


def fixed_key(row: dict[str, Any]) -> str:
    # org_code collapses multiple H5/M-shop representations of the same physical outlet.
    for field in ("org_code", "shop_id", "sap_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    name = str(row.get("deptName") or row.get("org_name") or "").strip()
    address = str(row.get("deptAddr") or "").strip()
    coord = base.coord(row)
    return f"fallback:{name}|{address}|{coord or ''}"


def fixed_merge(rows: list[dict[str, Any]], stores: dict[str, dict[str, Any]]) -> int:
    added = 0
    for row in rows:
        if is_closed(row.get("is_close")):
            continue
        key = fixed_key(row)
        if key not in stores:
            stores[key] = row
            added += 1
        else:
            current = stores[key]
            for field, value in row.items():
                if current.get(field) in (None, "") and value not in (None, ""):
                    current[field] = value
    return added


_original_checkpoint = base.checkpoint


def fixed_checkpoint(phase: str, stores: dict[str, dict[str, Any]], wave: int, queued: int) -> None:
    _original_checkpoint(phase, stores, wave, queued)
    # Keep a recoverable data snapshot even if the outer workflow is interrupted.
    base.write_outputs(stores, f"running:{phase}:wave={wave}")


base.merge = fixed_merge
base.checkpoint = fixed_checkpoint


if __name__ == "__main__":
    print(json.dumps({
        "runner": "lbx_fast_bfs_crawl_fixed",
        "workers": base.WORKERS,
        "seed_step": base.SEED_STEP,
        "max_requests": base.MAX_REQUESTS,
        "max_seconds": base.MAX_SECONDS,
        "physical_store_key_order": ["org_code", "shop_id", "sap_id"],
        "closed_values": ["1", "true", "yes", "closed", "停业", "关闭"],
    }, ensure_ascii=False), flush=True)
    base.main()
