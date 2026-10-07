"""Add immutable architect candidates and a transactional user adoption record."""
from .schema_v2 import V2_STATEMENTS, V2_TABLES

V3_STATEMENTS = (
    next(sql for sql in V2_STATEMENTS if sql.startswith("CREATE TABLE events_v2(")).replace("events_v2", "events_v3").replace(
        "'RETRY_PREPARED'))", "'RETRY_PREPARED','QUESTION_ADOPTED'))"),
    "INSERT INTO events_v3 SELECT * FROM events",
    "DROP TABLE events",
    "ALTER TABLE events_v3 RENAME TO events",
    """CREATE TABLE architect_proposals(
        proposal_hash TEXT PRIMARY KEY CHECK(length(proposal_hash)=64),
        debate_id TEXT NOT NULL REFERENCES debates(debate_id),
        proposal_version INTEGER NOT NULL CHECK(proposal_version>=1),
        snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),
        proposal_json TEXT NOT NULL CHECK(json_valid(proposal_json)),
        source_revision INTEGER NOT NULL CHECK(source_revision>=0),
        checkpoint_sequence INTEGER NOT NULL REFERENCES events(sequence),
        UNIQUE(debate_id,proposal_version)) STRICT""",
    """CREATE TABLE question_adoptions(
        debate_id TEXT PRIMARY KEY REFERENCES debates(debate_id),
        proposal_hash TEXT NOT NULL REFERENCES architect_proposals(proposal_hash),
        user_action_id TEXT NOT NULL UNIQUE,
        actor TEXT NOT NULL CHECK(length(trim(actor))>0),
        adopted_json TEXT NOT NULL CHECK(json_valid(adopted_json)),
        event_sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence)) STRICT""",
)
V3_TABLES = V2_TABLES | {"architect_proposals", "question_adoptions"}
