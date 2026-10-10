"""Atomic offline page observations. Resume polls; it never dispatches or resends."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from consilium.core.browser_probe import BrowserBinding, ProbeTicket
from consilium.core.browser_watch import BrowserWatch, PageSnapshot
from consilium.shell.private import ensure_public_payload

MAX_EVENTS = 256
MAX_EVENT_BYTES = 2 * 1048576
MAX_TOTAL_BYTES = 32 * 1048576


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class BrowserWatchJournal:
    """One exact operation/binding per database, with optimistic local revisions.

    Hashes detect accidental corruption, not an adversary rewriting the entire
    database. Stored pages are private synthetic evidence, never live authority.
    """

    @classmethod
    def from_recorded_probe(cls, database, *, store, ticket: ProbeTicket, baseline):
        """Attach to an already recorded attempt; never begin or repeat a send.

        This preparation bridge deliberately retains the narrow P03 ticket
        contract. It does not turn fixture pages into a product response.
        """
        ticket = ProbeTicket.model_validate(ticket.model_dump(mode="python"))
        record = store.ledger.get_attempt(ticket.request.intent.identity.attempt_id)
        if record.request != ticket.request:
            raise ValueError("JOURNAL_REQUIRES_EXACT_RECORDED_REQUEST")
        store._public(baseline.model_dump(mode="json"))
        return cls(
            database,
            operation_id=record.intent.identity.attempt_id,
            request_hash=record.intent.request_hash,
            binding=ticket.binding,
            baseline=baseline,
            prompt_hash=digest(record.intent.frozen_input.messages[0].content),
            forbidden_values=store._forbidden_values,
        )

    def inspect_recorded_probe(self, *, store, ticket: ProbeTicket):
        """Recheck attachment and report both states without ledger mutation."""
        attached = type(self).from_recorded_probe(
            self.database,
            store=store,
            ticket=ticket,
            baseline=PageSnapshot.model_validate_json(encoded(self.spec["baseline"])),
        )
        record = store.ledger.get_attempt(ticket.request.intent.identity.attempt_id)
        return {
            "scope": "OFFLINE_JOURNAL_INSPECTION_NOT_TRANSPORT_RESULT",
            "attempt_id": str(record.intent.identity.attempt_id),
            "ledger_state": record.state.value,
            "ledger_revision": record.active_revision,
            "observation": attached.resume(),
            "may_dispatch": False,
            "may_confirm_product_response": False,
        }

    def __init__(
        self,
        database: Path,
        *,
        operation_id: UUID,
        request_hash: str,
        binding: BrowserBinding,
        baseline: PageSnapshot,
        prompt_hash: str,
        forbidden_values: tuple[str, ...] = (),
    ):
        BrowserWatch(binding, baseline, prompt_hash)
        if (
            type(operation_id) is not UUID
            or not operation_id.int
            or type(request_hash) is not str
            or len(request_hash) != 64
            or any(c not in "0123456789abcdef" for c in request_hash)
        ):
            raise ValueError("JOURNAL_OPERATION_REQUIRED")
        self.database = Path(database)
        self.forbidden_values = forbidden_values
        self.spec = {
            "schema_version": 1,
            "scope": "OFFLINE_PAGE_JOURNAL_NOT_LIVE_AUTHORITY",
            "operation_id": str(operation_id),
            "request_hash": request_hash,
            "binding": binding.model_dump(mode="json"),
            "baseline": baseline.model_dump(mode="json"),
            "prompt_hash": prompt_hash,
        }
        ensure_public_payload(self.spec, forbidden_values)
        self.spec_json = encoded(self.spec)
        if len(self.spec_json.encode()) > MAX_EVENT_BYTES:
            raise ValueError("JOURNAL_BASELINE_TOO_LARGE")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS header (id INTEGER PRIMARY KEY CHECK(id=1), spec TEXT NOT NULL, revision INTEGER NOT NULL, tip TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS events (revision INTEGER PRIMARY KEY, "
                "event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, parent_hash TEXT NOT NULL, event_hash TEXT NOT NULL)"
            )
            row = db.execute("SELECT spec FROM header WHERE id=1").fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO header VALUES(1,?,0,?)",
                    (self.spec_json, digest(self.spec_json)),
                )
            elif row[0] != self.spec_json:
                raise ValueError("JOURNAL_OPERATION_OR_BINDING_CHANGED")
            self._replay(db)

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.database, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _replay(self, db):
        head = db.execute("SELECT spec,revision,tip FROM header WHERE id=1").fetchone()
        if head is None or head[0] != self.spec_json:
            raise ValueError("JOURNAL_HEADER_CHANGED")
        count, size = db.execute(
            "SELECT count(*),coalesce(sum(length(cast(payload AS BLOB))),0) FROM events"
        ).fetchone()
        if count > MAX_EVENTS or size > MAX_TOTAL_BYTES:
            raise ValueError("JOURNAL_LIMIT_EXCEEDED")
        rows = db.execute(
            "SELECT revision,event_id,payload,parent_hash,event_hash FROM events ORDER BY revision"
        ).fetchall()
        if (
            len(rows) > MAX_EVENTS
            or sum(len(r[2].encode()) for r in rows) > MAX_TOTAL_BYTES
        ):
            raise ValueError("JOURNAL_LIMIT_EXCEEDED")
        watch = BrowserWatch(
            BrowserBinding.model_validate_json(encoded(self.spec["binding"])),
            PageSnapshot.model_validate_json(encoded(self.spec["baseline"])),
            self.spec["prompt_hash"],
        )
        parent = digest(self.spec_json)
        for revision, row in enumerate(rows, 1):
            number, event_id, payload, prior, checksum = row
            if (
                number != revision
                or prior != parent
                or len(payload.encode()) > MAX_EVENT_BYTES
                or checksum != digest(encoded([prior, number, event_id, payload]))
            ):
                raise ValueError("JOURNAL_EVENT_CHAIN_INVALID")
            value = json.loads(payload)
            ensure_public_payload(value, self.forbidden_values)
            if value == {"kind": "INTERRUPT"}:
                if watch.stopped:
                    raise ValueError("JOURNAL_EVENT_AFTER_CLOSED_WATCH")
                watch.interrupt()
            elif set(value) == {"kind", "snapshot"} and value["kind"] == "PAGE":
                watch.observe(
                    PageSnapshot.model_validate_json(encoded(value["snapshot"]))
                )
            else:
                raise ValueError("JOURNAL_EVENT_INVALID")
            parent = checksum
        if (head[1], head[2]) != (len(rows), parent):
            raise ValueError("JOURNAL_HEAD_OR_TAIL_INVALID")
        return watch, len(rows), parent

    def resume(self):
        with self._transaction() as db:
            watch, revision, _ = self._replay(db)
            return {
                "revision": revision,
                "state": watch.state,
                "content": watch.content,
                "stopped": watch.stopped,
                "failure": watch.failure,
                "next_action": "STOP" if watch.stopped else "OBSERVE_ONLY_NO_RESEND",
                "live_origin_verified": False,
            }

    def append(self, snapshot: PageSnapshot, *, event_id: UUID, expected_revision: int):
        snapshot = PageSnapshot.model_validate(snapshot)
        return self._append(
            {"kind": "PAGE", "snapshot": snapshot.model_dump(mode="json")},
            event_id,
            expected_revision,
        )

    def interrupt(self, *, event_id: UUID, expected_revision: int):
        return self._append({"kind": "INTERRUPT"}, event_id, expected_revision)

    def _append(self, value, event_id, expected_revision):
        if (
            type(event_id) is not UUID
            or not event_id.int
            or type(expected_revision) is not int
            or expected_revision < 0
        ):
            raise ValueError("JOURNAL_EVENT_ID_OR_REVISION_INVALID")
        ensure_public_payload(value, self.forbidden_values)
        payload = encoded(value)
        if len(payload.encode()) > MAX_EVENT_BYTES:
            raise ValueError("JOURNAL_EVENT_TOO_LARGE")
        with self._transaction() as db:
            watch, revision, parent = self._replay(db)
            old = db.execute(
                "SELECT payload FROM events WHERE event_id=?", (str(event_id),)
            ).fetchone()
            if old is not None:
                if old[0] != payload:
                    raise ValueError("JOURNAL_EVENT_ID_REUSED")
                return revision  # Exact committed replay is harmless, even after a newer event.
            if watch.stopped or revision != expected_revision:
                raise ValueError("JOURNAL_CLOSED_OR_STALE_REVISION")
            size = db.execute(
                "SELECT coalesce(sum(length(cast(payload AS BLOB))),0) FROM events"
            ).fetchone()[0]
            if revision >= MAX_EVENTS or size + len(payload.encode()) > MAX_TOTAL_BYTES:
                raise ValueError("JOURNAL_LIMIT_EXCEEDED")
            if value["kind"] == "PAGE":
                watch.observe(
                    PageSnapshot.model_validate_json(encoded(value["snapshot"]))
                )
            else:
                watch.interrupt()
            number = revision + 1
            checksum = digest(encoded([parent, number, str(event_id), payload]))
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?)",
                (number, str(event_id), payload, parent, checksum),
            )
            db.execute(
                "UPDATE header SET revision=?,tip=? WHERE id=1", (number, checksum)
            )
            return number
