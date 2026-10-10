"""Abrupt real process exits at export filesystem boundaries."""
import json
import os
import sys
from pathlib import Path

from consilium.shell.council_export import write_generation

snapshot_path, destination, boundary = sys.argv[1:]


def crash(stage, name):
    if stage == boundary:
        os._exit(85)


write_generation(json.loads(Path(snapshot_path).read_text(encoding='utf-8')),
                 Path(destination), checkpoint_hook=crash)
raise SystemExit('Expected boundary not reached')
