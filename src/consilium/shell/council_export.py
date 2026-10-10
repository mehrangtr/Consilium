"""Regenerable checkpoint exports, never a second operational state source."""
import hashlib
import json
import os
import re
import shutil
import tempfile
from html import escape
from pathlib import Path
from uuid import UUID, uuid4

from consilium.core.output_contract import import_snapshot, read_json, validate_snapshot

FORMAT_VERSION = 2


def participant_name(participant_id):
    """Canonical UUIDs are stable, portable and cannot inject filesystem paths."""
    return 'participant-' + str(UUID(participant_id))


def literal(text):
    # Fence untrusted model Markdown, including its own nested fences, so mixed
    # RTL/LTR technical content and headings cannot damage the report scaffold.
    longest = max((len(m.group()) for m in re.finditer(r'`+', text)), default=0)
    fence = '`' * max(3, longest+1)
    return fence+'text\n'+text+'\n'+fence+'\n'


def render(snapshot, *, format_version=FORMAT_VERSION):
    if format_version not in (1, 2):
        raise ValueError('Unsupported export format')
    validate_snapshot(snapshot)
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
        if format_version == 2:
            entry = '\nشناسهٔ مشارکت‌کننده: `'+pid+'`\n'+entry
        by_participant[pid].append(entry); main.append(entry)
    main.append('\n## تصمیم‌های کاربر\n\n')
    for row in snapshot['user_decisions']: main.append(literal(json.dumps(row, ensure_ascii=False, indent=2)))
    for analysis in snapshot['round_analyses']:
        main.append('\n## تحلیل دور\n\n'+literal(json.dumps(analysis, ensure_ascii=False, indent=2)))
    final = snapshot['final_council_result']
    if final:
        main.append('\n## نتیجهٔ نهایی و افشای داور\n\n'+literal(json.dumps(final, ensure_ascii=False, indent=2)))
    if format_version == 2:
        main.append('\n## دفتر عملیات و دادهٔ بازتولید\n\n'
                    '[تاریخچهٔ کامل ماشین، تلاش‌های ناقص و رویدادها](debate.json)\n\n'
                    '[نمایش مستقل فارسی و انگلیسی](debate.html)\n')
    files['debate.md'] = ('\n'.join(main)).encode('utf-8')
    for index, (pid, entries) in enumerate(by_participant.items()):
        name = 'participant-'+str(index+1) if format_version == 1 else participant_name(pid)
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
    if format_version == 2:
        files['debate.html'] = render_html(snapshot).encode('utf-8')
    return files


def render_html(snapshot):
    """Offline viewer. Untrusted text is escaped; no script or remote resources."""
    def section(title, text):
        return '<section><h2>'+escape(title)+'</h2><pre dir="auto">'+escape(text)+'</pre></section>'
    sections = [section('پرسش اصلی', snapshot['debate']['original_request'])]
    for row in snapshot['council_sources']:
        item = row['item']
        identity = item.get('participant_id', item.get('reviewer_id'))
        title = 'دور '+str(row['source_round']['number'])+' · '+row['source_round']['kind']
        body = item.get('content') or json.dumps(item, ensure_ascii=False, indent=2)
        sections.append('<section><h2>'+escape(title)+'</h2><p>شناسه: <code>'+escape(identity)+'</code></p>'
                        '<pre dir="auto">'+escape(body)+'</pre></section>')
    final = snapshot['final_council_result']
    if final:
        sections.append(section('نتیجهٔ نهایی', final['output']['conclusion']))
        sections.append(section('مخالفت‌ها و افشای مشارکت قبلی داور', json.dumps(final, ensure_ascii=False, indent=2)))
    return '''<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>گزارش شورا</title><style>
body{font-family:Tahoma,Arial,sans-serif;background:#f4f6f8;color:#172536;margin:0;padding:24px}
main{max-width:960px;margin:auto}section{background:white;padding:20px;margin:20px 0;border:1px solid #ccd5df;border-radius:10px}
h1,h2{line-height:1.7}h2{font-size:20px}pre{font:16px/1.9 Tahoma,Arial,sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;unicode-bidi:plaintext;text-align:start}
code{direction:ltr;unicode-bidi:isolate;display:inline-block;overflow-wrap:anywhere;max-width:100%}
</style><main><h1>تاریخچهٔ شورا</h1><p>توافق به معنی احتمال درستی نیست.</p>'''+''.join(sections)+'</main></html>'


def export_council(store, debate_id, destination: Path, *, checkpoint_hook=None):
    with store._transaction(write=False):
        snapshot = store.export_debate(debate_id)
        snapshot['council_sources'] = [{**s.model_dump(mode='json'), 'content_hash':s.content_hash}
                                       for s in store.sources.context_sources(debate_id)]
    return write_generation(snapshot, destination, checkpoint_hook=checkpoint_hook)


def synced_write(path, raw):
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def sync_directory(path):
    # Windows does not expose portable directory fsync. Process-exit recovery
    # is verified on both hosts; hardware/power-loss durability is not claimed.
    if os.name != 'nt':
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def write_generation(snapshot, destination, *, checkpoint_hook=None):
    files = render(snapshot)
    debate_id = snapshot['debate']['debate_id']
    root = destination.resolve()/str(debate_id)
    root.mkdir(parents=True, exist_ok=True)
    target = root/('revision-'+str(snapshot['checkpoint']['revision'])+'-format-'+str(FORMAT_VERSION))
    index = {'format_version': FORMAT_VERSION, 'debate_id': str(debate_id), 'revision': snapshot['checkpoint']['revision'],
             'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    files['EXPORT.json'] = (json.dumps(index, sort_keys=True, indent=2)+'\n').encode('utf-8')
    temporary = Path(tempfile.mkdtemp(prefix='checkpoint-', dir=root))
    try:
        for name, raw in files.items():
            p=temporary/name; p.parent.mkdir(parents=True, exist_ok=True); synced_write(p, raw)
            if checkpoint_hook: checkpoint_hook('after_file', name)
        if target.exists():
            if target.is_symlink():
                raise ValueError('Symlink generation cannot be reused')
            validate_generation(target)
            if any(not (target/name).is_file() or (target/name).read_bytes()!=raw for name,raw in files.items()):
                raise ValueError('Existing checkpoint export differs; do not overwrite')
            shutil.rmtree(temporary)
        else:
            for directory in temporary.rglob('*'):
                if directory.is_dir(): sync_directory(directory)
            sync_directory(temporary)
            os.rename(temporary, target)
            sync_directory(root)
        if checkpoint_hook: checkpoint_hook('after_generation', target.name)
        pointer=root/'LATEST.json'; pending=root/('LATEST.'+temporary.name+'.tmp')
        synced_write(pending, (json.dumps({'directory':target.name, **index}, sort_keys=True, indent=2)+'\n').encode('utf-8'))
        if checkpoint_hook: checkpoint_hook('before_pointer', target.name)
        os.replace(pending, pointer)
        sync_directory(root)
        if checkpoint_hook: checkpoint_hook('after_pointer', target.name)
        return target
    finally:
        if temporary.exists(): shutil.rmtree(temporary)


def validate_generation(directory):
    """Reject truncation, extra files, symlinks, tampering and render divergence."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Generation must be a real directory')
    if any(p.is_symlink() for p in directory.rglob('*')):
        raise ValueError('Symlink in generation')
    index = read_json((directory/'EXPORT.json').read_bytes())
    version = index.get('format_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError('Unsupported generation format')
    snapshot = validate_snapshot(read_json((directory/'debate.json').read_bytes()))
    files = render(snapshot, format_version=version)
    expected = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    actual_names = {str(p.relative_to(directory)).replace(os.sep, '/') for p in directory.rglob('*') if p.is_file()}
    if (index.get('files') != expected or actual_names != set(files) | {'EXPORT.json'}
            or any((directory/name).read_bytes() != raw for name, raw in files.items())
            or index.get('debate_id') != snapshot['debate']['debate_id']
            or type(index.get('revision')) is not int or index['revision'] != snapshot['checkpoint']['revision']):
        raise ValueError('Generation content/manifest mismatch')
    return index, snapshot


def recover_latest(root, *, confirmed=False):
    """Scan complete generations, ignoring partial temp dirs. Explicit repair."""
    if root.is_symlink():
        raise ValueError('Symlink export root')
    candidates = []
    for path in root.glob('revision-*'):
        try:
            index, snapshot = validate_generation(path)
            if index['debate_id'] != root.name: continue
            candidates.append((index['revision'], index.get('format_version', 1), path, index, snapshot))
        except (ValueError, OSError, KeyError, TypeError):
            continue
    if not candidates:
        raise ValueError('No complete valid generation')
    _, _, path, index, snapshot = max(candidates, key=lambda row: (row[0], row[1], row[2].name))
    if confirmed is True:
        pending = root/('LATEST.recovery-'+str(uuid4())+'.tmp')
        synced_write(pending, (json.dumps({'directory':path.name, **index}, sort_keys=True, indent=2)+'\n').encode())
        os.replace(pending, root/'LATEST.json')
        sync_directory(root)
    return path, snapshot


def import_output(source, destination, *, expected_sha256, confirmed=False):
    """Recover output into a separate immutable generation, not operational DB."""
    with source.open('rb') as handle:
        from consilium.core.output_contract import MAX_JSON_BYTES
        raw = handle.read(MAX_JSON_BYTES+1)
    snapshot = import_snapshot(raw, expected_sha256=expected_sha256, confirmed=confirmed)
    return write_generation(snapshot, destination)
