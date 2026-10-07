"""Local manual-round records; neither login nor remote generation is certified."""
from typing import Annotated, Literal, Self
from uuid import uuid5
import json
from pydantic import Field, model_validator
from .artifact_contracts import CritiquesOutput, VersionedOutput, decode_response_json
from .contracts import Answer, ConnectionSpec, Contract, Critique, Identifier, Revision, Sha256, RoundSpec, Text, UserDecision
from .question_contracts import _hash
from .round_context import ContextSource, NamedReviewAuthorization, RoundContext, TransferGrant

class ManualReviewTarget(Contract):
    alias: Annotated[str, Field(pattern='^[A-Z]{1,12}$')]
    answer_id: Identifier
    source_hash: Sha256

class ManualRoundFrame(Contract):
    scope: Literal['LOCAL_MANUAL_CONTEXT_NOT_REMOTE_TOKEN_OR_HISTORY_PROOF'] = 'LOCAL_MANUAL_CONTEXT_NOT_REMOTE_TOKEN_OR_HISTORY_PROOF'
    round_spec: RoundSpec
    participant_id: Identifier
    connection: ConnectionSpec
    connection_revision: Revision
    context: RoundContext
    sources: tuple[ContextSource, ...]
    grants: tuple[TransferGrant, ...]
    continuation_decision: UserDecision
    named_authorization: NamedReviewAuthorization | None = None
    rubric_version: Text = 'manual-rubric.v1'
    max_context_bytes: Annotated[int, Field(ge=1, le=1048576)] = 1048576

    @property
    def staged_revision(self):
        return self.context.ledger_revision

    @property
    def expected_prompt(self):
        return self.context.frozen_input.canonical_bytes().decode('utf-8')

    @property
    def targets(self) -> tuple[ManualReviewTarget, ...]:
        if self.round_spec.kind != 'REVIEW':
            return ()
        latest = {}
        for source in self.sources:
            if isinstance(source.item, Answer) and source.item.participant_id != self.participant_id:
                old = latest.get(source.item.participant_id)
                if old is None or (source.source_round.number, source.source_revision) > (old.source_round.number, old.source_revision):
                    latest[source.item.participant_id] = source
        ordered = sorted(latest.values(), key=lambda s: str(s.item.participant_id))
        projected = json.loads(self.context.frozen_input.messages[1].content)['sources']
        aliases = {row['source_hash']: row['author'] for row in projected if row['kind'] == 'ANSWER'}
        return tuple((ManualReviewTarget(alias=aliases[s.content_hash], answer_id=s.item.answer_id, source_hash=s.content_hash) for s in ordered))

    @model_validator(mode='after')
    def bounded_role(self) -> Self:
        if self.round_spec.kind not in {'REVIEW', 'TARGETED'} or self.round_spec.number < 2 or self.connection.mode != 'MANUAL' or (self.participant_id not in self.round_spec.participant_ids) or ((self.context.debate_id, self.context.round_id, self.context.participant_id) != (self.round_spec.debate_id, self.round_spec.round_id, self.participant_id)) or (len(self.sources) != len({s.content_hash for s in self.sources})) or ({s.content_hash for s in self.sources} != set(self.context.source_hashes)) or (len(self.expected_prompt.encode('utf-8')) > self.max_context_bytes) or (self.round_spec.kind == 'REVIEW' and (not self.targets)):
            raise ValueError('Manual round frame role, canonical view or local byte limit is invalid')
        return self

    @property
    def content_hash(self):
        return _hash(self)

class ManualRoundSubmission(VersionedOutput):
    candidate_id: Identifier
    actual_prompt: Text
    round_seen: bool
    content: Annotated[Text, Field(max_length=262144)]
    claimed_origin: Annotated[Text, Field(max_length=1024)] | None = None
    data_class: Literal['PUBLIC', 'PRIVATE'] = 'PRIVATE'

class ManualRoundCandidate(Contract):
    frame: ManualRoundFrame
    candidate_id: Identifier
    actual_prompt: Text
    round_seen: bool
    content: Annotated[Text, Field(max_length=262144)]
    claimed_origin: Annotated[Text, Field(max_length=1024)] | None = None
    data_class: Literal['PUBLIC', 'PRIVATE'] = 'PRIVATE'

    @property
    def round_spec(self):
        return self.frame.round_spec

    @property
    def participant_id(self):
        return self.frame.participant_id

    @property
    def connection(self):
        return self.frame.connection

    @property
    def connection_revision(self):
        return self.frame.connection_revision

    @property
    def staged_revision(self):
        return self.frame.staged_revision

    @property
    def alignment(self):
        return 'ALIGNED' if self.round_seen and self.actual_prompt == self.frame.expected_prompt else 'DIVERGED'

    @property
    def content_hash(self):
        return _hash(self)

    def critique_output(self) -> CritiquesOutput:
        output = CritiquesOutput.model_validate_json(decode_response_json(self.content, 262144))
        aliases = [c.target_alias for c in output.critiques]
        if len(aliases) != len(set(aliases)) or set(aliases) != {t.alias for t in self.frame.targets}:
            raise ValueError('Manual review must cover every frozen peer target exactly once')
        return output

    @model_validator(mode='after')
    def bounded_content(self) -> Self:
        if len(self.content.encode('utf-8')) > 262144 or len(self.model_dump_json().encode('utf-8')) > 4194304:
            raise ValueError('Manual candidate exceeds its local byte limit')
        if self.round_spec.kind == 'REVIEW':
            self.critique_output()
        return self

def manual_round_sources(candidate: ManualRoundCandidate, accepted_revision: int) -> tuple[ContextSource, ...]:
    c = ManualRoundCandidate.model_validate(candidate)
    r = c.round_spec
    if r.kind == 'TARGETED':
        items = (Answer(answer_id=uuid5(c.candidate_id, 'consilium/manual-round-answer/v1'), debate_id=r.debate_id, round_id=r.round_id, participant_id=c.participant_id, content=c.content, provenance='MANUAL', used_prompt=c.actual_prompt, round_seen=c.round_seen, logical_operation_id=None),)
    else:
        by_alias = {item.target_alias: item for item in c.critique_output().critiques}
        items = tuple((Critique(critique_id=uuid5(c.candidate_id, 'consilium/manual-critique/v1/' + str(t.answer_id)), debate_id=r.debate_id, round_id=r.round_id, reviewer_id=c.participant_id, target_answer_id=t.answer_id, rubric_version=c.frame.rubric_version, **by_alias[t.alias].model_dump(mode='python', exclude={'target_alias'})) for t in c.frame.targets))
    return tuple((ContextSource(item=item, source_round=r, source_revision=accepted_revision, provenance='MANUAL', data_class=c.data_class) for item in items))

class AcceptedManualRound(Contract):
    scope: Literal['USER_ACCEPTED_MANUAL_ROUND_NOT_LIVE_DELIVERY_PROOF'] = 'USER_ACCEPTED_MANUAL_ROUND_NOT_LIVE_DELIVERY_PROOF'
    candidate: ManualRoundCandidate
    candidate_hash: Sha256
    trusted_user_action_id: Identifier
    actor: Text
    accepted_revision: Revision
    alignment: Literal['ALIGNED', 'DIVERGED']
    external_origin_verified: Literal[False] = False
    sources: tuple[ContextSource, ...]

    @model_validator(mode='after')
    def exact_sources(self) -> Self:
        if self.candidate_hash != self.candidate.content_hash or self.alignment != self.candidate.alignment or self.accepted_revision != self.candidate.staged_revision + 1 or (self.sources != manual_round_sources(self.candidate, self.accepted_revision)):
            raise ValueError('Accepted manual batch differs from its reviewed candidate')
        return self

    @property
    def content_hash(self):
        return _hash(self)
