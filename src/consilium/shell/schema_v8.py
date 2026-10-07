"""Append manual later-round acceptance; published V1-V7 SQL stays unchanged."""
from .schema_v7 import V7_STATEMENTS,V7_TABLES

V8_STATEMENTS=(
    V7_STATEMENTS[0].replace("events_v7","events_v8").replace(
        "'MANUAL_ANSWER_ACCEPTED'))","'MANUAL_ANSWER_ACCEPTED','MANUAL_ROUND_ACCEPTED'))"),
    "INSERT INTO events_v8 SELECT * FROM events",
    "DROP TABLE events",
    "ALTER TABLE events_v8 RENAME TO events",
    """CREATE TABLE manual_round_candidates(
        candidate_id TEXT PRIMARY KEY, candidate_hash TEXT NOT NULL UNIQUE CHECK(length(candidate_hash)=64),
        debate_id TEXT NOT NULL REFERENCES debates(debate_id), round_id TEXT NOT NULL REFERENCES rounds(round_id),
        participant_id TEXT NOT NULL, candidate_json TEXT NOT NULL CHECK(json_valid(candidate_json)),
        staged_revision INTEGER NOT NULL CHECK(staged_revision>=0),
        checkpoint_sequence INTEGER NOT NULL REFERENCES events(sequence)) STRICT""",
    """CREATE TABLE manual_round_acceptances(
        candidate_id TEXT PRIMARY KEY REFERENCES manual_round_candidates(candidate_id),
        round_id TEXT NOT NULL REFERENCES rounds(round_id),participant_id TEXT NOT NULL,
        user_action_id TEXT NOT NULL UNIQUE,record_json TEXT NOT NULL CHECK(json_valid(record_json)),
        record_hash TEXT NOT NULL CHECK(length(record_hash)=64),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence),UNIQUE(round_id,participant_id)) STRICT""",
)
V8_TABLES=V7_TABLES|{"manual_round_candidates","manual_round_acceptances"}
