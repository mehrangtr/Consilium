"""Export identity and immutable legacy generations; no live provider claims."""
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import test_council as fixtures

from consilium.core.output_contract import import_snapshot, read_json
from consilium.shell.council_export import (
    export_council,
    import_output,
    recover_latest,
    render,
    validate_generation,
)


class OutputCase(fixtures.CouncilCase):
    # Reuse the complete flow fixture without inheriting the entire test suite.
    def test_stable_identity_survives_reordered_participants(self):
        self.through_review()
        self.finish()
        out = export_council(self.store, self.debate.debate_id, Path(self.temp.name)/'export')
        snapshot = json.loads((out/'debate.json').read_text())
        reordered = copy.deepcopy(snapshot)
        reordered['debate']['participant_ids'].reverse()
        first, second = render(snapshot), render(reordered)
        for prefix in ('participants/', 'assessments/'):
            names = [name for name in first if name.startswith(prefix)]
            self.assertEqual(len(names), 2)
            for name in names:
                self.assertEqual(first[name], second[name])
                self.assertIn(name.split('participant-')[1][:-3].encode(), first[name])

    def test_legacy_generation_not_overwritten_at_same_revision(self):
        self.through_review()
        destination = Path(self.temp.name)/'export'
        new = export_council(self.store, self.debate.debate_id, destination)
        snapshot = json.loads((new/'debate.json').read_text())
        old = new.parent/('revision-'+str(snapshot['checkpoint']['revision']))
        old.mkdir()
        for name, data in render(snapshot, format_version=1).items():
            path = old/name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
        before = {str(p.relative_to(old)): p.read_bytes() for p in old.rglob('*') if p.is_file()}
        self.assertEqual(export_council(self.store, self.debate.debate_id, destination), new)
        self.assertEqual(before, {str(p.relative_to(old)): p.read_bytes() for p in old.rglob('*') if p.is_file()})

    def final_export(self):
        self.through_review()
        self.finish()
        return export_council(self.store, self.debate.debate_id, Path(self.temp.name)/'export')

    def test_json_import_requires_confirmed_exact_hash_without_db_mutation(self):
        out = self.final_export()
        source = out/'debate.json'
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        before = self.store.export_debate(self.debate.debate_id)
        for confirmed, expected in ((False, digest), (True, '0'*64)):
            with self.assertRaises(ValueError):
                import_output(source, Path(self.temp.name)/'recovered', expected_sha256=expected, confirmed=confirmed)
        imported = import_output(source, Path(self.temp.name)/'recovered', expected_sha256=digest, confirmed=True)
        self.assertEqual(validate_generation(imported)[1], read_json(raw))
        self.assertEqual(before, self.store.export_debate(self.debate.debate_id))

    def test_import_rejects_invalid_versions_references_and_completion(self):
        snapshot = read_json((self.final_export()/'debate.json').read_bytes())
        cases = []
        for key, value in (('schema_version', True), ('schema_version', 99), ('debate_completed', False)):
            changed = copy.deepcopy(snapshot)
            changed[key] = value
            cases.append(changed)
        changed = copy.deepcopy(snapshot)
        changed['council_sources'][0]['item']['content'] = 'tampered'
        cases.append(changed)
        changed = copy.deepcopy(snapshot)
        changed['checkpoint']['debate_id'] = str(self.pid[0])
        cases.append(changed)
        changed = copy.deepcopy(snapshot)
        changed['final_council_result']['judge_source_hash'] = '0'*64
        cases.append(changed)
        for changed in cases:
            raw = json.dumps(changed).encode()
            with self.assertRaises(ValueError):
                import_snapshot(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), confirmed=True)
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff', b'['*2000):
            with self.assertRaises(ValueError): read_json(raw)

    def test_generation_rejects_extra_files_tampering_and_unsupported_format(self):
        out = self.final_export()
        extra = out/'extra.txt'
        extra.write_text('unexpected')
        with self.assertRaises(ValueError): validate_generation(out)
        with self.assertRaises(ValueError):
            export_council(self.store, self.debate.debate_id, out.parent.parent)
        extra.unlink()
        main = out/'debate.md'
        original = main.read_bytes()
        main.write_bytes(b'truncated')
        with self.assertRaises(ValueError): validate_generation(out)
        main.write_bytes(original)
        index = read_json((out/'EXPORT.json').read_bytes())
        index['format_version'] = True
        (out/'EXPORT.json').write_text(json.dumps(index))
        with self.assertRaises(ValueError): validate_generation(out)

    def test_html_escapes_untrusted_code_and_links_without_scripts(self):
        snapshot = read_json((self.final_export()/'debate.json').read_bytes())
        snapshot['debate']['original_request'] = '<script>alert(1)</script> فارسی C:\\project\\file.py\n[link](javascript:alert(1))'
        html = render(snapshot)['debate.html'].decode()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('unicode-bidi:plaintext', html)
        self.assertIn('dir="auto"', html)
        self.assertNotIn('<a ', html)

    def test_real_process_exits_during_export_keep_recoverable_complete_generation(self):
        self.through_review()
        destination = Path(self.temp.name)/'export'
        early = export_council(self.store, self.debate.debate_id, destination)
        old = {str(p.relative_to(early)): p.read_bytes() for p in early.rglob('*') if p.is_file()}
        self.finish()
        final = export_council(self.store, self.debate.debate_id, Path(self.temp.name)/'fixture')
        root = early.parent
        for boundary in ('after_file', 'after_generation', 'before_pointer', 'after_pointer'):
            # Each subprocess has its own output root with the complete prior generation.
            import shutil
            target = Path(self.temp.name)/boundary
            shutil.copytree(destination, target)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('output_crash_worker.py')),
                                     str(final/'debate.json'), str(target), boundary],
                                    env=dict(os.environ, PYTHONPATH=str(fixtures.ROOT/'src')),
                                    capture_output=True, timeout=15, check=False)
            self.assertEqual(result.returncode, 85, result.stderr.decode())
            recovered, snapshot = recover_latest(target/root.name, confirmed=True)
            self.assertEqual(snapshot['debate_completed'], boundary != 'after_file')
            self.assertEqual(json.loads((target/root.name/'LATEST.json').read_text())['directory'], recovered.name)
            self.assertEqual(old, {str(p.relative_to(target/root.name/early.name)):p.read_bytes()
                                  for p in (target/root.name/early.name).rglob('*') if p.is_file()})
            repaired = export_council(self.store, self.debate.debate_id, target)
            self.assertTrue(validate_generation(repaired)[1]['debate_completed'])

    def test_recovery_ignores_newest_invalid_generation_and_broken_pointer(self):
        self.through_review()
        destination = Path(self.temp.name)/'export'
        early = export_council(self.store, self.debate.debate_id, destination)
        self.finish()
        final = export_council(self.store, self.debate.debate_id, destination)
        (final/'debate.md').write_bytes(b'incomplete')
        (final.parent/'LATEST.json').write_text('{')
        recovered, snapshot = recover_latest(final.parent, confirmed=True)
        self.assertEqual(recovered, early)
        self.assertFalse(snapshot['debate_completed'])


# unittest otherwise repeats every inherited CouncilCase test in this subclass.
for _name in tuple(vars(fixtures.CouncilCase)):
    if _name.startswith('test_') and _name not in vars(OutputCase):
        setattr(OutputCase, _name, None)
