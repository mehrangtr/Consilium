"""Durable serial offline council built on the existing operation and manual ledgers.

Model content is data. Only explicit local user actions decide continuation and
select the judge. Recovery reads canonical state and never resends a request.
"""
import json
from uuid import UUID, uuid4, uuid5

from consilium.core.artifact_contracts import ArtifactResponseContract, ReviewTarget, decode_response_json
from consilium.core.contracts import (AdapterRequest, Answer, ConnectionSpec, Critique, GenerationParameters,
    OperationIdentity, OperationIntent, RoundSpec, UserDecision)
from consilium.core.council_contracts import FinalCouncilResult, JudgeOutput, Objection, RoundAnalysis, SelectedJudge
from consilium.core.context_observations import HistorySnapshot
from consilium.core.dispatch_policy import PrivacyDecision, destination_hash
from consilium.core.independent_context import build_independent_context
from consilium.core.operation_states import AttemptState
from consilium.core.round_context import JudgeSelection, TransferGrant, build_round_context
from consilium.shell.storage import Conflict, SchemaError, _identifier


class Council:
    def __init__(self, store):
        self.store, self._db = store, store._db

    @staticmethod
    def _explicit(actor, confirmed):
        if confirmed is not True or type(actor) is not str or not actor.strip() or actor.upper() in {'SYSTEM', 'MODEL', 'ANALYST', 'JUDGE'}:
            raise ValueError('An explicit local user action is required')

    def revision(self, debate_id): return self.store.checkpoint(debate_id).revision

    def current_round(self, debate_id):
        row = self._db.execute('SELECT spec_json FROM rounds WHERE debate_id=? ORDER BY number DESC LIMIT 1', (_identifier(debate_id),)).fetchone()
        return None if row is None else RoundSpec.model_validate_json(row[0])

    def binding(self, debate_id, participant_id):
        row = self._db.execute('SELECT spec_json,revision FROM bindings WHERE debate_id=? AND participant_id=?',
                               (_identifier(debate_id), _identifier(participant_id))).fetchone()
        if row is None: raise Conflict('Participant has no registered connection')
        return ConnectionSpec.model_validate_json(row[0]), row[1]

    def _wait(self, debate_id):
        return self._db.execute('SELECT wait_state FROM debates WHERE debate_id=?', (_identifier(debate_id),)).fetchone()[0]

    def start_round(self, *, debate_id, round_id, kind, expected_revision, targets=(), participant_ids=None):
        with self.store._transaction():
            debate = self.store._checked_debate(debate_id, expected_revision)
            if self.store.questions.get_adopted(debate_id) is None or len(debate.participant_ids) < 2:
                raise Conflict('A council requires an adopted question and at least two participants')
            previous = self.current_round(debate_id)
            if kind == 'SYNTHESIS': raise Conflict('Only explicit judge selection starts synthesis')
            if previous is None and kind != 'INDEPENDENT' or previous is not None and kind == 'INDEPENDENT':
                raise Conflict('Independent answers are the first round only')
            if previous is not None and self.get('ANALYSIS', previous.round_id) is None:
                raise Conflict('Analyze and complete the previous round before continuing')
            if kind in {'INDEPENDENT', 'REVIEW'} and participant_ids is not None and len(participant_ids) < 2:
                raise Conflict('Independent and peer review rounds require at least two participants')
            spec = RoundSpec(round_id=round_id, debate_id=debate_id, number=1 if previous is None else previous.number+1,
                kind=kind, participant_ids=participant_ids or debate.participant_ids, targets=targets)
            # register_round owns its transaction; leave this read/guard transaction
            # first, then repeat its revision guard atomically at the write boundary.
        self.store.register_round(spec, expected_revision=expected_revision)
        return spec

    def _sources(self, round_spec, revision):
        return tuple(s for s in self.store.sources.context_sources(round_spec.debate_id, through_revision=revision)
                     if s.source_round.number < round_spec.number)

    def grants(self, round_spec, participant_id, revision, user_action_id):
        _identifier(user_action_id)
        connection, _ = self.binding(round_spec.debate_id, participant_id)
        return tuple(TransferGrant(source_hash=s.content_hash, destination_hash=destination_hash(connection),
            ledger_revision=revision, decision='ALLOW', trusted_user_action_id=user_action_id) for s in self._sources(round_spec, revision))

    def authorization(self, round_spec, revision):
        selected = self.get('JUDGE', round_spec.round_id)
        if selected is None or selected.synthesis_round != round_spec or revision < selected.selected_revision:
            raise Conflict('No matching durable user judge selection')
        return JudgeSelection(debate_id=round_spec.debate_id, participant_id=selected.participant_id,
            destination_hash=destination_hash(selected.connection), ledger_revision=revision,
            trusted_user_action_id=selected.user_action_id)

    def prepare_mock(self, *, debate_id, participant_id, identity, expected_revision, user_action_id, actor, confirmed,
                     named_authorization=None, parameters=None):
        self._explicit(actor, confirmed)
        _identifier(user_action_id)
        parameters = parameters or GenerationParameters(max_output_tokens=256)
        with self.store._transaction(write=False):
            self.store._checked_debate(debate_id, expected_revision)
            round_spec = self.current_round(debate_id)
            if round_spec is None or participant_id not in round_spec.participant_ids or self._wait(debate_id) != 'ACTIVE':
                raise Conflict('No active council slot')
            if self._db.execute('SELECT 1 FROM operations WHERE round_id=? AND participant_id=?',
                                (str(round_spec.round_id), str(participant_id))).fetchone():
                raise Conflict('Resume the existing operation; do not create another slot')
            if any(s.source_round.round_id == round_spec.round_id and
                   (s.item.participant_id if isinstance(s.item, Answer) else s.item.reviewer_id) == participant_id
                   for s in self.store.sources.context_sources(debate_id)):
                raise Conflict('This slot already has a canonical contribution')
            connection, binding_revision = self.binding(debate_id, participant_id)
            if connection.provider_id != 'mock' or connection.model_id != 'mock-v1' or connection.mode not in {'API', 'BROWSER'}:
                raise Conflict('P05 permits the declared offline mock driver only')
            question = self.store.questions.get_adopted(debate_id)
            grants, sources, judge = (), (), None
            if round_spec.kind == 'INDEPENDENT':
                context = build_independent_context(question=question, round_spec=round_spec, participant_id=participant_id,
                    revision=question.adoption.adopted_revision, parameters=parameters)
            else:
                sources = self._sources(round_spec, expected_revision)
                grants = self.grants(round_spec, participant_id, expected_revision, user_action_id)
                judge = self.authorization(round_spec, expected_revision) if round_spec.kind == 'SYNTHESIS' else None
                context = build_round_context(question=question, debate=self.store.get_debate(debate_id), round_spec=round_spec,
                    participant_id=participant_id, expected_revision=expected_revision, sources=sources,
                    required_source_hashes=tuple(s.content_hash for s in sources), grants=grants, connection=connection,
                    parameters=parameters, continuation_decision=self.store.admissions.continuation_for(round_spec),
                    judge_selection=judge, named_authorization=named_authorization)
            targets = ()
            if round_spec.kind == 'REVIEW':
                latest = {}
                for s in sources:
                    if isinstance(s.item, Answer) and s.item.participant_id != participant_id:
                        old = latest.get(s.item.participant_id)
                        if old is None or (s.source_round.number, s.source_revision) > (old.source_round.number, old.source_revision):
                            latest[s.item.participant_id] = s
                projected = json.loads(context.frozen_input.messages[1].content)['sources']
                aliases = {r['source_hash']: r['author'] for r in projected if r['kind'] == 'ANSWER'}
                targets = tuple(ReviewTarget(alias=aliases[s.content_hash], logical_operation_id=s.item.logical_operation_id,
                    answer_id=s.item.answer_id, source_hash=s.content_hash) for s in sorted(latest.values(), key=lambda s: str(s.item.participant_id)))
            intent = OperationIntent(identity=identity, debate_id=debate_id, round_id=round_spec.round_id,
                participant_id=participant_id, connection_id=connection.connection_id, connection_revision=binding_revision,
                expected_revision=expected_revision, frozen_input=context.frozen_input, request_hash=context.frozen_input.content_hash)
            output = ArtifactResponseContract(logical_operation_id=identity.logical_operation_id, round_spec=round_spec,
                participant_id=participant_id, request_hash=intent.request_hash,
                kind='CRITIQUES' if round_spec.kind == 'REVIEW' else 'ANSWER', targets=targets,
                rubric_version='council-rubric.v1' if targets else None)
            privacy = PrivacyDecision(view_hash=context.content_hash, request_hash=intent.request_hash,
                destination_hash=destination_hash(connection), ledger_revision=expected_revision,
                decision='ALLOW', contains_secret=False, trusted_user_action_id=user_action_id)
        from consilium.shell.context_observers import observe_context
        receipt, budget, history = observe_context(store=self.store, context=context, connection=connection,
            expected_revision=expected_revision, expected_connection_revision=binding_revision, privacy=privacy,
            snapshot=HistorySnapshot(debate_id=debate_id, destination_hash=destination_hash(connection),
                conversation_id=None, complete=True, entries=()), new_topic=round_spec.number == 1,
            preference='PREFER_CURRENT', user_action_id=None, grants=grants,
            judge_selection=judge, named_authorization=named_authorization)
        from consilium.core.round_admission import ObservedAdmissionBundle, ObservedRoundAdmissionBundle
        from consilium.core.dispatch_policy import evaluate_dispatch_policy, evaluate_round_dispatch_policy
        common = dict(context=context, connection=connection, connection_revision=binding_revision,
                      privacy=privacy, budget=budget, history=history, observation=receipt)
        if round_spec.kind == 'INDEPENDENT':
            bundle = ObservedAdmissionBundle(**common, admission=evaluate_dispatch_policy(context=context,
                connection=connection, privacy=privacy, budget=budget, history=history, expected_revision=expected_revision))
        else:
            bundle = ObservedRoundAdmissionBundle(**common, sources=sources,
                required_source_hashes=tuple(s.content_hash for s in sources), grants=grants,
                continuation_decision=self.store.admissions.continuation_for(round_spec), judge_selection=judge,
                named_authorization=named_authorization, admission=evaluate_round_dispatch_policy(context=context,
                connection=connection, privacy=privacy, budget=budget, history=history, expected_revision=expected_revision))
        self.store.prepare_intent(intent, admission_bundle=bundle, response_contract=output)
        return AdapterRequest(intent=intent, connection=connection, timeout_seconds=10.0)

    def execute_mock(self, request, adapter, *, expected_revision):
        from consilium.adapters.mock import MockAdapter
        from consilium.shell.runner import DurableRunner
        if type(adapter) is not MockAdapter:
            raise Conflict('P05 cannot invoke an external or subclassed driver')
        plan = DurableRunner(self.store).execute(request, adapter, expected_revision=expected_revision)
        if plan.attempt.state == AttemptState.CONFIRMED:
            self.publish_confirmed(request.intent.identity.logical_operation_id, expected_revision=self.revision(request.intent.debate_id))
        return self.store.ledger.resume(request.intent.identity.attempt_id)

    def publish_confirmed(self, operation_id, *, expected_revision):
        return self.store.artifacts.publish(operation_id, expected_revision=expected_revision)

    def _analyze(self, round_spec, revision):
        sources = self.store.sources.context_sources(round_spec.debate_id, through_revision=revision)
        current = tuple(s for s in sources if s.source_round.round_id == round_spec.round_id)
        authors = {s.item.participant_id if isinstance(s.item, Answer) else s.item.reviewer_id for s in current}
        if authors != set(round_spec.participant_ids):
            raise Conflict('Round analysis requires every canonical participant contribution')
        objections = []
        for s in sources:
            if isinstance(s.item, Critique):
                for i, point in enumerate(s.item.points):
                    if point.verdict != 'ACCEPT':
                        objections.append(Objection(issue_id=uuid5(s.item.critique_id, str(i)), source_hash=s.content_hash,
                            reference=point.reference, reason=point.reason, verdict=point.verdict))
        independent = tuple(s for s in sources if isinstance(s.item, Answer) and s.source_round.kind == 'INDEPENDENT')
        if len({s.item.content for s in independent}) > 1:
            for s in independent:
                objections.append(Objection(issue_id=uuid5(s.item.answer_id, 'reported-difference'), source_hash=s.content_hash,
                    reference='INDEPENDENT_ANSWER_DIFFERENCE', reason=s.item.content, verdict='DIFFERENT_ANSWERS'))
        return RoundAnalysis(debate_id=round_spec.debate_id, round_id=round_spec.round_id, input_revision=revision,
            source_hashes=tuple(s.content_hash for s in sources), objections=tuple(objections),
            recommendation='REVIEW' if round_spec.kind == 'INDEPENDENT' else 'TARGETED' if objections else 'FINISH')

    def _put(self, kind, record, revision, event_kind, record_id):
        cp = self.store._advance(record.debate_id, revision, event_kind, {'record_id': str(record_id),
            'round_id': str(record.round_id if hasattr(record, 'round_id') else record.synthesis_round.round_id),
            'record_hash': record.content_hash})
        round_id = record.round_id if hasattr(record, 'round_id') else record.synthesis_round.round_id
        self._db.execute('INSERT INTO council_records VALUES(?,?,?,?,?,?,?)', (str(record_id), str(record.debate_id),
            str(round_id), kind, self.store._public(record.model_dump(mode='json')), record.content_hash, cp.event_sequence))
        return cp

    def seal_round(self, *, debate_id, expected_revision):
        with self.store._transaction():
            self.store._checked_debate(debate_id, expected_revision)
            spec = self.current_round(debate_id)
            if spec is None or spec.kind == 'SYNTHESIS' or self._wait(debate_id) != 'ACTIVE':
                raise Conflict('Only an active normal round can enter a decision gate')
            self.store.ledger._round_confirmed(debate_id, spec.round_id)
            analysis = self._analyze(spec, expected_revision)
            cp = self._put('ANALYSIS', analysis, expected_revision, 'COUNCIL_ANALYZED', uuid5(spec.round_id, 'analysis'))
            self._db.execute("UPDATE debates SET wait_state='WAITING_DECISION' WHERE debate_id=?", (str(debate_id),))
            return analysis

    def decide(self, decision, *, actor, confirmed):
        self._explicit(actor, confirmed)
        spec = self.current_round(decision.debate_id)
        if spec is None or spec.kind == 'SYNTHESIS' or self.get('ANALYSIS', spec.round_id) is None:
            raise Conflict('Decisions require the analyzed current normal round')
        if decision.kind == 'FINISH' and not self._db.execute(
            "SELECT 1 FROM rounds r JOIN council_records c USING(round_id) WHERE r.debate_id=? "
            "AND c.kind='ANALYSIS' AND json_extract(r.spec_json,'$.kind')='REVIEW'",
            (str(decision.debate_id),)).fetchone():
            raise Conflict('Finish requires a completed peer review before judge selection')
        return self.store.ledger.record_decision(decision, actor=actor)

    def resume_pause(self, *, debate_id, expected_revision, user_action_id, actor, confirmed):
        self._explicit(actor, confirmed); _identifier(user_action_id)
        with self.store._transaction():
            self.store._checked_debate(debate_id, expected_revision)
            if self._wait(debate_id) != 'PAUSED': raise Conflict('Debate is not paused')
            self._db.execute("UPDATE debates SET wait_state='WAITING_DECISION' WHERE debate_id=?", (str(debate_id),))
            return self.store._advance(debate_id, expected_revision, 'COUNCIL_RESUMED',
                                      {'user_action_id': str(user_action_id), 'actor': actor})

    def select_judge(self, *, debate_id, participant_id, round_id, expected_revision, user_action_id, actor, confirmed,
                     bias_mitigation='BLIND_ALL_EVIDENCE_WITH_DISSENT'):
        self._explicit(actor, confirmed); _identifier(user_action_id)
        with self.store._transaction():
            debate = self.store._checked_debate(debate_id, expected_revision)
            old = self.current_round(debate_id)
            if self._wait(debate_id) != 'WAITING_JUDGE_SELECTION' or old is None or participant_id not in debate.participant_ids:
                raise Conflict('Finish and valid explicit judge selection are required')
            if not self._db.execute("SELECT 1 FROM rounds r JOIN council_records c USING(round_id) "
                                    "WHERE r.debate_id=? AND c.kind='ANALYSIS' AND json_extract(r.spec_json,'$.kind')='REVIEW'",
                                    (str(debate_id),)).fetchone():
                raise Conflict('A completed peer review is required before final synthesis')
            connection, binding_revision = self.binding(debate_id, participant_id)
            spec = RoundSpec(round_id=round_id, debate_id=debate_id, number=old.number+1, kind='SYNTHESIS', participant_ids=(participant_id,))
            sources = self.store.sources.context_sources(debate_id, through_revision=expected_revision)
            participation = tuple(dict.fromkeys(s.source_round.round_id for s in sources if
                (s.item.participant_id if isinstance(s.item, Answer) else s.item.reviewer_id) == participant_id))
            selected = SelectedJudge(debate_id=debate_id, previous_round_id=old.round_id, synthesis_round=spec,
                participant_id=participant_id, connection=connection, connection_revision=binding_revision,
                selected_revision=expected_revision+1, user_action_id=user_action_id, actor=actor,
                participated_in_rounds=participation, bias_mitigation=bias_mitigation)
            self._db.execute('INSERT INTO rounds VALUES(?,?,?,?)', (str(round_id), str(debate_id), spec.number, self.store._public(spec.model_dump(mode='json'))))
            self._put('JUDGE', selected, expected_revision, 'COUNCIL_JUDGE_SELECTED', user_action_id)
            self._db.execute("UPDATE debates SET wait_state='ACTIVE' WHERE debate_id=?", (str(debate_id),))
            return selected

    def _final(self, spec, revision):
        selected = self.get('JUDGE', spec.round_id)
        if selected is None: raise Conflict('No selected judge')
        sources = self.store.sources.context_sources(spec.debate_id, through_revision=revision)
        finals = [s for s in sources if s.source_round.round_id == spec.round_id and isinstance(s.item, Answer)]
        if len(finals) != 1 or finals[0].item.participant_id != selected.participant_id:
            raise Conflict('Only the selected judge canonical answer can finish')
        clean = decode_response_json(finals[0].item.content, 262144)
        output = JudgeOutput.model_validate_json(clean)
        analysis = self.get('ANALYSIS', selected.previous_round_id)
        if analysis is None: raise Conflict('Final synthesis lacks the previous analysis')
        return FinalCouncilResult(debate_id=spec.debate_id, round_id=spec.round_id, judge=selected,
            judge_source_hash=finals[0].content_hash, input_source_hashes=tuple(s.content_hash for s in sources if s.source_round.number < spec.number),
            output=output, preserved_objections=analysis.objections, completed_revision=revision+1)

    def finalize(self, *, debate_id, expected_revision):
        with self.store._transaction():
            self.store._checked_debate(debate_id, expected_revision)
            spec = self.current_round(debate_id)
            if spec is None or spec.kind != 'SYNTHESIS' or self._wait(debate_id) != 'ACTIVE':
                raise Conflict('A selected active synthesis is required')
            selected = self.get('JUDGE', spec.round_id)
            if self.binding(debate_id, selected.participant_id) != (selected.connection, selected.connection_revision):
                raise Conflict('Judge binding changed; no silent replacement')
            self.store.ledger._round_confirmed(debate_id, spec.round_id)
            result = self._final(spec, expected_revision)
            self._put('FINAL', result, expected_revision, 'COUNCIL_COMPLETED', uuid5(spec.round_id, 'final'))
            self._db.execute("UPDATE debates SET wait_state='COMPLETED' WHERE debate_id=?", (str(debate_id),))
            return result

    def get(self, kind, round_id):
        if not self._db.in_transaction:
            with self.store._transaction(write=False): return self.get(kind, round_id)
        kinds = {'ANALYSIS': (RoundAnalysis, 'COUNCIL_ANALYZED'), 'JUDGE': (SelectedJudge, 'COUNCIL_JUDGE_SELECTED'),
                 'FINAL': (FinalCouncilResult, 'COUNCIL_COMPLETED')}
        model, event_kind = kinds[kind]
        row = self._db.execute('SELECT * FROM council_records WHERE round_id=? AND kind=?', (_identifier(round_id), kind)).fetchone()
        marked = self._db.execute("SELECT * FROM events WHERE kind=? AND json_extract(payload_json,'$.round_id')=?", (event_kind, str(round_id))).fetchall()
        if row is None:
            if marked: raise SchemaError('Council record removed while its event remains')
            return None
        try:
            record = model.model_validate_json(row['record_json'])
            if len(marked) != 1 or row['event_sequence'] != marked[0]['sequence'] or record.content_hash != row['record_hash']:
                raise ValueError('Council checksum or event mismatch')
            event = marked[0]
            expected = {'record_id': row['record_id'], 'round_id': str(round_id), 'record_hash': record.content_hash}
            rev = record.input_revision+1 if kind == 'ANALYSIS' else record.selected_revision if kind == 'JUDGE' else record.completed_revision
            if (event['debate_id'], event['revision']) != (str(record.debate_id), rev) or json.loads(event['payload_json']) != expected:
                raise ValueError('Council event graph mismatch')
            round_row = self._db.execute('SELECT spec_json FROM rounds WHERE round_id=?', (str(round_id),)).fetchone()
            if round_row is None: raise ValueError('Council round missing')
            spec = RoundSpec.model_validate_json(round_row[0])
            if kind == 'ANALYSIS' and record != self._analyze(spec, record.input_revision):
                raise ValueError('Analysis differs from canonical sources')
            if kind == 'JUDGE':
                if spec != record.synthesis_round or record.participant_id != spec.participant_ids[0]:
                    raise ValueError('Judge identity differs from registered synthesis')
                if self.store.admissions.continuation_for(spec).kind != 'FINISH':
                    raise ValueError('Judge lacks a preceding finish decision')
            if kind == 'FINAL' and record != self._final(spec, record.completed_revision-1):
                raise ValueError('Final output differs from canonical judge result')
            return record
        except (ValueError, TypeError, KeyError, RecursionError):
            raise SchemaError('Stored council record is inconsistent') from None

    def export_fields(self, debate_id):
        rows = self._db.execute('SELECT kind,round_id FROM council_records WHERE debate_id=? ORDER BY event_sequence', (_identifier(debate_id),)).fetchall()
        records = [(kind, self.get(kind, UUID(rid))) for kind, rid in rows]
        final = next((r for kind, r in records if kind == 'FINAL'), None)
        return {'scope': 'P05_OFFLINE_COUNCIL_NOT_LIVE_PROVIDER_CERTIFICATION', 'debate_completed': final is not None,
                'round_analyses': [r.model_dump(mode='json') for kind, r in records if kind == 'ANALYSIS'],
                'judge_selections': [r.model_dump(mode='json') for kind, r in records if kind == 'JUDGE'],
                'final_council_result': None if final is None else final.model_dump(mode='json')}

    def recover(self, debate_id):
        with self.store._transaction(write=False):
            snapshot = self.store.export_debate(debate_id)
            attempts = tuple(self.store.ledger.resume(UUID(a['intent']['identity']['attempt_id'])).model_dump(mode='json') for a in snapshot['attempts'])
            return {'snapshot': snapshot, 'attempts': attempts, 'automatic_send': False,
                    'next_action': 'USE_FINAL' if snapshot['debate_completed'] else snapshot['wait_state']}

    def check_integrity(self):
        rows = self._db.execute('SELECT kind,round_id,event_sequence FROM council_records').fetchall()
        for kind, rid, _ in rows: self.get(kind, UUID(rid))
        actual = {(r[1], r[2]) for r in rows}
        marked = {(json.loads(r['payload_json'])['round_id'], r['sequence']) for r in self._db.execute(
            "SELECT * FROM events WHERE kind IN ('COUNCIL_ANALYZED','COUNCIL_JUDGE_SELECTED','COUNCIL_COMPLETED')")}
        if actual != marked: raise SchemaError('Council event/record sets differ')
        for row in self._db.execute('SELECT debate_id,wait_state FROM debates'):
            final = self._db.execute("SELECT 1 FROM council_records WHERE debate_id=? AND kind='FINAL'", (row['debate_id'],)).fetchone()
            if (row['wait_state'] == 'COMPLETED') != (final is not None):
                raise SchemaError('Terminal wait state differs from the durable final result')
