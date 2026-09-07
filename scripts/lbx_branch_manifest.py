#!/usr/bin/env python3
"""Summarize all LBX crawl outputs on the temporary branch."""
from __future__ import annotations

import csv
import gzip
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path('.')
OUT = Path('probe_output')
OUT.mkdir(exist_ok=True)
SKIP_DIRS = {'.git', '.venv', 'node_modules', '__pycache__'}
DATA_EXTS = {'.csv', '.tsv', '.json', '.jsonl', '.ndjson', '.xlsx', '.zip', '.gz', '.parquet', '.txt'}
KEYWORDS = ('store', 'shop', 'poi', 'pharmacy', 'lbx', 'baidu', 'amap', '门店', '药房', '药店', 'national', 'nationwide', 'final', 'merged', 'complete')


def iter_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            p = Path(base) / fn
            if p == OUT / 'branch_manifest.json' or p == OUT / 'branch_manifest.txt':
                continue
            yield p


def line_count_text(p: Path, limit_bytes: int = 50_000_000) -> int | None:
    try:
        if p.stat().st_size > limit_bytes:
            return None
        with p.open('rb') as f:
            return sum(1 for _ in f)
    except Exception:
        return None


def csv_info(p: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        opener = gzip.open if p.suffix.lower() == '.gz' else open
        with opener(p, 'rt', encoding='utf-8-sig', errors='replace', newline='') as f:
            sample = f.read(65536)
        dialect = csv.Sniffer().sniff(sample[:20000], delimiters=',\t;')
        reader = csv.reader(sample.splitlines(), dialect)
        rows = list(reader)
        info['header'] = rows[0][:50] if rows else []
        info['sample_rows'] = rows[1:4]
    except Exception as e:
        info['parse_error'] = repr(e)
    info['line_count'] = line_count_text(p)
    if info.get('line_count') is not None:
        info['estimated_data_rows'] = max(0, info['line_count'] - 1)
    return info


def json_info(p: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        if p.stat().st_size > 20_000_000:
            info['skipped_parse'] = 'over_20mb'
            return info
        text = p.read_text(encoding='utf-8-sig', errors='replace')
        obj = json.loads(text)
        if isinstance(obj, list):
            info['json_type'] = 'list'
            info['length'] = len(obj)
            info['sample'] = obj[:2]
        elif isinstance(obj, dict):
            info['json_type'] = 'dict'
            info['keys'] = list(obj.keys())[:80]
            for k in ('stores', 'data', 'pois', 'items', 'results', 'records'):
                v = obj.get(k)
                if isinstance(v, list):
                    info[f'{k}_length'] = len(v)
                    info[f'{k}_sample'] = v[:2]
    except Exception as e:
        info['parse_error'] = repr(e)
    return info


def text_preview(p: Path) -> str | None:
    try:
        if p.stat().st_size > 2_000_000:
            return None
        return p.read_text(encoding='utf-8-sig', errors='replace')[:3000]
    except Exception:
        return None


def main() -> None:
    entries: list[dict[str, Any]] = []
    for p in sorted(iter_files(), key=lambda x: str(x)):
        rel = p.as_posix().lstrip('./')
        stat = p.stat()
        ext = p.suffix.lower()
        low = rel.lower()
        relevant = ext in DATA_EXTS and any(k.lower() in low for k in KEYWORDS)
        e: dict[str, Any] = {
            'path': rel,
            'size': stat.st_size,
            'extension': ext,
            'relevant': relevant,
        }
        if relevant:
            if ext in {'.csv', '.tsv'} or (ext == '.gz' and p.name.lower().endswith(('.csv.gz', '.tsv.gz'))):
                e['inspection'] = csv_info(p)
            elif ext == '.json':
                e['inspection'] = json_info(p)
            elif ext in {'.txt', '.jsonl', '.ndjson'}:
                e['line_count'] = line_count_text(p)
                preview = text_preview(p)
                if preview is not None:
                    e['preview'] = preview
        entries.append(e)

    relevant = [e for e in entries if e['relevant']]
    report = {
        'file_count': len(entries),
        'relevant_file_count': len(relevant),
        'relevant_files': sorted(relevant, key=lambda e: (-e['size'], e['path'])),
        'all_paths': [e['path'] for e in entries],
    }
    (OUT / 'branch_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        f"file_count={len(entries)}",
        f"relevant_file_count={len(relevant)}",
        '',
        '== Relevant files (largest first) ==',
    ]
    for e in report['relevant_files']:
        ins = e.get('inspection', {})
        detail = ''
        if 'estimated_data_rows' in ins:
            detail = f" rows={ins['estimated_data_rows']} header={ins.get('header')}"
        elif 'length' in ins:
            detail = f" json_length={ins['length']}"
        elif e.get('line_count') is not None:
            detail = f" lines={e['line_count']}"
        lines.append(f"{e['size']:>10}\t{e['path']}{detail}")
    (OUT / 'branch_manifest.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
