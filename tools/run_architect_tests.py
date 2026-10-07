#!/usr/bin/env python3
"""P04 architect slice tests with fresh JUnit; not full phase acceptance."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import platform
import sys
import unittest
import xml.etree.ElementTree as ET

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []
        self.current = None

    def startTest(self, test):
        super().startTest(test)
        self.current = {"id": test.id(), "kind": None, "details": []}

    def _record(self, kind, message):
        self.current["kind"] = self.current["kind"] or kind
        self.current["details"].append(message)

    def addError(self, test, err):
        super().addError(test, err)
        self._record("error", self._exc_info_to_string(err, test))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record("failure", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record("skipped", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record("failure", "Expected failure is not accepted")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record("failure", "Unexpected success")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            kind = "failure" if issubclass(err[0], test.failureException) else "error"
            self._record(kind, self._exc_info_to_string(err, subtest))

    def stopTest(self, test):
        self.rows.append(self.current)
        super().stopTest(test)


def main():
    before = q.source_digest(ROOT)
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests/architect")]
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests/architect"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    counts = {"tests": len(result.rows), **{field: sum(x["kind"] == kind for x in result.rows)
              for field, kind in [("failures", "failure"), ("errors", "error"), ("skipped", "skipped")]}}
    after = q.source_digest(ROOT)
    passed = result.wasSuccessful() and counts["tests"] > 0 and before == after and not any(
        counts[x] for x in ("failures", "errors", "skipped")) and not result.expectedFailures
    report = {"phase": "P04", "scope": "P04_QUESTION_CONTEXT_AND_POLICY_OFFLINE_NOT_FULL_PHASE_ACCEPTANCE",
              "status": "PASS" if passed else "FAIL", "counts": counts,
              "source_digest_before": before, "source_digest_after": after,
              "date_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "host": {"system": platform.system(), "python": platform.python_version()},
              "windows_execution": "NOT_RUN" if platform.system() != "Windows" else "THIS_RUN",
              "live_provider_calls": 0, "verified_application_requirements": 0,
              "cases": [{"id": x["id"], "status": x["kind"].upper() if x["kind"] else "PASS"}
                        for x in result.rows]}
    folder = ROOT / "evidence/architect-tests"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "RUN.json").write_bytes(q.encoded(report))
    xml = ET.Element("testsuite", **{k: str(v) for k, v in counts.items()})
    for row in result.rows:
        case = ET.SubElement(xml, "testcase", name=row["id"])
        if row["kind"]:
            ET.SubElement(case, row["kind"]).text = "\n".join(row["details"])
    ET.ElementTree(xml).write(folder / "JUNIT.xml", encoding="utf-8", xml_declaration=True)
    print(json.dumps({k: report[k] for k in ("phase", "scope", "status", "counts")}))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
