#!/usr/bin/env python3
"""Local stage evidence and portable snapshots; not a proof of application correctness."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import uuid
import zipfile
import xml.etree.ElementTree as ET


class Blocked(ValueError):
    pass


MUTABLE = {"PROGRESS.json", "MANIFEST.json", "HANDOFF.json", "VALIDATION_REPORT.json"}
IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__",
           ".pytest_cache", ".mypy_cache", "evidence", ".auth", "profiles", "credentials", "build", "dist"}
RESERVED = {"MANIFEST.json", "HANDOFF.json"}
NAVIGATION_FILES = ("evidence/navigation/STATUS_FA.md", "evidence/navigation/BACKLOG_FA.md")
BASELINE_SHA256 = "8f898b60627c07ec9c4028ff4bfa510c1b5578c2dd1141fa8f2f16ed648fd742"
MAX_MEMBER = 100 * 1024 * 1024
MAX_TOTAL = 250 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Blocked("Cannot read JSON: " + str(path)) from exc


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def safe_path(root, name):
    require(isinstance(name, str) and name and "\\" not in name, "Invalid relative path")
    part = PurePosixPath(name)
    require(not part.is_absolute() and ".." not in part.parts and ":" not in name,
            "Path must stay inside project")
    path = root / name
    require(path.resolve().is_relative_to(root.resolve()), "Path escapes project")
    current = root
    for segment in part.parts:
        current = current / segment
        require(not current.is_symlink(), "Symlink is not portable: " + name)
    return path


def source_rows(root):
    rows = []
    # Native Windows paths compare without case; canonical strings must not.
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root)
        if (any(x in IGNORED or x.endswith(".egg-info") or x == ".env" or x.startswith(".env.") and x != ".env.example"
                for x in rel.parts) or rel.as_posix() in MUTABLE):
            continue
        require(not path.is_symlink(), "Symlink in source snapshot")
        if path.is_file():
            rows.append([rel.as_posix(), digest(path.read_bytes())])
    return rows


def source_digest(root):
    return digest(encoded(source_rows(root)))


def state(root):
    plan, progress = load(root / "ROADMAP.json"), load(root / "PROGRESS.json")
    phases = plan["phases"]
    ids = [p["id"] for p in phases]
    require(ids == ["P%02d" % i for i in range(17)], "Phase order changed")
    require(plan["plan_version"] == progress["plan_version"], "Plan/progress version mismatch")
    require([p["id"] for p in progress["phases"]] == ids, "Progress phases differ")
    required = {"UR-%03d" % i for i in range(1, 31)}
    require({p["id"] for p in plan["coverage"]} == required
            and len(plan["coverage"]) == 30, "Protected requirement coverage changed")
    require({p["id"] for p in progress["runtime_conformance"]} == required
            and len(progress["runtime_conformance"]) == 30, "Runtime requirement list changed")
    for i, p in enumerate(phases):
        require(p["depends_on"] == ([] if i == 0 else [ids[i - 1]]), "Dependency changed")
    current = None
    for p in progress["phases"]:
        status = p["status"]
        if current is None and status == "COMPLETED":
            require(p.get("tests") and p.get("exit_evidence")
                    and p.get("accepted_receipt_sha256") and p.get("accepted_review_sha256"),
                    "Completed phase lacks acceptance record")
            artifact(root, {"path": p["tests"][0], "sha256": p["accepted_receipt_sha256"]})
            artifact(root, {"path": p["exit_evidence"][0], "sha256": p["accepted_review_sha256"]})
            continue
        if current is None:
            require(status in {"READY", "IN_PROGRESS", "BLOCKED"}, "Unknown phase state")
            require(status != "BLOCKED" or p["blockers"], "Blocked phase needs a reason")
            current = p["id"]
        else:
            require(status == "BLOCKED", "Later phase was advanced out of order")
    require(progress["current_phase"] == (current or "COMPLETE"), "Current phase differs")
    resume = progress.get("resume", {})
    require(resume.get("phase") == (current or "COMPLETE"), "Resume position differs from current phase")
    require(not current or isinstance(resume.get("next_action"), str)
            and resume["next_action"].strip(), "Current phase needs an explicit next action")
    baseline = root / "baseline" / plan["baseline"]["package_name"]
    require(plan["baseline"]["package_sha256"] == BASELINE_SHA256 and baseline.is_file()
            and digest(baseline.read_bytes()) == plan["baseline"]["package_sha256"],
            "Protected governance baseline differs")
    verified = sum(r["implementation_status"] == "IMPLEMENTED"
                   and r["verification_status"] == "PASS" for r in progress["runtime_conformance"])
    require(verified == progress["verified_application_requirements"], "Runtime count inconsistent")
    if any(p["status"] == "COMPLETED" and int(p["id"][1:]) >= 13 for p in progress["phases"]):
        require(verified == 30 and plan.get("transfer_policy", {}).get("application_source_supplied"),
                "Application acceptance cannot be inferred from control tests")
    return plan, progress, current


def selected(root, phase):
    plan, progress, current = state(root)
    require(phase == current, "Only the first unfinished phase may proceed")
    index = next(i for i, p in enumerate(plan["phases"]) if p["id"] == phase)
    require(progress["phases"][index]["status"] in {"READY", "IN_PROGRESS"}, "Current phase blocked")
    config = load(root / "CHECKS.json")
    checks = []
    for p in plan["phases"][:index + 1]:
        registered = config["phases"].get(p["id"], [])
        require(registered, "No acceptance checks registered for " + p["id"])
        for item in registered:
            if item.get("acceptance_only", False):
                require(item.get("execution_mode") in {"REAL_EVALUATION", "LIVE_BROWSER", "LIVE_API"}
                        and item.get("reason", "").strip(),
                        "Non-regression checks need an explicit live/evaluation reason")
        if p["id"] != "P00":
            require(any(x["kind"] == "test" for x in registered), "Phase needs actual tests")
        live_mode = {"P03": "LIVE_BROWSER", "P08": "LIVE_API", "P09": "LIVE_BROWSER",
                     "P06": "REAL_EVALUATION", "P14": "REAL_EVALUATION"}.get(p["id"])
        if live_mode:
            require(any(x.get("execution_mode") == live_mode for x in registered),
                    "Required execution mode missing for " + p["id"])
        active = registered if p["id"] == phase else [x for x in registered
                                                     if not x.get("acceptance_only", False)]
        require(active, "Every completed phase needs registered regression checks")
        checks.extend(active)
    require(len({x["id"] for x in checks}) == len(checks), "Duplicate check identifiers")
    junit_paths = [x.get("junit") for x in checks if x["kind"] == "test"]
    require(len(set(junit_paths)) == len(junit_paths), "Checks need separate JUnit outputs")
    for check in checks:
        require(re.fullmatch(r"[A-Za-z0-9_-]+", check["id"]) is not None, "Unsafe check id")
        require(check["kind"] in {"test", "static"}, "Unknown check kind")
        require(isinstance(check["argv"], list) and check["argv"]
                and all(isinstance(x, str) and x for x in check["argv"]), "Invalid argv")
        timeout = check.get("timeout_seconds", 60)
        require(type(timeout) is int and 1 <= timeout <= 3600, "Invalid command timeout")
        if check["kind"] == "test":
            path = safe_path(root, check["junit"])
            require(path.relative_to(root).parts[0] == "evidence", "JUnit must be a run output")
    return plan, progress, checks


def junit_counts(path):
    require(path.is_file() and path.stat().st_size <= 5 * 1024 * 1024, "Missing/oversized JUnit")
    try:
        doc = ET.fromstring(path.read_bytes())
    except ET.ParseError as exc:
        raise Blocked("Invalid JUnit") from exc
    cases = [x for x in doc.iter() if x.tag.rsplit("}", 1)[-1] == "testcase"]
    require(cases, "Zero tests is not a test pass")
    counts = {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0}
    for case in cases:
        tags = {x.tag.rsplit("}", 1)[-1] for x in case}
        for tag, field in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
            counts[field] += int(tag in tags)
    if "tests" in doc.attrib:
        require(doc.attrib["tests"] == str(len(cases)), "JUnit totals inconsistent")
    return counts


def run(root, phase):
    plan, progress, checks = selected(root, phase)
    before = source_digest(root)
    progress_hash = digest((root / "PROGRESS.json").read_bytes())
    run_name = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:10]
    folder = root / "evidence" / "runs" / run_name
    folder.mkdir(parents=True)
    results = []
    for check in checks:
        argv = [sys.executable if x == "{python}" else x for x in check["argv"]]
        test_path = safe_path(root, check["junit"]) if check["kind"] == "test" else None
        if test_path:
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.unlink(missing_ok=True)  # Old report cannot certify a new command.
        log = folder / (check["id"] + ".log")
        counts = None
        message = None
        with log.open("wb") as handle:
            try:
                proc = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                                      stdout=handle, stderr=subprocess.STDOUT,
                                      timeout=check.get("timeout_seconds", 60), shell=False)
                returncode = proc.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                returncode = -1
                message = type(exc).__name__
        ok = returncode == 0
        result = {"id": check["id"], "kind": check["kind"], "argv": argv,
                  "returncode": returncode, "log": log.relative_to(root).as_posix(),
                  "log_sha256": digest(log.read_bytes()), "counts": counts}
        if test_path:
            try:
                counts = junit_counts(safe_path(root, check["junit"]))
                ok = ok and not any(counts[x] for x in ("failures", "errors", "skipped"))
                captured = folder / (check["id"] + ".xml")
                captured.write_bytes(test_path.read_bytes())
                result.update(junit=captured.relative_to(root).as_posix(),
                              junit_input=check["junit"], junit_sha256=digest(captured.read_bytes()),
                              counts=counts)
            except Blocked as exc:
                ok = False
                message = str(exc)
        result.update(status="PASS" if ok else "FAIL", error=message)
        results.append(result)
    after = source_digest(root)
    stable = (before == after
              and progress_hash == digest((root / "PROGRESS.json").read_bytes()))
    receipt = {"schema_version": 1, "phase": phase, "plan_version": plan["plan_version"],
               "source_digest_before": before, "source_digest_after": after,
               "progress_sha256": progress_hash, "checks": results,
               "status": "PASS" if stable and all(x["status"] == "PASS" for x in results) else "FAIL",
               "scope": "CONFIGURED_CHECKS_NOT_PROOF_OF_CORRECTNESS"}
    path = folder / "RUN.json"
    path.write_bytes(encoded(receipt))
    # Keep the latest completed attempt, including FAIL, outside canonical progress.
    # Acceptance still requires gate(); writing this pointer never advances a phase.
    latest = safe_path(root, "evidence/latest/" + phase + ".json")
    latest.parent.mkdir(parents=True, exist_ok=True)
    pointer = {"phase": phase, "receipt": path.relative_to(root).as_posix(),
               "sha256": digest(path.read_bytes())}
    temp = latest.with_name(latest.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(encoded(pointer))
        os.replace(temp, latest)
    finally:
        temp.unlink(missing_ok=True)
    return path, receipt


def artifact(root, entry):
    require(isinstance(entry, dict), "Evidence entry must be an object")
    path = safe_path(root, entry["path"])
    require(path.is_file() and digest(path.read_bytes()) == entry["sha256"],
            "Evidence missing or changed: " + entry["path"])
    return path


@contextlib.contextmanager
def progress_lock(root):
    path = root / "evidence" / "gate.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise Blocked("Another gate or an interrupted gate owns the lock; inspect before recovery") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def freeze_review_evidence(root, phase, review_name, review):
    """Preserve validated criterion bytes before later phases can change their paths."""
    if review.get("evidence_preservation") == "IMMUTABLE_CRITERION_SNAPSHOTS":
        for criterion in review["criteria"]:
            for entry in criterion["evidence"]:
                artifact(root, entry)
        return review_name
    payloads = {}
    for criterion in review["criteria"]:
        for entry in criterion["evidence"]:
            path = artifact(root, entry)
            data = path.read_bytes()
            require(digest(data) == entry["sha256"], "Criterion changed while taking its snapshot")
            secret_check(entry["path"], data)
            require(len(data) <= MAX_MEMBER, "Oversized criterion snapshot")
            payloads[entry["path"]] = data
    require(sum(map(len, payloads.values())) <= MAX_TOTAL, "Criterion snapshots exceed size limit")
    prefix = "evidence/accepted/" + phase + "_" + uuid.uuid4().hex[:12]
    frozen = json.loads(json.dumps(review))
    frozen["original_review"] = {"path": review_name, "sha256": digest(safe_path(root, review_name).read_bytes())}
    frozen["evidence_preservation"] = "IMMUTABLE_CRITERION_SNAPSHOTS"
    for criterion in frozen["criteria"]:
        for entry in criterion["evidence"]:
            entry["original_path"] = entry["path"]
            entry["path"] = prefix + "/proofs/" + entry["path"]
    for original, data in payloads.items():
        path = safe_path(root, prefix + "/proofs/" + original)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    frozen_name = prefix + "/REVIEW.json"
    safe_path(root, frozen_name).write_bytes(encoded(frozen))
    return frozen_name


def preserve_accepted_evidence(root, phase):
    """Upgrade old evidence references without changing an accepted judgment or phase."""
    with progress_lock(root):
        _, progress, current = state(root)
        row = next((x for x in progress["phases"] if x["id"] == phase), None)
        require(row is not None and row["status"] == "COMPLETED", "Only accepted evidence can be preserved")
        require(len(row["exit_evidence"]) == 1, "Inspect multiple-review legacy records manually")
        old_name = row["exit_evidence"][0]
        old = artifact(root, {"path": old_name, "sha256": row["accepted_review_sha256"]})
        before = source_digest(root)
        new_name = freeze_review_evidence(root, phase, old_name, load(old))
        if new_name == old_name:
            return {"status": "PASS", "phase": phase, "phase_advanced": False, "already_preserved": True}
        new_sha = digest(safe_path(root, new_name).read_bytes())
        record_name = str(PurePosixPath(new_name).parent / "PRESERVATION.json")
        record = {"phase": phase, "current_phase": current, "phase_advanced": False,
                  "reason": "Preserve the same validated historical bytes; do not recertify newer source",
                  "original_review": {"path": old_name, "sha256": row["accepted_review_sha256"]},
                  "preserved_review": {"path": new_name, "sha256": new_sha},
                  "accepted_source_digest_unchanged": row["accepted_source_digest"]}
        safe_path(root, record_name).write_bytes(encoded(record))
        row["exit_evidence"] = [new_name]
        row["accepted_review_sha256"] = new_sha
        row["evidence_preservation_record"] = {"path": record_name,
                                              "sha256": digest(safe_path(root, record_name).read_bytes())}
        require(source_digest(root) == before, "Source changed during evidence preservation")
        temp = root / "evidence" / ("progress_" + uuid.uuid4().hex + ".tmp")
        temp.write_bytes(encoded(progress))
        os.replace(temp, root / "PROGRESS.json")
        return {"status": "PASS", "phase": phase, "phase_advanced": False, "review": new_name}


def gate(root, phase, receipt_name, review_name, commit=False):
    with progress_lock(root):
        plan, progress, checks = selected(root, phase)
        current_digest = source_digest(root)
        receipt = load(safe_path(root, receipt_name))
        require(receipt["phase"] == phase and receipt["plan_version"] == plan["plan_version"],
                "Receipt belongs to another phase or plan")
        require(receipt["status"] == "PASS"
                and receipt["source_digest_before"] == receipt["source_digest_after"] == current_digest,
                "Checks failed or source changed since the run")
        require(receipt["progress_sha256"] == digest((root / "PROGRESS.json").read_bytes()),
                "Progress changed since the run")
        require([x["id"] for x in receipt["checks"]] == [x["id"] for x in checks],
                "Receipt does not include all current and regression checks")
        for expected, result in zip(checks, receipt["checks"]):
            argv = [sys.executable if x == "{python}" else x for x in expected["argv"]]
            require(result["status"] == "PASS" and result["returncode"] == 0
                    and result["argv"] == argv and result["kind"] == expected["kind"],
                    "Invalid check result")
            artifact(root, {"path": result["log"], "sha256": result["log_sha256"]})
            if expected["kind"] == "test":
                require(result["junit_input"] == expected["junit"], "Wrong JUnit output")
                path = artifact(root, {"path": result["junit"], "sha256": result["junit_sha256"]})
                counts = junit_counts(path)
                require(counts == result["counts"]
                        and not any(counts[x] for x in ("failures", "errors", "skipped")),
                        "Failed, skipped, inconsistent or empty tests")
        review = load(safe_path(root, review_name))
        require(review["phase"] == phase and review["source_digest"] == current_digest
                and review["status"] == "PASS", "Missing, stale or failed review")
        require(isinstance(review["reviewer"], str) and review["reviewer"].strip()
                and isinstance(review["method"], str) and review["method"].strip(),
                "Review needs a named reviewer and method")
        require(review["impact_assessment"].strip(), "Review must assess affected earlier behavior")
        require(all(x["kind"] in {"DEFECT", "IMPROVEMENT"} and x["state"] in {"OPEN", "CLOSED"}
                    for x in review["findings"]), "Unknown review finding type/state")
        require(not any(x["state"] != "CLOSED" and x["kind"] == "DEFECT"
                        for x in review["findings"]), "Known defect remains open")
        index = next(i for i, p in enumerate(plan["phases"]) if p["id"] == phase)
        entries = review["criteria"]
        expected_ids = [phase + ".E%02d" % (i + 1) for i in range(len(plan["phases"][index]["exit"]))]
        require([x["id"] for x in entries] == expected_ids, "Exit criteria are missing or reordered")
        for entry, expected_text in zip(entries, plan["phases"][index]["exit"]):
            require(entry["status"] == "PASS" and entry["notes"].strip()
                    and entry["evidence"], "Every exit criterion needs review and evidence")
            require(entry["criterion"] == expected_text, "Reviewed criterion text differs from plan")
            for evidence in entry["evidence"]:
                artifact(root, evidence)
        require(not progress["phases"][index]["blockers"], "Phase still has recorded blockers")
        if index >= 13:
            require(plan.get("transfer_policy", {}).get("application_source_supplied"),
                    "No application source is supplied")
            for row in progress["runtime_conformance"]:
                require(row["implementation_status"] == "IMPLEMENTED"
                        and row["verification_status"] == "PASS"
                        and row["evidence"], "Runtime conformance is incomplete")
                for evidence in row["evidence"]:
                    artifact(root, evidence)
                    check = next((x for x in checks if x["id"] == evidence.get("check_id")), None)
                    require(check and row["id"] in check.get("covers", []),
                            "Runtime evidence is not mapped to an executed check")
        require(source_digest(root) == current_digest, "Source changed during gate")
        if commit:
            preserved_review_name = freeze_review_evidence(root, phase, review_name, review)
            require(source_digest(root) == current_digest, "Source changed during evidence snapshot")
            phase_state = progress["phases"][index]
            phase_state.update(status="COMPLETED", accepted_source_digest=current_digest,
                               tests=[receipt_name], exit_evidence=[preserved_review_name],
                               accepted_receipt_sha256=digest(safe_path(root, receipt_name).read_bytes()),
                               accepted_review_sha256=digest(safe_path(root, preserved_review_name).read_bytes()))
            if index + 1 < len(progress["phases"]):
                next_state = progress["phases"][index + 1]
                next_state["blockers"] = [x for x in next_state["blockers"]
                                         if x != "پیش‌نیاز " + phase + " کامل نشده است."]
                next_state["status"] = "BLOCKED" if next_state["blockers"] else "READY"
                progress["current_phase"] = progress["phases"][index + 1]["id"]
            else:
                progress["current_phase"] = "COMPLETE"
            next_phase = next((p for p in plan["phases"]
                               if p["id"] == progress["current_phase"]), None)
            progress["resume"] = {
                "phase": progress["current_phase"],
                "last_verified_checkpoint": phase,
                "completed_work": ["Acceptance and review recorded for " + phase],
                "working_changes": [],
                "next_action": next_phase["tasks"][0] if next_phase else None,
                "next_command": None,
                "note": "Update this record with precise subtask and pending work during development."}
            temp = root / "evidence" / ("progress_" + uuid.uuid4().hex + ".tmp")
            temp.write_bytes(encoded(progress))
            os.replace(temp, root / "PROGRESS.json")
        return {"status": "PASS", "phase": phase, "progress_updated": commit,
                "scope": "MECHANICAL_EVIDENCE_CHECK; REVIEW_CONTENT_REQUIRES_JUDGMENT"}


def template(root, phase, destination):
    plan, progress, current = state(root)
    require(phase == current, "Only current phase can be reviewed")
    selected_phase = next(p for p in plan["phases"] if p["id"] == phase)
    data = {"phase": phase, "source_digest": source_digest(root), "status": "NOT_RUN",
            "reviewer": "", "method": "", "impact_assessment": "", "findings": [],
            "criteria": [{"id": phase + ".E%02d" % (i + 1), "criterion": text,
                          "status": "NOT_RUN", "notes": "", "evidence": []}
                         for i, text in enumerate(selected_phase["exit"])]}
    path = safe_path(root, destination)
    require(not path.exists(), "Review already exists; do not overwrite it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(data))
    return path


def secret_check(name, data):
    parts = PurePosixPath(name).parts
    lowered = {p.lower() for p in parts}
    require(not lowered.intersection({".git", ".auth", "auth", "profiles", "credentials"})
            and not any(p == ".env" or p.startswith(".env.") and p != ".env.example" for p in lowered)
            and Path(name).suffix.lower() not in {".pem", ".key", ".pfx", ".p12"},
            "Sensitive path refused: " + name)
    require(not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", data)
            and not re.search(rb"(?i)(?:api[_-]?key|access[_-]?token)[ \t]*[:=][ \t]*[\"']?[A-Za-z0-9_-]{24,}", data),
            "Recognizable secret refused: " + name)


def run_evidence_files(root, receipt_name):
    receipt = load(safe_path(root, receipt_name))
    names = [receipt_name]
    for result in receipt["checks"]:
        artifact(root, {"path": result["log"], "sha256": result["log_sha256"]})
        names.append(result["log"])
        if "junit" in result:
            artifact(root, {"path": result["junit"], "sha256": result["junit_sha256"]})
            names.append(result["junit"])
    return receipt, names


def latest_phase_run(root, phase, plan_version):
    if phase is None:
        return None, []
    name = "evidence/latest/" + phase + ".json"
    path = safe_path(root, name)
    if not path.exists():
        return None, []
    pointer = load(path)
    require(pointer["phase"] == phase, "Latest run pointer belongs to another phase")
    require(PurePosixPath(pointer["receipt"]).parts[:2] == ("evidence", "runs"),
            "Latest run must point to recorded run evidence")
    artifact(root, {"path": pointer["receipt"], "sha256": pointer["sha256"]})
    receipt, names = run_evidence_files(root, pointer["receipt"])
    require(receipt["phase"] == phase and receipt["plan_version"] == plan_version
            and receipt["status"] in {"PASS", "FAIL"}, "Invalid latest phase run")
    info = {"receipt": pointer["receipt"], "sha256": pointer["sha256"],
            "status": receipt["status"],
            "source_matches_current": receipt["source_digest_before"]
                == receipt["source_digest_after"] == source_digest(root),
            "checks": [{k: x[k] for k in ("id", "status", "counts", "error")}
                       for x in receipt["checks"]],
            "scope": "LATEST_COMPLETED_CONFIGURED_RUN; NOT_PHASE_ACCEPTANCE"}
    return info, [name] + names


def navigation(root, check=False):
    """Derived human-readable views; ROADMAP/PROGRESS/CHECKS remain authoritative."""
    plan, progress, current = state(root)
    inputs = {name: digest((root / name).read_bytes())
              for name in ("ROADMAP.json", "PROGRESS.json", "CHECKS.json")}
    fingerprint = digest(encoded(inputs))
    header = ("این نما خودکار از `ROADMAP.json`، `PROGRESS.json` و `CHECKS.json` ساخته شده است. "
              "ویرایش دستی مرجع نیست؛ پس از تغییر مبنا فرمان تولید را دوباره اجرا کنید.\n\n"
              "شناسهٔ مبنای نما: `" + fingerprint + "`.\n\n")
    completed = [p["id"] for p in progress["phases"] if p["status"] == "COMPLETED"]
    resume = json.dumps(progress["resume"], ensure_ascii=False, indent=2)
    status = ("# وضعیت ادامهٔ پروژه\n\n" + header
              + "مرحلهٔ فعلی: `" + (current or "COMPLETE") + "`. "
              + "آخرین مرحلهٔ پذیرفته‌شده: `" + (completed[-1] if completed else "NONE") + "`.\n\n"
              + "خواسته‌های اجرایی تأییدشده: `" + str(progress["verified_application_requirements"])
              + "/30`. موفقیت ابزار توسعه، پذیرش محصول نیست.\n\n"
              + "## نقطهٔ دقیق ادامه\n\n```json\n" + resume + "\n```\n\n"
              + "## وضعیت مراحل\n\n| مرحله | وضعیت | مانع‌های ثبت‌شده |\n|---|---|---|\n")
    for row in progress["phases"]:
        status += "| `" + row["id"] + "` | `" + row["status"] + "` | " + str(len(row["blockers"])) + " |\n"
    # Task and criterion text is copied verbatim. Technical words are enclosed
    # for Persian Markdown; tests use independent state changes to detect drift.
    def display(value):
        return re.sub(r"[A-Za-z][A-Za-z0-9_./:-]*(?:[ \t]+[A-Za-z][A-Za-z0-9_./:-]*)*",
                      lambda m: "`" + m.group(0) + "`", value)
    backlog = "# کارهای بعدی و معیار پایان\n\n" + header
    backlog += "فقط اولین مرحلهٔ ناتمام قابل ادامه است. معیارهای زیر برنامهٔ آزمون‌اند؛ نتیجهٔ اجرا محسوب نمی‌شوند.\n\n"
    config = load(root / "CHECKS.json")
    for phase, row in zip(plan["phases"], progress["phases"]):
        backlog += "## `" + phase["id"] + "` — " + display(phase["title"]) + "\n\n"
        backlog += "وضعیت: `" + row["status"] + "`؛ بررسی‌های پذیرش ثبت‌شده: `" + str(len(config["phases"].get(phase["id"], []))) + "`.\n\n"
        backlog += "کارها:\n\n" + "".join("- " + display(x) + "\n" for x in phase["tasks"]) + "\n"
        backlog += "معیار پایان:\n\n" + "".join("- " + display(x) + "\n" for x in phase["exit"]) + "\n"
        backlog += "علت اولویت: " + display(phase["why"]) + "\n\n"
    content = dict(zip(NAVIGATION_FILES, (status.encode("utf-8"), backlog.encode("utf-8"))))
    for name, data in content.items():
        path = safe_path(root, name)
        if check:
            require(path.is_file() and path.read_bytes() == data,
                    "Navigation missing or stale; run navigation: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    require(inputs == {name: digest((root / name).read_bytes()) for name in inputs},
            "Canonical inputs changed during navigation")
    return {"status": "PASS", "files": list(content), "input_digest": fingerprint,
            "scope": "DERIVED_NAVIGATION_ONLY; NO_PHASE_ADVANCED"}


def target_evidence_files(root):
    """Follow recorded native report graphs without putting run IDs in source metadata."""
    scope_path = root / "SCOPE.json"
    if not scope_path.is_file():
        return [], []
    targets = load(scope_path).get("target_platforms", [])
    require(isinstance(targets, list) and all(isinstance(x, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", x)
                                             for x in targets), "Invalid target names")
    names, records = [], []
    snapshot = source_digest(root)
    for target in targets:
        pointer_name = "evidence/targets/" + target + "/LATEST.json"
        pointer_path = safe_path(root, pointer_name)
        if not pointer_path.is_file():
            continue  # Missing evidence remains missing; never create a success record.
        reference = load(pointer_path)
        report = load(artifact(root, reference))
        names += [pointer_name, reference["path"]]
        for entry in report["artifacts"].values():
            artifact(root, entry)
            names.append(entry["path"])
        records.append({"target": target, "report": reference, "status": report["status"],
                        "source_matches_current": report["source_digest_before"] == snapshot,
                        "scope": "RECORDED_TARGET_ARTIFACTS_NOT_PHASE_ACCEPTANCE"})
    return names, records


def handoff(root, output):
    plan, progress, current = state(root)
    config = load(root / "TRANSFER_FILES.json")
    names = list(config["files"])
    require(len(names) == len(set(names)) and not RESERVED.intersection(names),
            "Duplicate or reserved transfer paths")
    require({"ROADMAP.json", "PROGRESS.json", "CHECKS.json", "TRANSFER_FILES.json",
             "tools/qualityctl.py", "START_HERE_FA.md"}.issubset(names),
            "Missing mandatory transfer files")
    require({row[0] for row in source_rows(root)}.issubset(names),
            "Source files omitted from transfer allowlist")
    if any(safe_path(root, name).exists() for name in NAVIGATION_FILES):
        navigation(root, check=True)
        names.extend(NAVIGATION_FILES)
    latest, latest_names = latest_phase_run(root, current, plan["plan_version"])
    names.extend(latest_names)
    target_names, target_records = target_evidence_files(root)
    names.extend(target_names)
    for phase in progress["phases"]:
        if phase["status"] != "COMPLETED":
            continue
        for receipt_name in phase["tests"]:
            _, evidence_names = run_evidence_files(root, receipt_name)
            names.extend(evidence_names)
        for review_name in phase["exit_evidence"]:
            review = load(safe_path(root, review_name))
            names.append(review_name)
            if review.get("original_review"):
                artifact(root, review["original_review"])
                names.append(review["original_review"]["path"])
            for criterion in review["criteria"]:
                for evidence in criterion["evidence"]:
                    artifact(root, evidence)
                names.extend(x["path"] for x in criterion["evidence"])
        if phase.get("evidence_preservation_record"):
            artifact(root, phase["evidence_preservation_record"])
            names.append(phase["evidence_preservation_record"]["path"])
    names = sorted(set(names))
    output = output.resolve()
    if output.is_relative_to(root.resolve()):
        require(output.relative_to(root.resolve()).parts[0] == "evidence",
                "Put generated archives under evidence or outside the source root")
    require(not output.exists(), "Archive already exists")
    snapshot = source_digest(root)
    payload = {}
    total = 0
    for name in names:
        path = safe_path(root, name)
        require(path.is_file() and path.stat().st_size <= MAX_MEMBER, "Missing/oversized transfer file")
        data = path.read_bytes()
        secret_check(name, data)
        total += len(data)
        require(total <= MAX_TOTAL, "Transfer size limit exceeded")
        payload[name] = data
    completed = [p for p in progress["phases"] if p["status"] == "COMPLETED"]
    last = completed[-1] if completed else None
    info = {"schema_version": 1, "plan_version": plan["plan_version"],
            "source_snapshot_digest": snapshot, "current_phase": current or "COMPLETE",
            "last_accepted_phase": last["id"] if last else None,
            "latest_current_phase_run": latest,
            "native_target_runs": target_records,
            "last_acceptance_matches_current_source":
                bool(last and last.get("accepted_source_digest") == snapshot),
            "application_source_supplied":
                plan.get("transfer_policy", {}).get("application_source_supplied", False),
            "application_source_commit": progress.get("application_source_commit") or plan["baseline"].get("application_source_commit"),
            "verified_application_requirements": progress["verified_application_requirements"],
            "state_label": "INCOMPLETE" if current else "PHASES_COMPLETED; CHECK_RELEASE_EVIDENCE",
            "next_action": progress["resume"].get("next_action"),
            "resume": progress["resume"],
            "security_note": "Allowlist and basic patterns only; manually review before sharing."}
    payload["HANDOFF.json"] = encoded(info)
    manifest = {"schema_version": 1, "files": [
        {"path": name, "bytes": len(data), "sha256": digest(data)}
        for name, data in sorted(payload.items())]}
    payload["MANIFEST.json"] = encoded(manifest)
    require(source_digest(root) == snapshot, "Source changed while preparing handoff")
    require(payload["PROGRESS.json"] == (root / "PROGRESS.json").read_bytes(),
            "Progress changed while preparing handoff")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.parent / (output.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(payload.items()):
                archive.writestr(name, data)
        verify(temp)
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    return info


def verify(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [x.filename for x in entries]
        require(len(names) == len(set(names)) and len(names) <= 10000, "Duplicate/excessive ZIP members")
        require(len({x.casefold() for x in names}) == len(names), "Case-colliding ZIP paths")
        total = 0
        for entry in entries:
            name = PurePosixPath(entry.filename)
            require(not name.is_absolute() and ".." not in name.parts and "\\" not in entry.filename
                    and ":" not in entry.filename and name.as_posix() == entry.filename
                    and not entry.is_dir(), "Unsafe ZIP member")
            require(not stat.S_ISLNK(entry.external_attr >> 16), "ZIP symlink refused")
            total += entry.file_size
            require(entry.file_size <= MAX_MEMBER and total <= MAX_TOTAL, "ZIP size limit exceeded")
        require("MANIFEST.json" in names, "No manifest")
        try:
            manifest = json.loads(archive.read("MANIFEST.json"))
            rows = manifest["files"]
        except (ValueError, KeyError) as exc:
            raise Blocked("Invalid manifest") from exc
        require(len(rows) == len({x["path"] for x in rows})
                and {x["path"] for x in rows} == set(names) - {"MANIFEST.json"},
                "Manifest coverage differs")
        for row in rows:
            data = archive.read(row["path"])
            require(len(data) == row["bytes"] and digest(data) == row["sha256"],
                    "Archive content differs: " + row["path"])
            secret_check(row["path"], data)
    return {"status": "PASS", "files": len(names),
            "scope": "BYTES_AND_PATHS_ONLY; NO_CODE_EXECUTED_OR_PRODUCT_CERTIFIED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("phase")
    gate_parser = sub.add_parser("gate")
    gate_parser.add_argument("phase")
    gate_parser.add_argument("--receipt", required=True)
    gate_parser.add_argument("--review", required=True)
    gate_parser.add_argument("--commit", action="store_true")
    draft = sub.add_parser("review-template")
    draft.add_argument("phase")
    draft.add_argument("--out", required=True)
    export = sub.add_parser("handoff")
    export.add_argument("--out", type=Path, required=True)
    inspect = sub.add_parser("verify")
    inspect.add_argument("archive", type=Path)
    views = sub.add_parser("navigation")
    views.add_argument("--check", action="store_true")
    preserve = sub.add_parser("preserve-evidence")
    preserve.add_argument("phase")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "status":
            plan, progress, current = state(root)
            result = {"plan_version": plan["plan_version"], "current_phase": current,
                      "verified_application_requirements": progress["verified_application_requirements"],
                      "source_snapshot_digest": source_digest(root)}
        elif args.command == "navigation":
            result = navigation(root, args.check)
        elif args.command == "preserve-evidence":
            result = preserve_accepted_evidence(root, args.phase)
        elif args.command == "run":
            path, receipt = run(root, args.phase)
            result = {"receipt": path.relative_to(root).as_posix(), "status": receipt["status"]}
            print(json.dumps(result, ensure_ascii=False))
            return int(receipt["status"] != "PASS")
        elif args.command == "gate":
            result = gate(root, args.phase, args.receipt, args.review, args.commit)
        elif args.command == "review-template":
            result = {"draft": str(template(root, args.phase, args.out)), "status": "NOT_RUN"}
        elif args.command == "handoff":
            result = handoff(root, args.out)
        else:
            result = verify(args.archive)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (Blocked, KeyError, TypeError, AttributeError, ValueError,
            zipfile.BadZipFile, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
