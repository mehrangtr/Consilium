"""Read-only acquisition bridge; injected readers are not live-certified drivers."""

from dataclasses import dataclass
from uuid import UUID

from consilium.adapters.qwen_page_reader import read_qwen_capture
from consilium.core.browser_probe import BrowserBinding, BrowserContext, context_matches
from consilium.shell.browser_watch_journal import BrowserWatchJournal, encoded


@dataclass(frozen=True)
class QwenCaptureRead:
    before: BrowserContext
    raw: bytes
    after: BrowserContext


def record_qwen_read(
    journal: BrowserWatchJournal, reader, *, event_id: UUID, expected_revision: int
):
    """Read once and atomically ingest, or return an already committed capture.

    The reader must only observe and return a QwenCaptureRead. It owns browser
    deadlines/cancellation; this bridge cannot cancel a blocking callable.
    Contexts are declarations pending live driver verification. No authority or
    main-ledger delivery is granted, and no dispatch interface is provided.
    """
    if (
        type(event_id) is not UUID
        or not event_id.int
        or type(expected_revision) is not int
        or expected_revision < 0
        or not callable(reader)
    ):
        raise ValueError("QWEN_READ_ARGUMENTS_INVALID")
    # Validates the whole chain before any external observation.
    state = journal.resume()
    try:
        committed = journal.read_qwen_capture(event_id=event_id)
    except ValueError as error:
        if str(error) != "JOURNAL_QWEN_CAPTURE_NOT_FOUND":
            raise
    else:
        return {**committed, "reused": True, "reader_invoked": False}
    if state["stopped"] or state["revision"] != expected_revision:
        raise ValueError("QWEN_READ_CLOSED_OR_STALE")
    binding = BrowserBinding.model_validate_json(encoded(journal.spec["binding"]))
    failed = False
    try:
        packet = reader()
    except Exception:  # noqa: BLE001 -- private reader failures must not cross this boundary
        failed = True
    if failed:
        # Raise outside the handler so private reader exceptions are not chained.
        raise ValueError("QWEN_READ_FAILED")
    if type(packet) is not QwenCaptureRead:
        raise ValueError("QWEN_READ_PACKET_REQUIRED")
    invalid = False
    try:
        before = BrowserContext.model_validate(packet.before)
        after = BrowserContext.model_validate(packet.after)
    except ValueError:
        invalid = True
    if invalid:
        raise ValueError("QWEN_READ_CONTEXT_INVALID")
    if not context_matches(binding, before) or not context_matches(binding, after):
        raise ValueError("QWEN_READ_CONTEXT_CHANGED")
    page = read_qwen_capture(packet.raw)
    if not context_matches(binding, page.context):
        raise ValueError("QWEN_READ_CAPTURE_CONTEXT_CHANGED")
    # The transaction rechecks revision after the read; no stale writer can commit.
    journal.append_qwen_capture(
        packet.raw, event_id=event_id, expected_revision=expected_revision
    )
    return {
        **journal.read_qwen_capture(event_id=event_id),
        "reused": False,
        "reader_invoked": True,
    }
