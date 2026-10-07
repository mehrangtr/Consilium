"""Add source publication without rewriting any published migration."""
from .schema_v4 import V4_TABLES
from .schema_v3 import V3_STATEMENTS

V5_STATEMENTS = (
    V3_STATEMENTS[0].replace("events_v3", "events_v5").replace(
        "'QUESTION_ADOPTED'))", "'QUESTION_ADOPTED','CONTEXT_SOURCE_PUBLISHED'))"),
    "INSERT INTO events_v5 SELECT * FROM events",
    "DROP TABLE events",
    "ALTER TABLE events_v5 RENAME TO events",
    """CREATE TABLE canonical_context_sources(
        logical_operation_id TEXT PRIMARY KEY REFERENCES canonical_results(logical_operation_id),
        attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
        source_hash TEXT NOT NULL UNIQUE CHECK(length(source_hash)=64),
        record_json TEXT NOT NULL CHECK(json_valid(record_json)),
        record_hash TEXT NOT NULL CHECK(length(record_hash)=64),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence)) STRICT""",
)
V5_TABLES = V4_TABLES | {"canonical_context_sources"}
