#!/usr/bin/env python3
"""Offline manual context, answer/critique entry and explicit local review."""
import argparse
import json
from pathlib import Path
import sys
from uuid import UUID
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from consilium.core.manual_rounds import ManualRoundFrame, ManualRoundSubmission
from consilium.core.round_context import TransferGrant
from consilium.shell.manual_round_review import review_manual_round
from consilium.shell.manual_entry import collect_manual_text
from consilium.shell.architect_review import _display
from consilium.shell.storage import SQLiteStore

def read_file(path, limit=4194304):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError('Manual file exceeds local byte limit')
    return path.read_bytes()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--revision', type=int, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    context = commands.add_parser('context')
    for name in ('debate-id', 'round-id', 'participant-id'):
        context.add_argument('--' + name, type=UUID, required=True)
    context.add_argument('--grants', type=Path, required=True)
    stage = commands.add_parser('stage')
    stage.add_argument('--context-file', required=True)
    stage.add_argument('--submission', required=True)
    enter = commands.add_parser('enter')
    enter.add_argument('--context-file', required=True)
    enter.add_argument('--candidate-id', type=UUID, required=True)
    enter.add_argument('--actual-prompt-file', required=True)
    enter.add_argument('--round-seen', action='store_true')
    enter.add_argument('--claimed-origin')
    review = commands.add_parser('review')
    review.add_argument('--candidate-id', type=UUID, required=True)
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file() or database.is_relative_to(ROOT):
        raise ValueError('Use an existing local database outside source')
    with SQLiteStore(database) as store:
        if args.command == 'context':
            grants = tuple((TransferGrant.model_validate_json(json.dumps(g)) for g in json.loads(read_file(args.grants))))
            frame = store.manual_rounds.prepare_context(debate_id=args.debate_id, round_id=args.round_id, participant_id=args.participant_id, expected_revision=args.revision, grants=grants)
            output = {'status': 'LOCAL_CONTEXT_NOT_SEND_AUTHORITY', 'frame': frame.model_dump(mode='json'), 'expected_prompt': frame.expected_prompt, 'targets': [t.model_dump(mode='json') for t in frame.targets], 'provider_calls': 0, 'phase_accepted': False}
        elif args.command in {'stage', 'enter'}:
            raw = json.loads(read_file(args.context_file))
            frame = ManualRoundFrame.model_validate_json(json.dumps(raw.get('frame', raw)))
            if args.command == 'stage':
                submission = ManualRoundSubmission.model_validate_json(read_file(args.submission, 1048576))
            else:
                print(_display({'participant_id': str(frame.participant_id), 'round': frame.round_spec.number, 'claimed_service': frame.connection.provider_id, 'provenance': 'MANUAL', 'external_origin_verified': False, 'expected_prompt': frame.expected_prompt, 'targets': [t.model_dump(mode='json') for t in frame.targets]}))
                content = collect_manual_text(args.candidate_id, read_line=input, write=print)
                if content is None:
                    print(json.dumps({'status': 'CANCELLED_NOT_STAGED', 'provider_calls': 0, 'phase_accepted': False}))
                    return 0
                submission = ManualRoundSubmission(schema_version=1, candidate_id=args.candidate_id, actual_prompt=read_file(args.actual_prompt_file, 1048576).decode('utf-8'), round_seen=args.round_seen, content=content, claimed_origin=args.claimed_origin)
            candidate = store.manual_rounds.stage(frame=frame, expected_revision=args.revision, **submission.model_dump(mode='python', exclude={'schema_version'}))
            output = {'status': 'STAGED_NOT_ACCEPTED', 'candidate_id': str(candidate.candidate_id), 'candidate_hash': candidate.content_hash, 'alignment': candidate.alignment, 'provider_calls': 0, 'phase_accepted': False}
        else:
            output = review_manual_round(store, args.candidate_id, expected_revision=args.revision, read_line=input, write=print)
    print(json.dumps(output, ensure_ascii=False))
    return 0
if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RecursionError):
        print(json.dumps({'status': 'REJECTED', 'error': 'LOCAL_MANUAL_ROUND_STATE_OR_INPUT_REJECTED', 'provider_calls': 0, 'phase_accepted': False}))
        raise SystemExit(1)
