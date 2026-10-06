#!/usr/bin/env python3
"""Run control-tool tests with actual JUnit counts, not application acceptance."""
import datetime
import hashlib
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

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append((test.id(), None, ""))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.rows.append((test.id(), "failure", self._exc_info_to_string(err, test)))

    def addError(self, test, err):
        super().addError(test, err)
        self.rows.append((test.id(), "error", self._exc_info_to_string(err, test)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.rows.append((test.id(), "skipped", reason))

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.rows.append((test.id(), "skipped", "Expected failure is not accepted"))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.rows.append((test.id(), "failure", "Unexpected success"))


def main():
    inputs = [ROOT / "tools/qualityctl.py", Path(__file__).resolve(),
              ROOT / "tools/check.py",
              ROOT / "tools/check_target_matrix.py", ROOT / "tools/record_target_checks.py",
              ROOT / "ROADMAP.json", ROOT / "PROGRESS.json",
              ROOT / "baseline/Consilium_User_Guarded_Governance_v1.3_Reviewed.zip"]
    inputs += sorted((ROOT / "tests").glob("test_*.py"))
    def snapshot():
        return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in inputs}
    before = snapshot()
    source_before = q.source_digest(ROOT)
    sys.path.insert(0, str(ROOT / "tests"))
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(path.stem)
                               for path in sorted((ROOT / "tests").glob("test_*.py")))
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    folder = ROOT / "evidence" / "control-tests"
    folder.mkdir(parents=True, exist_ok=True)
    counts = {"tests": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": len(result.skipped),
              "expected_failures": len(result.expectedFailures),
              "unexpected_successes": len(result.unexpectedSuccesses)}
    after = snapshot()
    source_after = q.source_digest(ROOT)
    passed = before == after and source_before == source_after and result.wasSuccessful() and result.testsRun > 0 and not any(
        counts[k] for k in ("skipped", "expected_failures", "unexpected_successes"))
    report = {"scope": "DEVELOPMENT_CONTROL_TOOLING_ONLY",
              "application_runtime_tests": "NOT_RUN", "verified_application_requirements": 0,
              "status": "PASS" if passed else "FAIL", "counts": counts,
              "python": sys.version, "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "platform": platform.platform(), "source_files_before": before,
              "host": {"system": platform.system(), "python": platform.python_version()},
              "source_digest_before": source_before, "source_digest_after": source_after,
              "source_files_after": after, "source_unchanged": before == after,
              "cases": [{"id": name, "status": "PASS" if not kind else kind.upper()}
                        for name, kind, _ in result.rows]}
    (folder / "RUN.json").write_bytes(q.encoded(report))
    xml = ET.Element("testsuite", tests=str(result.testsRun), failures=str(len(result.failures)),
                     errors=str(len(result.errors)), skipped=str(len(result.skipped)))
    for name, kind, message in result.rows:
        case = ET.SubElement(xml, "testcase", name=name)
        if kind:
            ET.SubElement(case, kind).text = message
    ET.ElementTree(xml).write(folder / "JUNIT.xml", encoding="utf-8", xml_declaration=True)
    print(json.dumps({k: report[k] for k in ("scope", "status", "counts")}))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
