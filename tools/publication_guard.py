"""Durable permits for bounded Git connector calls, not a connector canceller.

Store public identifiers and hashes only. The caller enforces the wait deadline
and supplies independently read object/ref SHA evidence after ambiguous calls.
Only immutable content-addressed Git objects can receive a second permit.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from uuid import uuid4


class Blocked(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class PublicationGuard:
    def __init__(self, path):
        self.db = sqlite3.connect(Path(path), timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, plan TEXT NOT NULL, "
                        "state TEXT NOT NULL, attempts INTEGER NOT NULL, nonce TEXT, deadline REAL, "
                        "observed_sha TEXT, reason TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, "
                        "operation_id TEXT NOT NULL, state TEXT NOT NULL, nonce TEXT, at REAL NOT NULL)")
        self.db.commit()

    def close(self):
        self.db.close()

    def _event(self, operation_id, state, nonce):
        self.db.execute("INSERT INTO events(operation_id,state,nonce,at) VALUES(?,?,?,?)",
                        (operation_id, state, nonce, time.time()))

    def prepare(self, plan):
        if set(plan) != {"kind", "resource", "expected_sha", "request_sha256", "source_digest"}:
            raise Blocked("INVALID_PLAN_FIELDS")
        if (plan["kind"] not in {"GIT_OBJECT", "REF_UPDATE", "SERVER_COMMIT"}
                or not isinstance(plan["resource"], str)
                or not re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", plan["resource"])
                or not re.fullmatch(r"[0-9a-f]{40}", str(plan["expected_sha"]))
                or any(not re.fullmatch(r"[0-9a-f]{64}", str(plan[key]))
                       for key in ("request_sha256", "source_digest"))):
            raise Blocked("INVALID_PUBLIC_PLAN")
        encoded = canonical(plan)
        operation_id = hashlib.sha256(encoded.encode()).hexdigest()
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO operations VALUES(?,?,'PREPARED',0,NULL,NULL,NULL,NULL)",
                            (operation_id, encoded))
        return self.inspect(operation_id)

    def inspect(self, operation_id):
        row = self.db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if row is None:
            raise Blocked("UNKNOWN_OPERATION")
        result = dict(row)
        result["plan"] = json.loads(result["plan"])
        if hashlib.sha256(canonical(result["plan"]).encode()).hexdigest() != operation_id:
            raise Blocked("PLAN_CHECKSUM_MISMATCH")
        return result

    def begin(self, operation_id, *, wait_seconds=25):
        if type(wait_seconds) is not int or not 1 <= wait_seconds <= 60:
            raise Blocked("INVALID_WAIT_LIMIT")
        # Serial transaction prevents two controllers acquiring the same permit.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.inspect(operation_id)
            if row["state"] == "VERIFIED_COMPLETE":
                raise Blocked("ALREADY_VERIFIED_COMPLETE")
            if row["state"] not in {"PREPARED", "VERIFIED_NOT_APPLIED"}:
                raise Blocked("RECONCILIATION_REQUIRED")
            if row["plan"]["kind"] == "REF_UPDATE":
                for pending in self.pending():
                    if (pending["id"] != operation_id and pending["plan"]["resource"] == row["plan"]["resource"]
                            and pending["state"] in {"IN_FLIGHT", "UNKNOWN", "BLOCKED"}):
                        raise Blocked("RESOURCE_HAS_UNRESOLVED_MUTATION")
            if row["attempts"] >= 2 or (row["attempts"] and row["plan"]["kind"] != "GIT_OBJECT"):
                raise Blocked("RETRY_LIMIT_OR_MUTABLE_OPERATION")
            nonce = uuid4().hex
            self.db.execute("UPDATE operations SET state='IN_FLIGHT',attempts=attempts+1,nonce=?,"
                            "deadline=?,reason=NULL WHERE id=?", (nonce, time.time()+wait_seconds, operation_id))
            self._event(operation_id, "IN_FLIGHT", nonce)
            self.db.commit()
            return self.inspect(operation_id)
        except BaseException:
            self.db.rollback()
            raise

    def unknown(self, operation_id, nonce, *, reason="WAIT_TIMEOUT"):
        if reason not in {"WAIT_TIMEOUT", "CONNECTOR_ERROR", "SESSION_INTERRUPTED"}:
            raise Blocked("INVALID_FIXED_REASON")
        with self.db:
            row = self.inspect(operation_id)
            if row["nonce"] != nonce or row["state"] != "IN_FLIGHT":
                raise Blocked("STALE_ATTEMPT")
            self.db.execute("UPDATE operations SET state='UNKNOWN',reason=? WHERE id=?", (reason, operation_id))
            self._event(operation_id, "UNKNOWN", nonce)
        return self.inspect(operation_id)

    def reconcile(self, operation_id, nonce, *, observed_sha):
        if observed_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", str(observed_sha)):
            raise Blocked("INVALID_READ_EVIDENCE")
        with self.db:
            row = self.inspect(operation_id)
            if row['plan']['kind'] == 'SERVER_COMMIT':
                raise Blocked('SERVER_COMMIT_REQUIRES_INDEPENDENT_CONTENT_EVIDENCE')
            if row["nonce"] != nonce or row["state"] not in {"IN_FLIGHT", "UNKNOWN", "BLOCKED", "VERIFIED_NOT_APPLIED"}:
                raise Blocked("STALE_ATTEMPT")
            if observed_sha == row["plan"]["expected_sha"]:
                state = "VERIFIED_COMPLETE"
            elif observed_sha is None and row["plan"]["kind"] == "GIT_OBJECT":
                state = "VERIFIED_NOT_APPLIED"
            else:
                # A missing/old ref could still change after a timed-out call.
                # Read evidence never grants a second mutable write permit.
                state = "BLOCKED"
            self.db.execute("UPDATE operations SET state=?,observed_sha=? WHERE id=?",
                            (state, observed_sha, operation_id))
            self._event(operation_id, state, nonce)
        return self.inspect(operation_id)

    def reconcile_commit(self, operation_id, nonce, *, observed_commit):
        # The server chooses author/committer timestamps, so the final commit
        # SHA cannot be predicted by this connector. Bind its independently
        # fetched tree, ordered parents and message hash to the prepared request.
        if set(observed_commit) != {'commit_sha', 'tree_sha', 'parent_shas', 'message_sha256'}:
            raise Blocked('INVALID_COMMIT_EVIDENCE')
        if (not isinstance(observed_commit['parent_shas'], list) or not observed_commit['parent_shas']
                or any(not re.fullmatch(r'[0-9a-f]{40}', str(value)) for value in
                       [observed_commit['commit_sha'], observed_commit['tree_sha'], *observed_commit['parent_shas']])
                or not re.fullmatch(r'[0-9a-f]{64}', str(observed_commit['message_sha256']))):
            raise Blocked('INVALID_COMMIT_EVIDENCE')
        request = {key: value for key, value in observed_commit.items() if key != 'commit_sha'}
        request_hash = hashlib.sha256(canonical(request).encode()).hexdigest()
        with self.db:
            row = self.inspect(operation_id)
            if (row['plan']['kind'] != 'SERVER_COMMIT' or row['nonce'] != nonce
                    or row['state'] not in {'IN_FLIGHT', 'UNKNOWN', 'BLOCKED'}):
                raise Blocked('STALE_OR_WRONG_COMMIT_ATTEMPT')
            matched = (observed_commit['tree_sha'] == row['plan']['expected_sha']
                       and request_hash == row['plan']['request_sha256'])
            state = 'VERIFIED_COMPLETE' if matched else 'BLOCKED'
            self.db.execute('UPDATE operations SET state=?,observed_sha=? WHERE id=?',
                            (state, observed_commit['commit_sha'], operation_id))
            self._event(operation_id, state, nonce)
        return self.inspect(operation_id)

    def pending(self):
        return [self.inspect(row[0]) for row in self.db.execute(
            "SELECT id FROM operations WHERE state!='VERIFIED_COMPLETE' ORDER BY rowid")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("action", choices=("prepare", "begin", "unknown", "reconcile", "reconcile_commit", "pending"))
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.action != "pending" else {}
        with closing(PublicationGuard(args.database)) as guard:
            result = getattr(guard, args.action)(**payload)
        print(canonical(result))
        return 0
    except (ValueError, TypeError, KeyError, sqlite3.Error, OSError):
        print('{"status":"BLOCKED_INVALID_OR_UNRESOLVED_OPERATION"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
