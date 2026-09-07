#!/usr/bin/env python3
"""Performance-fixed entry point for the full LBX public store crawl."""
from __future__ import annotations

import asyncio
import json
import random

import aiohttp

import lbx_full_store_crawl as base


async def fetch_rows_v2(
    session: aiohttp.ClientSession, lat: float, lng: float
) -> tuple[list[dict], int | None, str | None]:
    """Treat the endpoint's ``data.data = null`` as a normal empty result."""
    params = {"Latitude": f"{lat:.7f}", "Longitude": f"{lng:.7f}"}
    last_error: str | None = None
    for attempt in range(1, base.MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=base.REQUEST_TIMEOUT)
            async with session.get(base.ENDPOINT, params=params, timeout=timeout) as resp:
                status = resp.status
                text = await resp.text(encoding="utf-8", errors="replace")
                if status == 200:
                    try:
                        obj = json.loads(text.lstrip("\ufeff"))
                    except json.JSONDecodeError:
                        last_error = f"json_decode:{text[:180]}"
                    else:
                        if not isinstance(obj, dict):
                            last_error = f"unexpected_schema:{text[:280]}"
                        else:
                            code = str(obj.get("code", ""))
                            message = str(obj.get("message", ""))
                            data = obj.get("data")
                            # Known hard/backend failures should still be retried.
                            if code.startswith("-") or any(
                                token in message for token in ("异常", "失败", "错误", "超时")
                            ):
                                last_error = f"api_error:{code}:{message[:180]}"
                            elif data is None:
                                return [], status, None
                            elif isinstance(data, list):
                                return [x for x in data if isinstance(x, dict)], status, None
                            elif isinstance(data, dict):
                                rows = data.get("data")
                                if rows is None:
                                    return [], status, None
                                if isinstance(rows, list):
                                    return [x for x in rows if isinstance(x, dict)], status, None
                                last_error = f"unexpected_rows:{type(rows).__name__}:{text[:280]}"
                            else:
                                last_error = f"unexpected_data:{type(data).__name__}:{text[:280]}"
                elif status in {429, 500, 502, 503, 504}:
                    last_error = f"http_{status}:{text[:180]}"
                else:
                    return [], status, f"http_{status}:{text[:280]}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = repr(exc)
        if attempt < base.MAX_RETRIES:
            await asyncio.sleep((0.45 * (2 ** (attempt - 1))) + random.random() * 0.25)
    return [], None, last_error or "unknown_error"


base.fetch_rows = fetch_rows_v2

if __name__ == "__main__":
    asyncio.run(base.async_main())
