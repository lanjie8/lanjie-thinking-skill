#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path('.')
OUT = Path('compact_scan_output')
OUT.mkdir(exist_ok=True)

SEARCH_DIRS = [Path('yx_discovery_output'), Path('fast_output'), Path('probe_output')]
TEXT_EXTS = {'.js', '.txt', '.json', '.html', '.htm'}
KEY_RE = re.compile(
    r'附近门店|门店|药店|药房|store(?:List|Info|Code|Id|Name)?|shop(?:List|Info|Code|Id|Name)?|'
    r'branch|outlet|merchant|warehouse|longitude|latitude|\blng\b|\blat\b|getLocation|定位',
    re.I,
)
CALL_RE = re.compile(r'\b(?:fetch|axios\.(?:get|post|request)|\$\.ajax|\$\.get|\$\.post|request)\s*\(', re.I)
URL_RE = re.compile(r'''(?x)
    https?://[^\s"'<>\\`]+|
    //[A-Za-z0-9.-]+/[A-Za-z0-9_./?&=%${}:,@+-]*|
    /(?:[A-Za-z0-9_.~!$&()*+,;=:@%?+-]+/){1,10}[A-Za-z0-9_.~!$&()*+,;=:@%?+-]*
''')
QUOTED_RE = re.compile(r'''(?s)(["'`])((?:\\.|(?!\1).){1,600})\1''')
BASE_RE = re.compile(r'''(?i)(?:baseURL|baseUrl|apiHost|apiUrl|host|domain|gateway)\s*[:=]\s*(["'`])(.{4,300}?)\1''')


def clean(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def around(text: str, start: int, end: int, radius: int = 420) -> str:
    return clean(text[max(0, start-radius):min(len(text), end+radius)])


def iter_files():
    seen = set()
    for d in SEARCH_DIRS:
        if not d.exists():
            continue
        for p in d.rglob('*'):
            if not p.is_file() or p.suffix.lower() not in TEXT_EXTS:
                continue
            if p.stat().st_size > 12_000_000:
                continue
            if p in seen:
                continue
            seen.add(p)
            yield p


def score_candidate(value: str) -> int:
    score = 0
    low = value.lower()
    for w in ('store','shop','branch','outlet','merchant','warehouse','location','nearby','poi','map','门店','药店','药房'):
        if w in low:
            score += 3
    for w in ('api','crm','scc','mall','yx','activity','game','appointment','address','list','query','search','page'):
        if w in low:
            score += 1
    return score


def scan_file(path: Path) -> dict:
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return {'path': str(path), 'error': repr(e)}

    key_hits = []
    call_hits = []
    candidates = set()
    bases = set()

    for m in KEY_RE.finditer(text):
        key_hits.append({'term': m.group(0), 'context': around(text, m.start(), m.end())})
        if len(key_hits) >= 100:
            break

    for m in CALL_RE.finditer(text):
        call_hits.append({'call': m.group(0), 'context': around(text, m.start(), m.end(), 650)})
        if len(call_hits) >= 80:
            break

    for m in BASE_RE.finditer(text):
        bases.add(clean(m.group(2)))

    for m in URL_RE.finditer(text):
        value = m.group(0).rstrip('),.;]}')
        if score_candidate(value) > 0:
            candidates.add(value)

    for m in QUOTED_RE.finditer(text):
        value = clean(m.group(2))
        if 2 < len(value) < 600 and score_candidate(value) >= 2:
            candidates.add(value)

    return {
        'path': str(path),
        'size': path.stat().st_size,
        'bases': sorted(bases),
        'candidates': sorted(candidates, key=lambda x: (-score_candidate(x), len(x), x))[:800],
        'key_hits': key_hits,
        'call_hits': call_hits,
    }


def main():
    reports = []
    for path in iter_files():
        r = scan_file(path)
        if r.get('key_hits') or r.get('call_hits') or r.get('candidates') or r.get('bases'):
            reports.append(r)
    reports.sort(key=lambda r: (
        -len(r.get('key_hits', [])), -len(r.get('call_hits', [])), r.get('path', '')
    ))

    global_candidates = {}
    for r in reports:
        for c in r.get('candidates', []):
            global_candidates.setdefault(c, []).append(r['path'])

    compact = {
        'files_scanned': len(list(iter_files())),
        'interesting_files': len(reports),
        'top_files': [
            {
                'path': r['path'],
                'size': r.get('size'),
                'key_hit_count': len(r.get('key_hits', [])),
                'call_hit_count': len(r.get('call_hits', [])),
                'base_count': len(r.get('bases', [])),
                'candidate_count': len(r.get('candidates', [])),
            }
            for r in reports
        ],
        'bases': sorted({b for r in reports for b in r.get('bases', [])}),
        'global_candidates': [
            {'value': c, 'score': score_candidate(c), 'files': files}
            for c, files in sorted(global_candidates.items(), key=lambda kv: (-score_candidate(kv[0]), len(kv[0]), kv[0]))
        ],
        'reports': reports,
    }
    (OUT / 'compact_scan.json').write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        f"FILES_SCANNED\t{compact['files_scanned']}",
        f"INTERESTING_FILES\t{compact['interesting_files']}",
        '',
        'BASES',
    ]
    lines.extend(compact['bases'])
    lines += ['', 'TOP_CANDIDATES']
    for row in compact['global_candidates'][:1000]:
        lines.append(f"{row['score']}\t{row['value']}\t{'|'.join(row['files'][:5])}")
    lines += ['', 'TOP_KEY_CONTEXTS']
    for r in reports[:40]:
        lines.append(f"\n### {r['path']}")
        for hit in r.get('key_hits', [])[:30]:
            lines.append(f"[{hit['term']}] {hit['context']}")
        for hit in r.get('call_hits', [])[:20]:
            lines.append(f"[CALL] {hit['context']}")
    (OUT / 'compact_scan.txt').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines[:500]))


if __name__ == '__main__':
    main()
