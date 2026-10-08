"""Append council records and terminal state; published V1-V9 SQL is unchanged."""
from .schema_v9 import V9_STATEMENTS, V9_TABLES

V10_STATEMENTS = (
    V9_STATEMENTS[0].replace('events_v9', 'events_v10').replace(
        "'MANUAL_OPERATIONS_RECONCILED'))",
        "'MANUAL_OPERATIONS_RECONCILED','COUNCIL_ANALYZED','COUNCIL_JUDGE_SELECTED','COUNCIL_COMPLETED','COUNCIL_RESUMED'))"),
    'INSERT INTO events_v10 SELECT * FROM events',
    'DROP TABLE events',
    'ALTER TABLE events_v10 RENAME TO events',
    """CREATE TABLE debates_v10(
        debate_id TEXT PRIMARY KEY,spec_json TEXT NOT NULL CHECK(json_valid(spec_json)),
        revision INTEGER NOT NULL CHECK(revision>=0),
        checkpoint_event INTEGER REFERENCES events(sequence) DEFERRABLE INITIALLY DEFERRED,
        wait_state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(wait_state IN
        ('ACTIVE','WAITING_LOGIN','WAITING_DECISION','WAITING_JUDGE_SELECTION','READY_NEXT_ROUND','PAUSED','COMPLETED'))) STRICT""",
    'INSERT INTO debates_v10 SELECT * FROM debates',
    'DROP TABLE debates',
    'ALTER TABLE debates_v10 RENAME TO debates',
    """CREATE TABLE council_records(
        record_id TEXT PRIMARY KEY,debate_id TEXT NOT NULL REFERENCES debates(debate_id),
        round_id TEXT NOT NULL REFERENCES rounds(round_id),
        kind TEXT NOT NULL CHECK(kind IN ('ANALYSIS','JUDGE','FINAL')),
        record_json TEXT NOT NULL CHECK(json_valid(record_json)),
        record_hash TEXT NOT NULL CHECK(length(record_hash)=64),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence),
        UNIQUE(round_id,kind)) STRICT""",
)
V10_TABLES = V9_TABLES | {'council_records'}
