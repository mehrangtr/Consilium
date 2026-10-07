"""Durable manual review/answer acceptance; no provider, login or resend calls."""
import json
from uuid import UUID
from consilium.core.contracts import ConnectionSpec, GenerationParameters, RoundSpec
from consilium.core.manual_rounds import AcceptedManualRound, ManualRoundCandidate, ManualRoundFrame, manual_round_sources
from consilium.core.round_context import build_round_context
from consilium.shell.private import ensure_public_payload
from consilium.shell.storage import Conflict, SchemaError, _identifier, _revision

class ManualRoundLedger:

    def __init__(self, store):
        self.store, self._db = (store, store._db)

    def _frame(self, *, round_spec, participant_id, connection, connection_revision, revision, grants, parameters, named_authorization=None, rubric_version='manual-rubric.v1', max_context_bytes=1048576):
        question = self.store.questions.get_adopted(round_spec.debate_id)
        if question is None:
            raise Conflict('Manual round requires an adopted question')
        sources = tuple((s for s in self.store.sources.context_sources(round_spec.debate_id, through_revision=revision) if s.source_round.number < round_spec.number))
        decision = self.store.admissions.continuation_for(round_spec)
        for value in (question, decision, *sources):
            ensure_public_payload(value.model_dump(mode='json'), self.store._forbidden_values)
        context = build_round_context(question=question, debate=self.store.get_debate(round_spec.debate_id), round_spec=round_spec, participant_id=participant_id, expected_revision=revision, sources=sources, required_source_hashes=tuple((s.content_hash for s in sources)), grants=grants, connection=connection, parameters=parameters, named_authorization=named_authorization, continuation_decision=decision)
        return ManualRoundFrame(round_spec=round_spec, participant_id=participant_id, connection=connection, connection_revision=connection_revision, context=context, sources=sources, grants=grants, continuation_decision=decision, named_authorization=named_authorization, rubric_version=rubric_version, max_context_bytes=max_context_bytes)

    def _validate_frame(self, frame):
        row = self._db.execute('SELECT spec_json FROM rounds WHERE round_id=? AND debate_id=?', (str(frame.round_spec.round_id), str(frame.round_spec.debate_id))).fetchone()
        if row is None or RoundSpec.model_validate_json(row[0]) != frame.round_spec:
            raise Conflict('Manual frame differs from its registered round')
        expected = self._frame(round_spec=frame.round_spec, participant_id=frame.participant_id, connection=frame.connection, connection_revision=frame.connection_revision, revision=frame.staged_revision, grants=frame.grants, parameters=frame.context.frozen_input.parameters, named_authorization=frame.named_authorization, rubric_version=frame.rubric_version, max_context_bytes=frame.max_context_bytes)
        if expected != frame:
            raise Conflict('Manual frame differs from the canonical historical view')

    def prepare_context(self, *, debate_id, round_id, participant_id, expected_revision, grants, parameters=None, named_authorization=None, rubric_version='manual-rubric.v1', max_context_bytes=1048576):
        with self.store._transaction(write=False):
            self.store._checked_debate(debate_id, expected_revision)
            _identifier(participant_id)
            row = self._db.execute('SELECT spec_json FROM rounds WHERE debate_id=? AND round_id=?', (str(debate_id), str(round_id))).fetchone()
            binding = self._db.execute('SELECT spec_json,revision FROM bindings WHERE debate_id=? AND participant_id=?', (str(debate_id), str(participant_id))).fetchone()
            if row is None or binding is None:
                raise Conflict('Manual round and binding must be registered')
            frame = self._frame(round_spec=RoundSpec.model_validate_json(row[0]), participant_id=participant_id, connection=ConnectionSpec.model_validate_json(binding[0]), connection_revision=binding[1], revision=expected_revision, grants=grants, parameters=parameters or GenerationParameters(), named_authorization=named_authorization, rubric_version=rubric_version, max_context_bytes=max_context_bytes)
            self.store.manual_sources._current(frame, expected_revision)
            return frame

    def stage(self, *, candidate_id, frame, actual_prompt, round_seen, content, expected_revision, claimed_origin=None, data_class='PRIVATE'):
        _identifier(candidate_id)
        frame = ManualRoundFrame.model_validate(frame)
        with self.store._transaction():
            self.store.manual_sources._current(frame, expected_revision)
            if frame.staged_revision != expected_revision:
                raise Conflict('Manual frame revision changed')
            self._validate_frame(frame)
            candidate = ManualRoundCandidate(candidate_id=candidate_id, frame=frame, actual_prompt=actual_prompt, round_seen=round_seen, content=content, claimed_origin=claimed_origin, data_class=data_class)
            for source in manual_round_sources(candidate, expected_revision + 1):
                ensure_public_payload(source.model_dump(mode='json'), self.store._forbidden_values)
            public = self.store._public(candidate.model_dump(mode='json'))
            cp = self.store.checkpoint(frame.round_spec.debate_id)
            self._db.execute('INSERT INTO manual_round_candidates VALUES(?,?,?,?,?,?,?,?)', (str(candidate_id), candidate.content_hash, str(frame.round_spec.debate_id), str(frame.round_spec.round_id), str(frame.participant_id), public, expected_revision, cp.event_sequence))
            return candidate

    def get_candidate(self, candidate_id):
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get_candidate(candidate_id)
        row = self._db.execute('SELECT * FROM manual_round_candidates WHERE candidate_id=?', (_identifier(candidate_id),)).fetchone()
        if row is None:
            raise Conflict('Manual round candidate is not registered')
        try:
            candidate = ManualRoundCandidate.model_validate_json(row['candidate_json'])
            event = self._db.execute('SELECT debate_id,revision FROM events WHERE sequence=?', (row['checkpoint_sequence'],)).fetchone()
            if str(candidate.candidate_id) != row['candidate_id'] or candidate.content_hash != row['candidate_hash'] or (str(candidate.round_spec.debate_id), str(candidate.round_spec.round_id), str(candidate.participant_id)) != (row['debate_id'], row['round_id'], row['participant_id']) or (candidate.staged_revision != row['staged_revision']) or (event is None) or (tuple(event) != (row['debate_id'], row['staged_revision'])):
                raise ValueError('Candidate snapshot mismatch')
            self._validate_frame(candidate.frame)
            return candidate
        except (ValueError, TypeError, KeyError, RecursionError):
            raise SchemaError('Stored manual round candidate is inconsistent') from None

    def review_snapshot(self, candidate_id, *, expected_revision):
        with self.store._transaction(write=False):
            candidate = self.get_candidate(candidate_id)
            self.store.manual_sources._current(candidate, expected_revision)
            if candidate.staged_revision != expected_revision or self.get(candidate_id) is not None:
                raise Conflict('Manual round candidate is stale or already accepted')
            return candidate

    @staticmethod
    def _payload(record):
        return {'candidate_id': str(record.candidate.candidate_id), 'candidate_hash': record.candidate_hash, 'record_hash': record.content_hash, 'user_action_id': str(record.trusted_user_action_id), 'actor': record.actor, 'alignment': record.alignment, 'external_origin_verified': False}

    def accept(self, candidate_id, *, candidate_hash, user_action_id, actor, confirmed, expected_revision):
        if confirmed is not True or type(actor) is not str or (not actor.strip()):
            raise ValueError('Explicit local manual-round acceptance is required')
        _identifier(user_action_id)
        with self.store._transaction():
            candidate = self.get_candidate(candidate_id)
            self.store.manual_sources._current(candidate, expected_revision)
            if candidate.staged_revision != expected_revision or candidate.content_hash != candidate_hash or self.get(candidate_id) is not None:
                raise Conflict('Manual round content or revision changed')
            record = AcceptedManualRound(candidate=candidate, candidate_hash=candidate.content_hash, trusted_user_action_id=user_action_id, actor=actor, accepted_revision=expected_revision + 1, alignment=candidate.alignment, sources=manual_round_sources(candidate, expected_revision + 1))
            public = self.store._public(record.model_dump(mode='json'))
            cp = self.store._advance(candidate.round_spec.debate_id, expected_revision, 'MANUAL_ROUND_ACCEPTED', self._payload(record))
            self._db.execute('INSERT INTO manual_round_acceptances VALUES(?,?,?,?,?,?,?)', (str(candidate_id), str(candidate.round_spec.round_id), str(candidate.participant_id), str(user_action_id), public, record.content_hash, cp.event_sequence))
            return record

    def get(self, candidate_id):
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get(candidate_id)
        row = self._db.execute('SELECT * FROM manual_round_acceptances WHERE candidate_id=?', (_identifier(candidate_id),)).fetchone()
        if row is None:
            if self._db.execute("SELECT 1 FROM events WHERE kind='MANUAL_ROUND_ACCEPTED' AND json_extract(payload_json,'$.candidate_id')=?", (str(candidate_id),)).fetchone():
                raise SchemaError('Accepted manual round was removed')
            return None
        try:
            record = AcceptedManualRound.model_validate_json(row['record_json'])
            event = self._db.execute('SELECT * FROM events WHERE sequence=?', (row['event_sequence'],)).fetchone()
            if record.candidate != self.get_candidate(candidate_id) or record.content_hash != row['record_hash'] or (str(record.candidate.round_spec.round_id), str(record.candidate.participant_id), str(record.trusted_user_action_id)) != (row['round_id'], row['participant_id'], row['user_action_id']) or (event is None) or ((event['debate_id'], event['revision'], event['kind']) != (str(record.candidate.round_spec.debate_id), record.accepted_revision, 'MANUAL_ROUND_ACCEPTED')) or (json.loads(event['payload_json']) != self._payload(record)):
                raise ValueError('Manual acceptance graph mismatch')
            return record
        except (ValueError, TypeError, KeyError, RecursionError):
            raise SchemaError('Stored manual round acceptance is inconsistent') from None

    def for_debate(self, debate_id, *, through_revision=None):
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.for_debate(debate_id, through_revision=through_revision)
        self.store.checkpoint(debate_id)
        sql = "SELECT payload_json FROM events WHERE debate_id=? AND kind='MANUAL_ROUND_ACCEPTED'"
        args = [_identifier(debate_id)]
        if through_revision is not None:
            sql += ' AND revision<=?'
            args.append(_revision(through_revision))
        rows = self._db.execute(sql + ' ORDER BY sequence', args).fetchall()
        return tuple((self.get(UUID(json.loads(row[0])['candidate_id'])) for row in rows))

    def export_fields(self, debate_id):
        rows = self._db.execute('SELECT candidate_id FROM manual_round_candidates WHERE debate_id=? ORDER BY rowid', (_identifier(debate_id),)).fetchall()
        return {'manual_round_candidates': [self.get_candidate(UUID(row[0])).model_dump(mode='json') for row in rows], 'accepted_manual_rounds': [r.model_dump(mode='json') for r in self.for_debate(debate_id)]}

    def check_integrity(self):
        for row in self._db.execute('SELECT candidate_id FROM manual_round_candidates').fetchall():
            self.get_candidate(UUID(row[0]))
        for row in self._db.execute('SELECT candidate_id FROM manual_round_acceptances').fetchall():
            self.get(UUID(row[0]))
        actual = {(r[0], r[1]) for r in self._db.execute('SELECT candidate_id,event_sequence FROM manual_round_acceptances')}
        marked = {(json.loads(r[1])['candidate_id'], r[0]) for r in self._db.execute("SELECT sequence,payload_json FROM events WHERE kind='MANUAL_ROUND_ACCEPTED'")}
        if actual != marked:
            raise SchemaError('Manual round acceptance events and records differ')
