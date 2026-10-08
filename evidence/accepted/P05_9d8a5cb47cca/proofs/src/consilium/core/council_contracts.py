"""P05 council records. Advice and model text never grant local authority."""
from typing import Literal, Self
from pydantic import field_validator, model_validator
from .contracts import Contract, Identifier, Revision, Sha256, Text, ConnectionSpec, RoundSpec
from .question_contracts import _hash


class Objection(Contract):
    issue_id: Identifier
    source_hash: Sha256
    reference: Text
    reason: Text
    verdict: Literal['PARTIALLY_ACCEPT', 'REJECT', 'DIFFERENT_ANSWERS']


class RoundAnalysis(Contract):
    debate_id: Identifier
    round_id: Identifier
    input_revision: Revision
    source_hashes: tuple[Sha256, ...]
    objections: tuple[Objection, ...]
    recommendation: Literal['REVIEW', 'TARGETED', 'FINISH']
    recommendation_authorizes_round: Literal[False] = False
    agreement_is_truth_probability: Literal[False] = False
    method: Literal['DETERMINISTIC_REPORTED_DIFFERENCES_NOT_SEMANTIC_TRUTH'] = 'DETERMINISTIC_REPORTED_DIFFERENCES_NOT_SEMANTIC_TRUTH'

    @property
    def content_hash(self): return _hash(self)


class SelectedJudge(Contract):
    debate_id: Identifier
    previous_round_id: Identifier
    synthesis_round: RoundSpec
    participant_id: Identifier
    connection: ConnectionSpec
    connection_revision: Revision
    selected_revision: Revision
    user_action_id: Identifier
    actor: Text
    participated_in_rounds: tuple[Identifier, ...]
    bias_mitigation: Literal['BLIND_ALL_EVIDENCE_WITH_DISSENT']

    @property
    def content_hash(self): return _hash(self)


class JudgeOutput(Contract):
    schema_version: Literal[1]
    conclusion: Text
    evidence: tuple[Text, ...]
    uncertainty: tuple[Text, ...]
    unresolved_issues: tuple[Text, ...]
    dissent: tuple[Text, ...]
    agreement_is_truth_probability: Literal[False]

    @field_validator('schema_version', mode='before')
    @classmethod
    def exact_schema_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Judge schema version must be integer 1')
        return value

    @field_validator('agreement_is_truth_probability', mode='before')
    @classmethod
    def exact_false(cls, value):
        if value is not False:
            raise ValueError('Agreement must never be labeled a truth probability')
        return value


class FinalCouncilResult(Contract):
    debate_id: Identifier
    round_id: Identifier
    judge: SelectedJudge
    judge_source_hash: Sha256
    input_source_hashes: tuple[Sha256, ...]
    output: JudgeOutput
    preserved_objections: tuple[Objection, ...]
    completed_revision: Revision
    scope: Literal['P05_OFFLINE_COUNCIL_NOT_LIVE_PROVIDER_CERTIFICATION'] = 'P05_OFFLINE_COUNCIL_NOT_LIVE_PROVIDER_CERTIFICATION'

    @model_validator(mode='after')
    def identity_matches(self) -> Self:
        if self.judge.debate_id != self.debate_id or self.judge.synthesis_round.round_id != self.round_id:
            raise ValueError('Final output and selected judge disagree')
        return self

    @property
    def content_hash(self): return _hash(self)
