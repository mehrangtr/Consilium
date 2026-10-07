"""Append manual-source acceptance without changing published migration checksums."""
from .schema_v6 import V6_STATEMENTS, V6_TABLES

V7_STATEMENTS = (
    V6_STATEMENTS[0].replace("events_v6", "events_v7").replace(
        "'SOURCE_BATCH_PUBLISHED'))", "'SOURCE_BATCH_PUBLISHED','MANUAL_ANSWER_ACCEPTED'))"),
    "INSERT INTO events_v7 SELECT * FROM events",
    "DROP TABLE events",
    "ALTER TABLE events_v7 RENAME TO events",
    """CREATE TABLE manual_answer_candidates(
        candidate_id TEXT PRIMARY KEY, candidate_hash TEXT NOT NULL UNIQUE CHECK(length(candidate_hash)=64),
        debate_id TEXT NOT NULL REFERENCES debates(debate_id), round_id TEXT NOT NULL REFERENCES rounds(round_id),
        participant_id TEXT NOT NULL, candidate_json TEXT NOT NULL CHECK(json_valid(candidate_json)),
        staged_revision INTEGER NOT NULL CHECK(staged_revision>=0),
        checkpoint_sequence INTEGER NOT NULL REFERENCES events(sequence)) STRICT""",
    """CREATE TABLE manual_answer_acceptances(
        candidate_id TEXT PRIMARY KEY REFERENCES manual_answer_candidates(candidate_id),
        round_id TEXT NOT NULL REFERENCES rounds(round_id), participant_id TEXT NOT NULL,
        user_action_id TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL CHECK(json_valid(record_json)),
        record_hash TEXT NOT NULL CHECK(length(record_hash)=64),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence), UNIQUE(round_id,participant_id)) STRICT""",
)
V7_TABLES = V6_TABLES | {"manual_answer_candidates", "manual_answer_acceptances"}
