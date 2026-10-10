#!/usr/bin/env python3
"""Native Chrome screenshots of a synthetic mixed-text complete output fixture."""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests/council')]
import qualityctl as q
import test_council as fixtures

from consilium.shell.council_export import export_council, render_html


def main():
    folder = ROOT/'evidence/p07-visual'/platform.system()
    folder.mkdir(parents=True, exist_ok=True)
    browser = next((shutil.which(name) for name in ('google-chrome', 'chromium', 'chrome') if shutil.which(name)), None)
    if browser is None:
        for base in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            candidate = Path(os.environ.get(base, ''))/'Google/Chrome/Application/chrome.exe'
            if candidate.is_file(): browser = str(candidate); break
    if not browser:
        print('Native Chrome is required for visual evidence')
        return 1
    fixture = fixtures.CouncilCase()
    fixture.setUp()
    try:
        fixture.through_review()
        fixture.finish()
        out = export_council(fixture.store, fixture.debate.debate_id, Path(fixture.temp.name)/'exports')
        snapshot = json.loads((out/'debate.json').read_text(encoding='utf-8'))
    finally:
        fixture.tearDown()
    snapshot['debate']['original_request'] = '''بررسی خوانایی فارسی و English
مسیر C:\\project\\report.json و /home/user/project/main.py
کد: result = A.intersection(C)
| مدل | نتیجه |
|---|---|
| GLM | پیشنهاد کوتاه |
[پیوند نمونه](https://example.org/report?q=1)
```python
print("فارسی English")
```
توافق به معنی احتمال درستی نیست.'''
    page = folder/'sample.html'
    page.write_text(render_html(snapshot), encoding='utf-8')
    version = (subprocess.run([browser, '--version'], capture_output=True, text=True, timeout=15, check=True).stdout.strip()
               if os.name != 'nt' else 'Chrome executable SHA256 '+hashlib.sha256(Path(browser).read_bytes()).hexdigest())
    records = []
    for name, size in (('desktop', '1280,900'), ('mobile', '390,844')):
        screenshot = folder/(name+'.png')
        command = [browser, '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
                   '--disable-background-networking', '--disable-default-apps', '--no-default-browser-check',
                   '--hide-scrollbars', '--allow-file-access-from-files', '--window-size='+size,
                   '--screenshot='+str(screenshot.resolve()), page.resolve().as_uri()]
        result = subprocess.run(command, capture_output=True, timeout=40, check=False)
        (folder/(name+'.log')).write_bytes(result.stdout+result.stderr)
        if result.returncode or not screenshot.is_file() or screenshot.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
            print('Native visual capture failed')
            return 1
        records.append({'name':name,'viewport_requested':size,'sha256':hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                        'screenshot':name+'.png'})
    report = {'status':'CAPTURED_REQUIRES_HUMAN_VISUAL_REVIEW','host':platform.system(), 'browser':version, 'source_digest':q.source_digest(ROOT),
              'scope':'P07_SYNTHETIC_MIXED_TEXT_OFFLINE_HTML_VIEWER_NOT_LIVE_MODEL_EVIDENCE',
              'source_html_sha256':hashlib.sha256(page.read_bytes()).hexdigest(), 'records':records}
    (folder/'RUN.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
