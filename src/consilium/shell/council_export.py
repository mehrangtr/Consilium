"""Regenerable checkpoint exports, never a second operational state source."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from consilium.core.contracts import Answer


def literal(text):
    # Fence untrusted model Markdown, including its own nested fences, so mixed
    # RTL/LTR technical content and headings cannot damage the report scaffold.
    longest = max((len(m.group()) for m in re.finditer(r'`+', text)), default=0)
    fence = '`' * max(3, longest+1)
    return fence+'text\n'+text+'\n'+fence+'\n'


def render(snapshot):
    files = {'debate.json': (json.dumps(snapshot, ensure_ascii=False, indent=2)+'\n').encode('utf-8')}
    main = ['# تاریخچهٔ شورا\n', 'شناسهٔ بحث: `'+snapshot['debate']['debate_id']+'`\n',
            'پرسش اصلی:\n', literal(snapshot['debate']['original_request']),
            'وضعیت: `'+snapshot['wait_state']+'`\n', 'توافق به معنی احتمال درستی نیست.\n']
    by_participant = {pid: [] for pid in snapshot['debate']['participant_ids']}
    # Export canonical sources once; the complete machine history still includes
    # original attempts, incomplete/staged records, decisions and audit events.
    sources = snapshot['council_sources']
    for s in sources:
        item = s['item']; pid = item.get('participant_id', item.get('reviewer_id'))
        text = item.get('content') or json.dumps(item, ensure_ascii=False, indent=2)
        entry = '\n## دور `'+str(s['source_round']['number'])+'`\n\nمنشأ: `'+s['provenance']+'`\n\n'+literal(text)
        by_participant[pid].append(entry); main.append(entry)
    main.append('\n## تصمیم‌های کاربر\n\n')
    for row in snapshot['user_decisions']: main.append(literal(json.dumps(row, ensure_ascii=False, indent=2)))
    for analysis in snapshot['round_analyses']:
        main.append('\n## تحلیل دور\n\n'+literal(json.dumps(analysis, ensure_ascii=False, indent=2)))
    final = snapshot['final_council_result']
    if final:
        main.append('\n## نتیجهٔ نهایی و افشای داور\n\n'+literal(json.dumps(final, ensure_ascii=False, indent=2)))
    files['debate.md'] = ('\n'.join(main)).encode('utf-8')
    for index, (pid, entries) in enumerate(by_participant.items()):
        name = 'participant-'+str(index+1)
        files['participants/'+name+'.md'] = ('# تاریخچهٔ مشارکت‌کننده\n\nشناسه: `'+pid+'`\n'+''.join(entries)).encode('utf-8')
        if final:
            own = [s for s in sources if s['item'].get('participant_id') == pid and s['source_round']['kind'] != 'SYNTHESIS']
            assessment = {'participant_id': pid, 'method':'DERIVED_CANONICAL_POSITIONS_NOT_NEW_MODEL_JUDGMENT',
                'position_history':[s['item']['content'] for s in own], 'final_position':own[-1]['item']['content'] if own else None,
                'reviews_authored':[s['item'] for s in sources if s['item'].get('reviewer_id') == pid],
                'evidence_source_hashes':[s['content_hash'] for s in own],
                'preserved_reported_objections':final['preserved_objections'], 'agreement_is_truth_probability':False}
            files['assessments/'+name+'.md'] = ('# ارزیابی نهایی مشارکت‌کننده\n\n'+literal(json.dumps(assessment, ensure_ascii=False, indent=2))).encode('utf-8')
    if final: files['final.md'] = ('# نتیجهٔ نهایی شورا\n\n'+literal(json.dumps(final, ensure_ascii=False, indent=2))).encode('utf-8')
    return files


def export_council(store, debate_id, destination: Path):
    with store._transaction(write=False):
        snapshot = store.export_debate(debate_id)
        snapshot['council_sources'] = [{**s.model_dump(mode='json'), 'content_hash':s.content_hash}
                                       for s in store.sources.context_sources(debate_id)]
    files = render(snapshot)
    root = destination.resolve()/str(debate_id)
    root.mkdir(parents=True, exist_ok=True)
    target = root/('revision-'+str(snapshot['checkpoint']['revision']))
    index = {'debate_id': str(debate_id), 'revision': snapshot['checkpoint']['revision'],
             'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    files['EXPORT.json'] = (json.dumps(index, sort_keys=True, indent=2)+'\n').encode('utf-8')
    temporary = Path(tempfile.mkdtemp(prefix='checkpoint-', dir=root))
    try:
        for name, raw in files.items():
            p=temporary/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
        if target.exists():
            if any(not (target/name).is_file() or (target/name).read_bytes()!=raw for name,raw in files.items()):
                raise ValueError('Existing checkpoint export differs; do not overwrite')
            shutil.rmtree(temporary)
        else: os.rename(temporary, target)
        pointer=root/'LATEST.json'; pending=root/('LATEST.'+temporary.name+'.tmp')
        pending.write_text(json.dumps({'directory':target.name, **index}, sort_keys=True, indent=2)+'\n', encoding='utf-8')
        os.replace(pending, pointer)
        return target
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
