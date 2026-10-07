"""Add frozen response contracts and multi-source publication, preserving V1-V5."""
from .schema_v5 import V5_STATEMENTS, V5_TABLES

V6_STATEMENTS = (
    V5_STATEMENTS[0].replace("events_v5", "events_v6").replace(
        "'CONTEXT_SOURCE_PUBLISHED'))", "'CONTEXT_SOURCE_PUBLISHED','SOURCE_BATCH_PUBLISHED'))"),
    "INSERT INTO events_v6 SELECT * FROM events",
    "DROP TABLE events",
    "ALTER TABLE events_v6 RENAME TO events",
    """CREATE TABLE response_contracts(
        logical_operation_id TEXT PRIMARY KEY REFERENCES operations(logical_operation_id),
        prepared_attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
        contract_json TEXT NOT NULL CHECK(json_valid(contract_json)),
        contract_hash TEXT NOT NULL CHECK(length(contract_hash)=64),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence)) STRICT""",
    """CREATE TABLE canonical_source_batches(
        logical_operation_id TEXT PRIMARY KEY REFERENCES canonical_results(logical_operation_id),
        attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
        record_json TEXT NOT NULL CHECK(json_valid(record_json)),
        record_hash TEXT NOT NULL CHECK(length(record_hash)=64),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence)) STRICT""",
)
V6_TABLES = V5_TABLES | {"response_contracts", "canonical_source_batches"}
