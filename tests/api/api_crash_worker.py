"""Abrupt exit after a synthetic API result reaches the durable result boundary."""

import os
import sys
from pathlib import Path

from consilium.adapters.api_offline import ApiFixture, OfflineApiAdapter
from consilium.core.contracts import AdapterRequest
from consilium.shell.storage import SQLiteStore

request = AdapterRequest.model_validate_json(Path(sys.argv[2]).read_text())
with SQLiteStore(Path(sys.argv[1])) as store:
    revision = store.checkpoint(request.intent.debate_id).revision
    checkpoint = store.ledger.begin_send(
        request, expected_revision=revision, offline_mock=True
    )
    body = (
        b'data: {"id":"fixture-q","choices":[{"delta":{"content":"unfinished"}}]}\n\n'
    )
    adapter = OfflineApiAdapter(
        "qwen",
        "fixture-model",
        ApiFixture(chunks=(body,), streaming=True, interrupted=True),
    )
    result = adapter.send(request)
    store.ledger.record_result(result, expected_revision=checkpoint.revision)
    os._exit(79)
