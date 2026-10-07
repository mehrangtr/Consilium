"""Append explicit manual operation retirement; published V1-V8 SQL is immutable."""
from .schema_v8 import V8_STATEMENTS, V8_TABLES
from .schema_v2 import V2_STATEMENTS

V9_STATEMENTS = (
    V8_STATEMENTS[0].replace("events_v8", "events_v9").replace(
        "'MANUAL_ROUND_ACCEPTED'))", "'MANUAL_ROUND_ACCEPTED','MANUAL_OPERATIONS_RECONCILED'))"),
    "INSERT INTO events_v9 SELECT * FROM events",
    "DROP TABLE events",
    "ALTER TABLE events_v9 RENAME TO events",
    next(s for s in V2_STATEMENTS if s.startswith("CREATE TABLE rejected_results(")).replace(
        "CREATE TABLE rejected_results(", "CREATE TABLE rejected_results_v9(").replace(
        "'STALE_RESULT','RESULT_CONFLICT'", "'STALE_RESULT','RESULT_CONFLICT','MANUALLY_RECONCILED_OPERATION'"),
    "INSERT INTO rejected_results_v9 SELECT * FROM rejected_results",
    "DROP TABLE rejected_results",
    "ALTER TABLE rejected_results_v9 RENAME TO rejected_results",
    """CREATE TABLE manual_operation_reconciliations(
        user_action_id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES rounds(round_id),
        participant_id TEXT NOT NULL, record_json TEXT NOT NULL CHECK(json_valid(record_json)),
        record_hash TEXT NOT NULL CHECK(length(record_hash)=64),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence),
        UNIQUE(round_id,participant_id)) STRICT""",
)
V9_TABLES = V8_TABLES | {"manual_operation_reconciliations"}
