#!/usr/bin/env python3
"""Record exact manual observations and export blinded pilot material."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from consilium.core.pilot import PilotCall, summarize
from consilium.shell.pilot import PilotJournal
from consilium.shell.private import ensure_public_payload, redact_diagnostic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('status', 'prepare', 'import', 'blind'))
    parser.add_argument('--workspace', type=Path, required=True, help='Private pilot workspace outside source checkout')
    parser.add_argument('--record', type=Path)
    parser.add_argument('--prompt', type=Path)
    parser.add_argument('--response', type=Path)
    parser.add_argument('--confirmed-manual-origin', action='store_true')
    args = parser.parse_args()
    if args.workspace.resolve().is_relative_to(ROOT):
        parser.error('Pilot workspace must remain outside the source checkout')
    plan = json.loads((ROOT / 'docs/p06/PREREGISTRATION.json').read_text())
    workspace = args.workspace.resolve(); workspace.mkdir(parents=True, exist_ok=True)
    journal = PilotJournal(workspace, tuple(plan['task_ids']), plan['max_calls_per_task_method'])
    objects = journal.objects
    if args.command == 'prepare':
        dataset_path = ROOT / plan['dataset']
        if hashlib.sha256(dataset_path.read_bytes()).hexdigest() != plan['dataset_sha256']:
            parser.error('Preregistered dataset bytes have changed')
        dataset = json.loads(dataset_path.read_text())
        # Reference answers are withheld from generation prompts.
        tasks = [{'task_id': t['task_id'], 'prompt': t['prompt']} for t in dataset['tasks'] if t['task_id'] in plan['task_ids']]
        target = workspace / 'GENERATION_TASKS.json'
        with target.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(tasks, ensure_ascii=False, indent=2) + '\n')
    if args.command == 'import':
        if not args.confirmed_manual_origin or not all((args.record, args.prompt, args.response)):
            parser.error('Explicit manual origin confirmation, observation, prompt and response files are required')
        raw = json.loads(args.record.read_text())
        ensure_public_payload(raw, ())
        call = PilotCall(**raw)
        if call.origin != 'MANUAL':
            parser.error('This importer only accepts explicitly claimed real manual output')
        for path, expected in ((args.prompt, call.prompt_sha256), (args.response, call.response_sha256)):
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                parser.error('Input bytes differ from the observation digest')
        journal.append(call, args.prompt.read_bytes(), args.response.read_bytes())
    calls = journal.calls()
    report = summarize(calls, tuple(plan['task_ids']), plan['max_calls_per_task_method'])
    if args.command == 'blind':
        if report['status'] != 'READY_FOR_BLINDED_REVIEW':
            parser.error('All real protocol calls must be recorded before blind scoring')
        finals = [c for c in calls if c.final and c.origin == 'MANUAL']
        finals.sort(key=lambda c: hashlib.sha256((plan['blinding_seed'] + c.task_id + c.method).encode()).hexdigest())
        projected = [{'blind_id': f'BLIND-{i:03}', 'task_id': c.task_id,
            'response_sha256': c.response_sha256, 'response': objects.read(c.response_sha256).decode('utf-8')}
            for i, c in enumerate(finals, 1)]
        mapping = {f'BLIND-{i:03}': {'call_id': c.call_id, 'method': c.method, 'provider': c.provider}
                   for i, c in enumerate(finals, 1)}
        (workspace / 'BLINDED.json').write_text(json.dumps(projected, ensure_ascii=False, indent=2) + '\n')
        (workspace / 'PRIVATE_BLIND_MAP.json').write_text(json.dumps(mapping, indent=2) + '\n')
    print(json.dumps(redact_diagnostic(report), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
