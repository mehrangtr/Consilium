#!/usr/bin/env python3
"""Execute P02 storage/dispatch/resume, including actual child-process exits."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import platform
import sqlite3
import sys
import unittest
import xml.etree.ElementTree as ET

import qualityctl as q
from run_foundation_tests import RecordingResult

ROOT = Path(__file__).resolve().parents[1]


def main():
    before = q.source_digest(ROOT)
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests/persistence")]
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests/persistence"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    counts = {"tests": len(result.rows), **{field: sum(x["kind"] == kind for x in result.rows)
              for field, kind in [("failures", "failure"), ("errors", "error"), ("skipped", "skipped")]}}
    after = q.source_digest(ROOT)
    passed = result.wasSuccessful() and counts["tests"] > 0 and before == after and not any(
        counts[x] for x in ("failures", "errors", "skipped")) and not result.expectedFailures
    process_cases = [x["id"] for x in result.rows if ".test_actual_process_exit_" in x["id"] or ".test_process_exit_" in x["id"]]
    report = {"phase": "P02", "scope": "P02_DURABILITY_OFFLINE_NOT_FULL_V1_ACCEPTANCE",
              "status": "PASS" if passed else "FAIL", "counts": counts,
              "source_digest_before": before, "source_digest_after": after,
              "date_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "host": {"system": platform.system(), "python": platform.python_version(),
                       "sqlite": sqlite3.sqlite_version},
              "live_provider_calls": 0, "phase_accepted": False,
              "process_exit_cases": process_cases, "process_exit_case_count": len(process_cases),
              "external_transport": "MOCK_ONLY_SIMULATED_RECEIPTS_NOT_LIVE_PROVIDER_PROOF",
              "cases": [{"id": x["id"], "status": x["kind"].upper() if x["kind"] else "PASS"}
                        for x in result.rows]}
    folder = ROOT / "evidence/persistence-tests"
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
