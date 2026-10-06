"""Append-only migration from the published V1 storage schema."""
EVENT_KINDS = (
    "DEBATE_CREATED", "ROUND_REGISTERED", "CONNECTION_BOUND", "OPERATION_PREPARED",
    "SEND_STARTED", "SEND_INTERRUPTED", "RESULT_RECORDED", "RESULT_REJECTED",
    "RESPONSE_VALIDATED", "RESULT_CONFIRMED", "WAITING_DECISION", "USER_DECISION", "RETRY_PREPARED",
)
V2_STATEMENTS = (
    """CREATE TABLE attempts_v2(
        attempt_id TEXT PRIMARY KEY, logical_operation_id TEXT NOT NULL REFERENCES operations(logical_operation_id),
        state TEXT NOT NULL CHECK(state IN ('PREPARED','SENT','UNKNOWN_DELIVERY','RESPONSE_PENDING',
            'RESPONSE_RECEIVED','PARTIAL_RESPONSE','INVALID_RESPONSE','NOT_SENT','WAITING_LOGIN','VALIDATED','CONFIRMED')),
        intent_json TEXT NOT NULL CHECK(json_valid(intent_json)), active_revision INTEGER NOT NULL CHECK(active_revision>=1),
        request_json TEXT CHECK(request_json IS NULL OR json_valid(request_json)),
        validation_json TEXT CHECK(validation_json IS NULL OR json_valid(validation_json))) STRICT""",
    """INSERT INTO attempts_v2 SELECT attempt_id,logical_operation_id,state,intent_json,
        (SELECT revision FROM events WHERE kind='OPERATION_PREPARED'
            AND json_extract(payload_json,'$.attempt_id')=attempts.attempt_id),NULL,NULL FROM attempts""",
    "DROP TABLE attempts",
    "ALTER TABLE attempts_v2 RENAME TO attempts",
    """CREATE TABLE events_v2(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, debate_id TEXT NOT NULL REFERENCES debates(debate_id),
        revision INTEGER NOT NULL CHECK(revision>=0), kind TEXT NOT NULL CHECK(kind IN
            ('DEBATE_CREATED','ROUND_REGISTERED','CONNECTION_BOUND','OPERATION_PREPARED','SEND_STARTED',
             'SEND_INTERRUPTED','RESULT_RECORDED','RESULT_REJECTED','RESPONSE_VALIDATED','RESULT_CONFIRMED',
             'WAITING_DECISION','USER_DECISION','RETRY_PREPARED')),
        payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), created_at TEXT NOT NULL,
        UNIQUE(debate_id,revision)) STRICT""",
    "INSERT INTO events_v2 SELECT * FROM events",
    "DROP TABLE events",
    "ALTER TABLE events_v2 RENAME TO events",
    """ALTER TABLE debates ADD COLUMN wait_state TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK(wait_state IN ('ACTIVE','WAITING_LOGIN','WAITING_DECISION','WAITING_JUDGE_SELECTION','READY_NEXT_ROUND','PAUSED'))""",
    """CREATE TABLE transport_results(
        attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id), result_json TEXT NOT NULL CHECK(json_valid(result_json)),
        result_hash TEXT NOT NULL CHECK(length(result_hash)=64), recorded_revision INTEGER NOT NULL CHECK(recorded_revision>=1),
        event_sequence INTEGER NOT NULL REFERENCES events(sequence)) STRICT""",
    """CREATE TABLE canonical_results(
        logical_operation_id TEXT PRIMARY KEY REFERENCES operations(logical_operation_id),
        attempt_id TEXT NOT NULL UNIQUE REFERENCES transport_results(attempt_id),
        confirmed_revision INTEGER NOT NULL CHECK(confirmed_revision>=1),
        event_sequence INTEGER NOT NULL REFERENCES events(sequence)) STRICT""",
    """CREATE TABLE rejected_results(
        rejection_id INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
        result_json TEXT NOT NULL CHECK(json_valid(result_json)), result_hash TEXT NOT NULL CHECK(length(result_hash)=64),
        reason TEXT NOT NULL CHECK(reason IN ('STALE_RESULT','RESULT_CONFLICT')),
        event_sequence INTEGER NOT NULL REFERENCES events(sequence), UNIQUE(attempt_id,result_hash,reason)) STRICT""",
    """CREATE TABLE user_decisions(
        decision_id TEXT PRIMARY KEY, debate_id TEXT NOT NULL REFERENCES debates(debate_id),
        round_id TEXT NOT NULL REFERENCES rounds(round_id), decision_json TEXT NOT NULL CHECK(json_valid(decision_json)),
        actor TEXT NOT NULL CHECK(length(trim(actor))>0), event_sequence INTEGER NOT NULL REFERENCES events(sequence)) STRICT""",
    """CREATE TABLE retry_authorizations(
        previous_attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),
        next_attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
        authorization_json TEXT NOT NULL CHECK(json_valid(authorization_json)),
        event_sequence INTEGER NOT NULL REFERENCES events(sequence)) STRICT""",
)
V2_TABLES = {"schema_migrations", "debates", "rounds", "bindings", "operations", "attempts", "events",
             "transport_results", "canonical_results", "rejected_results", "user_decisions", "retry_authorizations"}
