"""Convert three private recorded files to a packet; never acquire or send live."""

import os
import stat
import sys

from consilium.adapters.qwen_page_reader import (
    MAX_CAPTURE_BYTES,
    _require_bounded_depth,
    _unique_object,
)
from consilium.adapters.qwen_process_reader import encode_reader_output
from consilium.core.browser_probe import BrowserContext
from consilium.shell.qwen_capture_ingest import QwenCaptureRead

MAX_CONTEXT_BYTES = 65536


def bounded_file(path, limit):
    invalid = False
    try:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise ValueError("size or type")
            raw = stream.read(limit + 1)
            if not raw or len(raw) > limit:
                raise ValueError("size")
    except (OSError, ValueError, TypeError):
        invalid = True
    if invalid:
        raise ValueError("QWEN_SAVED_INPUT_INVALID")
    return raw


def context_file(path):
    import json

    raw = bounded_file(path, MAX_CONTEXT_BYTES)
    _require_bounded_depth(raw)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    return BrowserContext.model_validate_json(json.dumps(value, allow_nan=False))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3:
        print("QWEN_SAVED_READ_REQUIRES_BEFORE_CAPTURE_AFTER", file=sys.stderr)
        return 2
    invalid = False
    try:
        before = context_file(argv[0])
        raw = bounded_file(argv[1], MAX_CAPTURE_BYTES)
        after = context_file(argv[2])
        result = encode_reader_output(QwenCaptureRead(before, raw, after))
    except (OSError, ValueError, TypeError, UnicodeError):
        invalid = True
    if invalid:
        print("QWEN_SAVED_READ_INVALID", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
