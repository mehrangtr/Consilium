#!/usr/bin/env python3
"""Hash-bound native visual and real output evidence; no external model calls."""
import hashlib
import json
from pathlib import Path

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


def main():
    try:
        source = q.source_digest(ROOT)
        real = q.load(ROOT/'evidence/p07/REAL_OUTPUT.json')
        review = q.load(ROOT/'evidence/p07/VISUAL_REVIEW.json')
        q.require(real['status']=='PASS' and real['new_model_calls']==0, 'Real output reproduction missing')
        q.require(real['source_digest']==source, 'Stale output reproduction')
        q.require(review['status']=='PASS' and review['source_digest']==source, 'Visual review missing or stale')
        for target in ('Windows', 'Linux'):
            folder = ROOT/'evidence/p07-visual'/target
            report = q.load(folder/'RUN.json')
            q.require(report['host']==target and report['source_digest']==source, 'Visual host/source mismatch')
            q.require(report['status']=='CAPTURED_REQUIRES_HUMAN_VISUAL_REVIEW', 'Capture missing')
            q.require(len(report['records'])==2 and {r['name'] for r in report['records']}=={'desktop','mobile'}, 'Views missing')
            q.require(hashlib.sha256((folder/'sample.html').read_bytes()).hexdigest()==report['source_html_sha256'], 'HTML changed')
            for row in report['records']:
                raw = (folder/(row['name']+'.png')).read_bytes()
                q.require(row['screenshot']==row['name']+'.png' and raw[:8]==b'\x89PNG\r\n\x1a\n'
                          and hashlib.sha256(raw).hexdigest()==row['sha256'], 'Screenshot changed')
                q.require(any(r['target']==target and r['name']==row['name'] and r['sha256']==row['sha256']
                              and r['result']=='PASS' for r in review['views']), 'Screenshot not reviewed')
        print(json.dumps({'status':'PASS','source_digest':source,'phase_accepted':False}))
        return 0
    except (q.Blocked, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'status':'BLOCKED','reason':'Current real output and both native visual reviews required'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
