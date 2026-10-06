"""Actual Git roundtrip must preserve immutable native evidence bytes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GitEvidencePreservation(unittest.TestCase):
    def test_native_evidence_survives_git_staging_and_checkout_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"
            root.mkdir()
            def git(*args):
                return subprocess.run(["git", "-c", "core.autocrlf=true", "-c", "core.safecrlf=false",
                                       "-c", "core.attributesfile=", "-C", str(root), *args],
                                      stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=10).stdout
            git("init")
            (root / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
            raw = "synthetic evidence؛ آزمون\r\nsecond line\r\n".encode("utf-8")
            for name in ("CHECK.log", "JUNIT.xml"):
                path = root / "evidence/synthetic" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            git("add", ".")
            for name in ("CHECK.log", "JUNIT.xml"):
                self.assertEqual(git("show", ":evidence/synthetic/" + name), raw)
            exported = Path(folder) / "checkout"
            exported.mkdir()
            git("checkout-index", "--all", "--prefix=" + exported.as_posix() + "/")
            for name in ("CHECK.log", "JUNIT.xml"):
                self.assertEqual((exported / "evidence/synthetic" / name).read_bytes(), raw)
