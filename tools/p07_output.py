#!/usr/bin/env python3
"""Explicit, local export validation/recovery; no model or operational dispatch."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from consilium.shell.council_export import (
    import_output,
    recover_latest,
    validate_generation,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('validate')
    check.add_argument('generation', type=Path)
    recover = commands.add_parser('recover')
    recover.add_argument('root', type=Path)
    recover.add_argument('--confirm', action='store_true')
    load = commands.add_parser('import')
    load.add_argument('source', type=Path)
    load.add_argument('destination', type=Path)
    load.add_argument('--sha256', required=True)
    load.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'validate':
            index, _ = validate_generation(args.generation)
            result = {'status':'PASS', 'revision':index['revision']}
        elif args.command == 'recover':
            path, _ = recover_latest(args.root, confirmed=args.confirm)
            result = {'status':'PASS', 'generation':str(path), 'pointer_repaired':args.confirm}
        else:
            path = import_output(args.source, args.destination, expected_sha256=args.sha256, confirmed=args.confirm)
            result = {'status':'PASS', 'generation':str(path), 'operational_database_changed':False}
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'status':'REJECTED', 'reason':'Invalid or unconfirmed output; original state preserved'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
