"""Consilium's early local CLI. Live provider operations are not enabled here."""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog='python -m consilium')
    commands = parser.add_subparsers(dest='command', required=True)
    demo = commands.add_parser('demo', help='Run a synthetic offline council')
    demo.add_argument('--scripted', action='store_true', help='Explicitly authorize prewritten DEMO decisions')
    demo.add_argument('--output', type=Path, help='New output directory; existing directories are rejected')
    args = parser.parse_args()
    if args.command == 'demo':
        if not args.scripted and not sys.stdin.isatty():
            parser.error('Interactive demo needs a terminal; use --scripted to authorize the synthetic decisions')
        from consilium.shell.demo import run_demo
        try:
            print(json.dumps(run_demo(args.output, scripted=args.scripted), ensure_ascii=False, indent=2))
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
