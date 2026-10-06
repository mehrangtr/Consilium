#!/usr/bin/env python3
"""Non-mutating lexical Bidi check, not a renderer or semantic proof."""
from __future__ import annotations
from pathlib import Path
import re
import sys
FA=re.compile(r'[\u0600-\u06ff]')
LATIN_RUN=re.compile(r'[A-Za-z][A-Za-z0-9_./:\\-]{2,}')
CONTROL=re.compile(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069]')
FENCE=re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
TICKS=re.compile(r'`+')

def strip_inline_code(line):
    runs=list(TICKS.finditer(line))
    output=[]
    start=0
    i=0
    while i<len(runs):
        opener=runs[i]
        closer=next((j for j in range(i+1,len(runs)) if len(runs[j][0])==len(opener[0])),None)
        if closer is None:
            i+=1
            continue
        output += [line[start:opener.start()], ' ']
        start=runs[closer].end()
        i=closer+1
    output.append(line[start:])
    return ''.join(output)

def issues_in(text):
    issues=[]
    fence=None
    opener_line=None
    for n,line in enumerate(text.splitlines(),1):
        if CONTROL.search(line):
            issues.append((n,'contains invisible bidi control characters'))
        marker=FENCE.match(line)
        if fence:
            if marker and marker[1][0]==fence[0] and len(marker[1])>=fence[1] and not marker[2].strip():
                fence=None
            continue
        if marker and not (marker[1][0]=='`' and '`' in marker[2]):
            fence=(marker[1][0],len(marker[1]))
            opener_line=n
            continue
        if line.startswith('    ') or line.startswith('\t'):
            continue
        visible=strip_inline_code(line)
        visible=re.sub(r'(?<=\])\([^\n)]*\)','',visible)
        if FA.search(visible) and LATIN_RUN.search(visible):
            issues.append((n,'mixed Persian/Latin prose may need visible isolation'))
    if fence:
        issues.append((opener_line,'unclosed fenced code block'))
    return issues

def check(path):
    issues=issues_in(Path(path).read_text(encoding='utf-8'))
    if issues:
        print(f'{path}:')
        for line,message in issues:
            print(f'  L{line}: {message}')
        return 1
    print(f'{path}: LEXICAL_CHECK=PASS (rendering not certified)')
    return 0

def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if not args:
        print('Usage: check_markdown_bidi.py <file.md> [more.md ...]')
        return 2
    result=0
    for name in args:
        if Path(name).suffix.lower()!='.md':
            print(f'Expected a Markdown input: {name}',file=sys.stderr)
            return 2
        try:
            result |= check(name)
        except OSError as exc:
            print(str(exc),file=sys.stderr)
            return 2
    return result

if __name__=='__main__':
    raise SystemExit(main())
