"""Versioned scoring definitions. Scores are judgments, never truth probabilities."""
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Rubric:
    identifier: str
    dimensions: Mapping[str, float]
    purpose: str

    def score(self, values: Mapping[str, float]) -> float:
        if set(values) != set(self.dimensions):
            raise ValueError('Every rubric dimension must be explicitly scored')
        if any(type(v) not in (int, float) or not 1 <= v <= 10 for v in values.values()):
            raise ValueError('Scores must be finite numbers from 1 to 10')
        return round(sum(values[k] * weight for k, weight in self.dimensions.items()), 2)


REVIEW_DIMENSIONS = MappingProxyType({'evidence': .40, 'reasoning': .25,
                                     'constraint_preservation': .20, 'coverage': .15})
RESEARCH_DIMENSIONS = MappingProxyType({'usefulness': .40, 'accuracy': .25,
                                       'user_constraints': .20, 'practicality': .15})
RUBRICS = MappingProxyType({
    key: Rubric(key, REVIEW_DIMENSIONS, 'Council response review')
    for key in ('council-rubric.v1', 'manual-rubric.v1', 'rubric.v1')
} | {'research-review.v1': Rubric('research-review.v1', RESEARCH_DIMENSIONS, 'Official proposal review'),
     'p06-quality.v1': Rubric('p06-quality.v1', REVIEW_DIMENSIONS, 'Preregistered quality pilot')})


def get_rubric(identifier: str) -> Rubric:
    try:
        return RUBRICS[identifier]
    except KeyError:
        raise ValueError('Unknown rubric version; register its definition before scoring') from None


def rubric_payload(identifier: str) -> dict[str, object]:
    rubric = get_rubric(identifier)
    return {'id': rubric.identifier, 'dimensions': dict(rubric.dimensions),
            'scale': [1, 10], 'unscored': 'NOT_SCORED', 'truth_probability': False,
            'purpose': rubric.purpose}
