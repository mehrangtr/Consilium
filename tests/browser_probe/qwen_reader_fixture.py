"""Private synthetic reader commands, including an actual owned descendant."""

import subprocess
import sys
import time
from pathlib import Path

mode, path = sys.argv[1:]
if mode == "success":
    sys.stdout.buffer.write(Path(path).read_bytes())
elif mode == "failure":
    print("sensitive-marker", file=sys.stderr)
    raise SystemExit(23)
elif mode == "flood":
    sys.stdout.buffer.write(b"x" * (4 * 1048576))
    sys.stdout.buffer.flush()
elif mode == "child":
    while True:
        with Path(path).open("ab") as file:
            file.write(b".")
        time.sleep(0.03)
elif mode == "hang":
    subprocess.Popen([sys.executable, __file__, "child", path])
    while True:
        time.sleep(0.05)
