"""Preserve published migrations; add atomic, inspectable local policy evidence."""
from .schema_v3 import V3_TABLES

V4_STATEMENTS = (
    """CREATE TABLE context_admissions(
        logical_operation_id TEXT PRIMARY KEY REFERENCES operations(logical_operation_id),
        prepared_attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
        bundle_json TEXT NOT NULL CHECK(json_valid(bundle_json)),
        bundle_hash TEXT NOT NULL CHECK(length(bundle_hash)=64),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence)) STRICT""",
)
V4_TABLES = V3_TABLES | {"context_admissions"}
