#!/usr/bin/env python3
"""Explicit offline council commands, with durable state and checkpoint exports."""
import argparse
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from consilium.adapters.mock import MockAdapter
from consilium.core.contracts import ConnectionSpec, DebateSpec, OperationIdentity, UserDecision
from consilium.shell.council_export import export_council
from consilium.shell.storage import SQLiteStore


def read(path):
    if path.stat().st_size > 1048576:
        raise ValueError('Input exceeds local byte limit')
    return path.read_text(encoding='utf-8')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--debate-id', type=UUID, required=True)
    p.add_argument('--revision', type=int)
    p.add_argument('--exports', type=Path)
    p.add_argument('--actor')
    p.add_argument('--confirm-user-action', action='store_true')
    commands = p.add_subparsers(dest='command', required=True)
    new = commands.add_parser('new')
    new.add_argument('--config', type=Path, required=True)
    commands.add_parser('status')
    start = commands.add_parser('start')
    start.add_argument('--kind', choices=('INDEPENDENT','REVIEW','TARGETED'), required=True)
    start.add_argument('--target', action='append', default=[])
    start.add_argument('--participant', action='append', type=UUID)
    commands.add_parser('seal')
    decide = commands.add_parser('decide')
    decide.add_argument('--choice', choices=('CONTINUE','CUSTOM','PAUSE','FINISH'), required=True)
    decide.add_argument('--instruction')
    judge = commands.add_parser('judge')
    judge.add_argument('--participant-id', type=UUID, required=True)
    commands.add_parser('resume-pause')
    commands.add_parser('finalize')
    commands.add_parser('export')
    context = commands.add_parser('manual-context')
    context.add_argument('--participant-id', type=UUID, required=True)
    mock = commands.add_parser('mock-answer')
    mock.add_argument('--participant-id', type=UUID, required=True)
    mock.add_argument('--response-file', type=Path, required=True)
    args = p.parse_args(argv)
    database = args.database.resolve()
    if args.database.is_symlink() or database.is_relative_to(ROOT):
        raise ValueError('Use a private database outside the source checkout')
    if args.command != 'new' and not database.is_file():
        raise ValueError('Existing database required; no implicit new debate')
    if args.command not in {'status','export','manual-context'}:
        if args.exports is None or args.revision is None:
            raise ValueError('Mutations require a revision and checkpoint export destination')
        from consilium.shell.council import Council
        Council._explicit(args.actor, args.confirm_user_action)
    if args.exports is not None and args.exports.resolve().is_relative_to(ROOT):
        raise ValueError('Keep debate exports outside the source checkout')
    if args.command == 'new':
        if args.revision != 0:
            raise ValueError('New debate begins at revision zero')
        config = json.loads(read(args.config))
        debate = DebateSpec.model_validate_json(json.dumps(config['debate']))
        bindings = [(UUID(row['participant_id']), ConnectionSpec.model_validate_json(json.dumps(row['connection'])))
                    for row in config['bindings']]
        if debate.debate_id != args.debate_id or len(debate.participant_ids) < 2 or {pid for pid,_ in bindings} != set(debate.participant_ids) or len(bindings) != len(debate.participant_ids):
            raise ValueError('Config must bind every council participant exactly once')
    with SQLiteStore(database, require_new=args.command=='new') as store:
        c = store.council
        common = dict(debate_id=args.debate_id, expected_revision=args.revision)
        explicit = dict(user_action_id=uuid4(), actor=args.actor, confirmed=args.confirm_user_action)
        output = None
        if args.command == 'new':
            store.create_debate(debate)
            for pid, connection in bindings:
                store.bind_connection(debate.debate_id, pid, connection,
                    expected_revision=c.revision(debate.debate_id), expected_connection_revision=None)
            output = {'next_action':'ARCHITECT_STAGE_AND_USER_REVIEW_BEFORE_INDEPENDENT_ROUND'}
        elif args.command == 'status':
            output = c.recover(args.debate_id)
        elif args.command == 'start':
            output = c.start_round(**common, round_id=uuid4(), kind=args.kind, targets=tuple(args.target),
                                   participant_ids=None if args.participant is None else tuple(args.participant)).model_dump(mode='json')
        elif args.command == 'seal':
            output = c.seal_round(**common).model_dump(mode='json')
        elif args.command == 'decide':
            current = c.current_round(args.debate_id)
            if current is None: raise ValueError('No current round')
            decision = UserDecision(decision_id=explicit['user_action_id'], debate_id=args.debate_id,
                round_id=current.round_id, expected_revision=args.revision, kind=args.choice, instruction=args.instruction)
            output = c.decide(decision, actor=args.actor, confirmed=args.confirm_user_action).model_dump(mode='json')
        elif args.command == 'judge':
            output = c.select_judge(**common, **explicit, participant_id=args.participant_id, round_id=uuid4()).model_dump(mode='json')
        elif args.command == 'resume-pause':
            output = c.resume_pause(**common, **explicit).model_dump(mode='json')
        elif args.command == 'finalize':
            output = c.finalize(**common).model_dump(mode='json')
        elif args.command == 'manual-context':
            c.store._checked_debate(args.debate_id, args.revision)
            spec = c.current_round(args.debate_id)
            if spec is None: raise ValueError('No active round')
            connection,_ = c.binding(args.debate_id, args.participant_id)
            if connection.mode != 'MANUAL': raise ValueError('Explicit manual binding required')
            if spec.kind == 'INDEPENDENT':
                output = {'expected_prompt':store.manual_sources._expected_prompt(spec,args.participant_id),
                          'round_spec':spec.model_dump(mode='json')}
            else:
                c._explicit(args.actor,args.confirm_user_action)
                frame = store.manual_rounds.prepare_context(debate_id=args.debate_id,round_id=spec.round_id,
                    participant_id=args.participant_id,expected_revision=args.revision,
                    grants=c.grants(spec,args.participant_id,args.revision,uuid4()))
                output = {'frame':frame.model_dump(mode='json'), 'expected_prompt':frame.expected_prompt,
                          'targets':[t.model_dump(mode='json') for t in frame.targets]}
        elif args.command == 'mock-answer':
            response = read(args.response_file)
            request = c.prepare_mock(**common, **explicit, participant_id=args.participant_id,
                identity=OperationIdentity(logical_operation_id=uuid4(),attempt_id=uuid4()))
            output = c.execute_mock(request,MockAdapter(response_content=response),
                expected_revision=c.revision(args.debate_id)).model_dump(mode='json')
        if args.exports is not None:
            destination = export_council(store,args.debate_id,args.exports)
        elif args.command == 'export':
            raise ValueError('Export destination required')
        else: destination = None
        report = {'project':'Consilium','phase':'P05','scope':'OFFLINE_COUNCIL_COMMAND',
                  'provider_calls':0,'checkpoint':store.checkpoint(args.debate_id).model_dump(mode='json'),
                  'result':output,'export_directory':str(destination) if destination else None}
        store._public(report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,KeyError,TypeError):
        print(json.dumps({'phase':'P05','status':'REJECTED','reason':'LOCAL_COUNCIL_STATE_OR_INPUT_REJECTED',
                          'provider_calls':0,'phase_accepted':False}))
        raise SystemExit(1)
