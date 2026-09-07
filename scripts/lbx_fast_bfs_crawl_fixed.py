#!/usr/bin/env python3
"""Launch the corrected LBX public nearby-store crawler.

The underlying crawler already uses strict string handling for is_close and
physical-store deduplication headed by org_code. This thin runner avoids
changing its function signatures.
"""
from __future__ import annotations

import json

import lbx_fast_bfs_crawl as base


if __name__ == "__main__":
    print(json.dumps({
        "runner": "lbx_fast_bfs_crawl_fixed",
        "workers": base.WORKERS,
        "seed_step": base.SEED_STEP,
        "max_requests": base.MAX_REQUESTS,
        "max_seconds": base.MAX_SECONDS,
        "status_handling": "open when is_close is empty or string 0",
        "physical_store_key_order": ["org_code", "shop_id", "fallback"],
    }, ensure_ascii=False), flush=True)
    base.main()
