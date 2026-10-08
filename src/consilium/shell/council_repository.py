"""SQLite implementation. SQL and private storage calls stay in this boundary."""
from consilium.core.contracts import ConnectionSpec, RoundSpec
from consilium.shell.storage import Conflict, _identifier


class SQLiteCouncilRepository:
    def __init__(self, store):
        self.store = store
        self.db = store._db

    @property
    def in_transaction(self):
        return self.db.in_transaction

    def transaction(self, *, write=True):
        return self.store._transaction(write=write)

    def require_revision(self, debate_id, revision):
        return self.store._checked_debate(debate_id, revision)

    def current_round(self, debate_id):
        row = self.db.execute('SELECT spec_json FROM rounds WHERE debate_id=? ORDER BY number DESC LIMIT 1',
                              (_identifier(debate_id),)).fetchone()
        return None if row is None else RoundSpec.model_validate_json(row[0])

    def round_spec(self, round_id):
        row = self.db.execute('SELECT spec_json FROM rounds WHERE round_id=?', (_identifier(round_id),)).fetchone()
        return None if row is None else RoundSpec.model_validate_json(row[0])

    def binding(self, debate_id, participant_id):
        row = self.db.execute('SELECT spec_json,revision FROM bindings WHERE debate_id=? AND participant_id=?',
                              (_identifier(debate_id), _identifier(participant_id))).fetchone()
        if row is None:
            raise Conflict('Participant has no registered connection')
        return ConnectionSpec.model_validate_json(row[0]), row[1]

    def wait_state(self, debate_id):
        return self.db.execute('SELECT wait_state FROM debates WHERE debate_id=?',
                               (_identifier(debate_id),)).fetchone()[0]

    def slot_exists(self, round_id, participant_id):
        return self.db.execute('SELECT 1 FROM operations WHERE round_id=? AND participant_id=?',
                               (_identifier(round_id), _identifier(participant_id))).fetchone() is not None

    def has_review(self, debate_id):
        return self.db.execute("SELECT 1 FROM rounds r JOIN council_records c USING(round_id) "
                               "WHERE r.debate_id=? AND c.kind='ANALYSIS' "
                               "AND json_extract(r.spec_json,'$.kind')='REVIEW'",
                               (_identifier(debate_id),)).fetchone() is not None

    def set_wait_state(self, debate_id, state):
        if state not in {'ACTIVE', 'WAITING_DECISION', 'COMPLETED'}:
            raise ValueError('Unsupported council state mutation')
        self.db.execute('UPDATE debates SET wait_state=? WHERE debate_id=?', (state, _identifier(debate_id)))

    def advance(self, debate_id, revision, kind, payload):
        return self.store._advance(debate_id, revision, kind, payload)

    def put(self, kind, record, revision, event_kind, record_id):
        round_id = record.round_id if hasattr(record, 'round_id') else record.synthesis_round.round_id
        cp = self.advance(record.debate_id, revision, event_kind,
                          {'record_id': str(record_id), 'round_id': str(round_id), 'record_hash': record.content_hash})
        self.db.execute('INSERT INTO council_records VALUES(?,?,?,?,?,?,?)',
                        (str(record_id), str(record.debate_id), str(round_id), kind,
                         self.store._public(record.model_dump(mode='json')), record.content_hash, cp.event_sequence))
        return cp

    def register_synthesis(self, spec):
        self.db.execute('INSERT INTO rounds VALUES(?,?,?,?)',
                        (str(spec.round_id), str(spec.debate_id), spec.number,
                         self.store._public(spec.model_dump(mode='json'))))

    def require_round_confirmed(self, debate_id, round_id):
        self.store.ledger._round_confirmed(debate_id, round_id)

    def record_and_events(self, kind, round_id, event_kind):
        row = self.db.execute('SELECT * FROM council_records WHERE round_id=? AND kind=?',
                              (_identifier(round_id), kind)).fetchone()
        marked = self.db.execute("SELECT * FROM events WHERE kind=? AND json_extract(payload_json,'$.round_id')=?",
                                 (event_kind, str(round_id))).fetchall()
        return row, marked

    def entries(self, debate_id=None):
        if debate_id is None:
            return self.db.execute('SELECT kind,round_id,event_sequence FROM council_records').fetchall()
        return self.db.execute('SELECT kind,round_id FROM council_records WHERE debate_id=? ORDER BY event_sequence',
                               (_identifier(debate_id),)).fetchall()

    def marked_events(self):
        return self.db.execute("SELECT * FROM events WHERE kind IN "
                               "('COUNCIL_ANALYZED','COUNCIL_JUDGE_SELECTED','COUNCIL_COMPLETED')").fetchall()

    def debate_states(self):
        return self.db.execute('SELECT debate_id,wait_state FROM debates').fetchall()

    def has_final(self, debate_id):
        return self.db.execute("SELECT 1 FROM council_records WHERE debate_id=? AND kind='FINAL'",
                               (str(debate_id),)).fetchone() is not None
