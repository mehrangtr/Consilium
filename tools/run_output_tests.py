#!/usr/bin/env python3
"""P07 output/import/recovery tests with independent fresh JUnit."""
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


from run_architect_tests import RecordingResult


def main():
    before = q.source_digest(ROOT)
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests/council")]
    suite = unittest.defaultTestLoader.loadTestsFromName('test_output')
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    counts = {"tests": len(result.rows), **{field: sum(x["kind"] == kind for x in result.rows)
              for field, kind in [("failures", "failure"), ("errors", "error"), ("skipped", "skipped")]}}
    after = q.source_digest(ROOT)
    passed = result.wasSuccessful() and counts["tests"] > 0 and before == after and not any(
        counts[x] for x in ("failures", "errors", "skipped")) and not result.expectedFailures
    report = {"phase": "P07", "scope": "P07_OUTPUT_IMPORT_PROCESS_EXIT_RECOVERY",
              "status": "PASS" if passed else "FAIL", "counts": counts,
              "source_digest_before": before, "source_digest_after": after,
              "date_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "host": {"system": platform.system(), "python": platform.python_version()},
              "windows_execution": "NOT_RUN" if platform.system() != "Windows" else "THIS_RUN",
              "real_process_exit_cases": sum("test_real_exit_" in x["id"] for x in result.rows),
              "manual_origin": "USER_ACCEPTED_SYNTHETIC_FIXTURES_NOT_AUTHENTICATED_EXTERNAL_GENERATION",
              "live_provider_calls": 0, "verified_application_requirements": 0,
              "cases": [{"id": x["id"], "status": x["kind"].upper() if x["kind"] else "PASS"}
                        for x in result.rows]}
    folder = ROOT / "evidence/output-tests"
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
