"""Raw differences are durable facts; optional semantic advice cannot replace them."""
from typing import Literal, Protocol
from uuid import uuid5

from consilium.core.contracts import Answer, Contract, Critique, Sha256, Text
from consilium.core.council_contracts import Objection, RoundAnalysis


class SemanticObservation(Contract):
    source_hashes: tuple[Sha256, ...]
    relation: Literal['EQUIVALENT', 'DIFFERENT', 'UNKNOWN']
    reason: Text
    method_version: Text
    authorizes_round: Literal[False] = False
    is_truth_probability: Literal[False] = False


class SemanticAnalyzer(Protocol):
    """Optional advisory extension; no implementation or live certification implied."""
    def annotate(self, sources: tuple) -> tuple[SemanticObservation, ...]: ...


class DeterministicAnalyzer:
    def analyze(self, round_spec, revision, sources):
        current = tuple(s for s in sources if s.source_round.round_id == round_spec.round_id)
        authors = {s.item.participant_id if isinstance(s.item, Answer) else s.item.reviewer_id for s in current}
        if authors != set(round_spec.participant_ids):
            raise ValueError('Round analysis requires every canonical participant contribution')
        objections = []
        for source in sources:
            if isinstance(source.item, Critique):
                for index, point in enumerate(source.item.points):
                    if point.verdict != 'ACCEPT':
                        objections.append(Objection(issue_id=uuid5(source.item.critique_id, str(index)),
                            source_hash=source.content_hash, reference=point.reference,
                            reason=point.reason, verdict=point.verdict))
        independent = tuple(s for s in sources if isinstance(s.item, Answer) and s.source_round.kind == 'INDEPENDENT')
        if len({s.item.content for s in independent}) > 1:
            for source in independent:
                objections.append(Objection(issue_id=uuid5(source.item.answer_id, 'reported-difference'),
                    source_hash=source.content_hash, reference='INDEPENDENT_ANSWER_DIFFERENCE',
                    reason=source.item.content, verdict='DIFFERENT_ANSWERS'))
        return RoundAnalysis(debate_id=round_spec.debate_id, round_id=round_spec.round_id,
            input_revision=revision, source_hashes=tuple(s.content_hash for s in sources), objections=tuple(objections),
            recommendation='REVIEW' if round_spec.kind == 'INDEPENDENT' else 'TARGETED' if objections else 'FINISH')
