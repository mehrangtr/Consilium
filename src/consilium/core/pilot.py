"""Preregistered pilot accounting. Mock outputs cannot certify model quality."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

METHODS = frozenset({'SINGLE', 'REPEATED_SINGLE', 'COUNCIL'})


@dataclass(frozen=True)
class PilotCall:
    call_id: str
    task_id: str
    method: str
    provider: str
    prompt_sha256: str
    response_sha256: str
    origin: str
    elapsed_seconds: float
    cost: float
    stage: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    final: bool = False
    external_origin_verified: bool = False

    def __post_init__(self) -> None:
        if (any(type(v) is not str or not v.strip() for v in
                (self.call_id, self.task_id, self.provider, self.model_id))
                or self.method not in METHODS or self.origin not in {'MOCK', 'MANUAL'}):
            raise ValueError('Invalid pilot observation identity or provenance')
        if not self.model_id or self.stage not in {'ARCHITECT', 'SINGLE', 'INDEPENDENT', 'REVIEW', 'SYNTHESIS'}:
            raise ValueError('Observed model label and protocol stage are required')
        if any(len(h) != 64 or any(c not in '0123456789abcdef' for c in h) for h in (self.prompt_sha256, self.response_sha256)):
            raise ValueError('Exact prompt and response hashes are required')
        if (type(self.cost) not in (int, float) or self.cost != 0 or type(self.elapsed_seconds) not in (int, float)
                or not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0):
            raise ValueError('Pilot authorizes zero cost and finite observed elapsed time only')
        for value in (self.input_tokens, self.output_tokens):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError('Unavailable token counts stay unknown')
        if type(self.final) is not bool or self.external_origin_verified is not False:
            raise ValueError('Manual imports cannot authenticate external generation')
        if self.final != (self.stage in {'SINGLE', 'SYNTHESIS'}):
            raise ValueError('Final flag must match the protocol stage')


def summarize(calls: tuple[PilotCall, ...], task_ids: tuple[str, ...], max_calls: int = 6) -> dict[str, object]:
    if (not task_ids or len(task_ids) != len(set(task_ids))
            or any(type(t) is not str or not t.strip() for t in task_ids)
            or type(max_calls) is not int or max_calls < 6):
        raise ValueError('Nonempty unique tasks and a valid protocol call ceiling are required')
    if len({c.call_id for c in calls}) != len(calls):
        raise ValueError('A pilot call must not be counted twice')
    expected = {(task, method) for task in task_ids for method in METHODS}
    grouped: dict[tuple[str, str], list[PilotCall]] = {}
    for call in calls:
        key = (call.task_id, call.method)
        if key not in expected:
            raise ValueError('Observation falls outside preregistered tasks or methods')
        grouped.setdefault(key, []).append(call)
    complete = set()
    per_method = []
    selected_models = set()
    architect_signatures: dict[str, set[tuple[str, str, str, str]]] = {}
    for key, group in grouped.items():
        if len(group) > max_calls or sum(c.final for c in group) > 1:
            raise ValueError('Call budget exceeded or final output is ambiguous')
        if sum(c.elapsed_seconds for c in group) > 600 or sum(c.output_tokens or 0 for c in group) > 2400:
            raise ValueError('Observed time or output budget exceeded')
        if any(c.output_tokens is not None and c.output_tokens >
               (2000 if c.stage == 'SINGLE' else 400) for c in group):
            raise ValueError('A call exceeded its preregistered output ceiling')
        expected_stages = {'ARCHITECT': 1, 'SINGLE': 1} if key[1] == 'SINGLE' else {'ARCHITECT': 1, 'INDEPENDENT': 2, 'REVIEW': 2, 'SYNTHESIS': 1}
        observed_stages = Counter(c.stage for c in group)
        if any(n > expected_stages.get(stage, 0) for stage, n in observed_stages.items()):
            raise ValueError('Observation does not follow the preregistered stage counts')
        stage_order = {'ARCHITECT': 0, 'SINGLE': 1, 'INDEPENDENT': 1, 'REVIEW': 2, 'SYNTHESIS': 3}
        ordered = [stage_order[c.stage] for c in group]
        if ordered != sorted(ordered):
            raise ValueError('Pilot stages must preserve actual execution order')
        stages_complete = dict(Counter(c.stage for c in group)) == expected_stages
        models = {(c.provider, c.model_id) for c in group if c.stage != 'ARCHITECT'}
        independent_models = {(c.provider, c.model_id) for c in group if c.stage == 'INDEPENDENT'}
        # A different judge alone cannot make the independent answers diverse.
        models_complete = len(independent_models) == 2 if key[1] == 'COUNCIL' else len(models) == 1
        if key[1] != 'COUNCIL':
            selected_models.update(models)
        for call in group:
            if call.stage == 'ARCHITECT':
                architect_signatures.setdefault(call.task_id, set()).add(
                    (call.provider, call.model_id, call.prompt_sha256, call.response_sha256))
        if all(c.origin == 'MANUAL' for c in group) and stages_complete and models_complete:
            complete.add(key)
        per_method.append({'task_id': key[0], 'method': key[1], 'calls': len(group),
            'elapsed_seconds': round(sum(c.elapsed_seconds for c in group), 3),
            'output_tokens': sum(c.output_tokens for c in group) if all(c.output_tokens is not None for c in group) else None,
            'observed_cost': sum(c.cost for c in group), 'protocol_complete': key in complete})
    if len(selected_models) > 1:
        raise ValueError('Single and repeated-single methods must retain one selected model')
    if any(len(signatures) > 1 for signatures in architect_signatures.values()):
        raise ValueError('All methods must reuse the same common architect input and output')
    return {'status': 'READY_FOR_BLINDED_REVIEW' if complete == expected else 'INCOMPLETE',
            'real_manual_final_outputs': len(complete), 'required_final_outputs': len(expected),
            'recorded_calls': len(calls), 'mock_calls': sum(c.origin == 'MOCK' for c in calls),
            'observed_cost': sum(c.cost for c in calls),
            'observed_elapsed_seconds': round(sum(c.elapsed_seconds for c in calls), 3),
            'token_accounting': 'COMPLETE' if calls and all(c.input_tokens is not None and c.output_tokens is not None for c in calls) else 'UNKNOWN_OR_PARTIAL',
            'output_budget_verification': 'OBSERVED' if calls and all(c.output_tokens is not None for c in calls) else 'PARTIAL_UNKNOWN_TOKENS',
            'per_task_method': sorted(per_method, key=lambda row: (row['task_id'], row['method'])),
            'external_origin_authenticated': False,
            'model_superiority_claimed': False, 'phase_accepted': False}
