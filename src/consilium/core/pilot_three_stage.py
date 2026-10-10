"""Separate, prospectively bound three-stage pilot; no legacy run promotion."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from consilium.core.pilot import METHODS, PilotCall
from consilium.core.pilot_review import digest, encoded


@dataclass(frozen=True)
class ThreeStagePlan:
    task_ids: tuple[str, ...]
    selected_provider: str
    selected_model: str
    peer_provider: str
    peer_model: str
    dataset_sha256: str
    version: str = 'p06-three-stage.v1'
    max_calls: int = 10
    max_elapsed_seconds: int = 1200
    max_output_tokens: int = 3200

    def __post_init__(self) -> None:
        if (self.version != 'p06-three-stage.v1' or self.max_calls != 10
                or self.max_elapsed_seconds != 1200 or self.max_output_tokens != 3200
                or not 6 <= len(self.task_ids) <= 10
                or len(set(self.task_ids)) != len(self.task_ids)
                or any(type(t) is not str or not t.strip() for t in self.task_ids)
                or any(type(v) is not str or not v.strip() for v in (
                    self.selected_provider, self.selected_model, self.peer_provider, self.peer_model))
                or (self.selected_provider, self.selected_model) == (self.peer_provider, self.peer_model)
                or not valid_hash(self.dataset_sha256)):
            raise ValueError('Invalid separate three-stage preregistration')

    @property
    def sha256(self) -> str:
        return digest(encoded(asdict(self)))


def valid_hash(value: object) -> bool:
    return (type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


@dataclass(frozen=True)
class ThreeStageCall:
    call: PilotCall
    plan_sha256: str
    round_number: int
    participant_slot: int
    conversation_sha256: str
    account_binding_sha256: str
    peer_call_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (not isinstance(self.call, PilotCall)
                or any(not valid_hash(h) for h in (self.plan_sha256,
                    self.conversation_sha256, self.account_binding_sha256))
                or type(self.round_number) is not int or self.round_number not in range(5)
                or type(self.participant_slot) is not int or self.participant_slot not in (0, 1)
                or type(self.peer_call_ids) is not tuple
                or any(type(p) is not str or not p for p in self.peer_call_ids)
                or len(set(self.peer_call_ids)) != len(self.peer_call_ids)):
            raise ValueError('Exact protocol, account, conversation and round binding required')


def protocol_steps(method: str) -> tuple[tuple[str, int, int], ...]:
    if method not in METHODS:
        raise ValueError('Unknown comparison method')
    if method == 'SINGLE':
        return (('ARCHITECT', 0, 0), ('SINGLE', 1, 0))
    return (('ARCHITECT', 0, 0), ('INDEPENDENT', 1, 0), ('INDEPENDENT', 1, 1),
            ('REVIEW', 2, 0), ('REVIEW', 2, 1), ('REVIEW', 3, 0),
            ('REVIEW', 3, 1), ('SYNTHESIS', 4, 0))


def summarize_three_stage(observations: tuple[ThreeStageCall, ...], plan: ThreeStagePlan) -> dict:
    if len({o.call.call_id for o in observations}) != len(observations):
        raise ValueError('Duplicate observation')
    groups: dict[tuple[str, str], list[ThreeStageCall]] = {}
    bindings = {}
    physical = {}
    architect_signatures = {}
    for obs in observations:
        call = obs.call
        if obs.plan_sha256 != plan.sha256 or call.task_id not in plan.task_ids:
            raise ValueError('Legacy or differently registered observations cannot enter this run')
        expected_model = ((plan.peer_provider, plan.peer_model)
            if call.method == 'COUNCIL' and obs.participant_slot == 1
            else (plan.selected_provider, plan.selected_model))
        if (call.provider, call.model_id) != expected_model:
            raise ValueError('Selected participant or judge changed')
        # One model/account conversation throughout a topic, including judging.
        key = (call.task_id, call.provider, call.model_id)
        binding = (obs.account_binding_sha256, obs.conversation_sha256)
        if key in bindings and bindings[key] != binding:
            raise ValueError('A topic cannot move to another account or conversation')
        bindings[key] = binding
        groups.setdefault((call.task_id, call.method), []).append(obs)
        identity = call.shared_architect_call_id or call.call_id
        signature = (call.task_id, call.provider, call.model_id, call.stage,
            call.prompt_sha256, call.response_sha256, call.origin, call.elapsed_seconds,
            call.cost, call.input_tokens, call.output_tokens, call.outcome,
            call.failure_reason, obs.round_number, obs.participant_slot, binding)
        if identity in physical and physical[identity] != signature:
            raise ValueError('A shared physical call has inconsistent evidence')
        physical[identity] = signature
        if call.stage == 'ARCHITECT' and call.outcome == 'SUCCESS':
            if call.shared_architect_call_id is None:
                raise ValueError('The same physical architect must be explicitly linked')
            arch_sig = (identity, call.prompt_sha256, call.response_sha256)
            if call.task_id in architect_signatures and architect_signatures[call.task_id] != arch_sig:
                raise ValueError('Methods must use the same architect')
            architect_signatures[call.task_id] = arch_sig
    rows = []
    complete = 0
    for (task, method), group in sorted(groups.items()):
        steps = protocol_steps(method)
        if (len(group) > plan.max_calls
                or sum(o.call.elapsed_seconds for o in group) > plan.max_elapsed_seconds
                or sum(o.call.output_tokens or 0 for o in group) > plan.max_output_tokens
                or any(o.call.output_tokens is not None and o.call.output_tokens >
                    (2000 if o.call.stage == 'SINGLE' else 400) for o in group)):
            raise ValueError('Separate registered call/time/output ceiling exceeded')
        successes: list[ThreeStageCall] = []
        pending = None
        for obs in group:
            call = obs.call
            if len(successes) >= len(steps):
                raise ValueError('A finished method cannot receive more calls')
            if (call.stage, obs.round_number, obs.participant_slot) != steps[len(successes)]:
                raise ValueError('Incomplete round, wrong slot or premature judgment')
            expected_peers = ()
            if obs.round_number in (2, 3, 4):
                expected_peers = tuple(o.call.call_id for o in successes
                    if o.round_number == obs.round_number - 1)
            if obs.peer_call_ids != expected_peers:
                raise ValueError('The next round must bind every preceding-round opinion')
            if pending is None:
                if call.repair_of is not None:
                    raise ValueError('Repair has no preceding definite failure')
            elif pending.call.outcome != 'FAILED' or call.repair_of != pending.call.call_id:
                raise ValueError('Unknown delivery never authorizes a resend')
            if call.outcome == 'SUCCESS':
                successes.append(obs)
                pending = None
            else:
                pending = obs
        done = (len(successes) == len(steps) and pending is None
                and all(o.call.origin == 'MANUAL' for o in group))
        complete += int(done)
        required = len(steps) - len(successes)
        rows.append({'task_id': task, 'method': method, 'protocol_complete': done,
            'recorded_attempts': len(group), 'remaining_required_successes': required,
            'remaining_call_allowance': plan.max_calls - len(group),
            'call_budget_feasible': required <= plan.max_calls - len(group),
            'unresolved_outcome': pending.call.outcome if pending else None})
    required_finals = len(plan.task_ids) * len(METHODS)
    return {'version': plan.version, 'plan_sha256': plan.sha256,
        'status': 'READY_FOR_BLINDED_REVIEW' if complete == required_finals else 'INCOMPLETE',
        'required_final_outputs': required_finals, 'real_manual_final_outputs': complete,
        'recorded_method_observations': len(observations), 'unique_model_attempts': len(physical),
        'per_task_method': rows, 'model_superiority_claimed': False, 'phase_accepted': False,
        'cross_method_context': 'SAME_TOPIC_CONVERSATION; CARRYOVER_CONFOUNDS_COMPARISON',
        'repeated_single_independence': 'NOT_CLAIMED; SAME_MODEL_SAME_CONVERSATION',
        'external_origin_authenticated': False,
        'token_accounting': 'OBSERVED' if observations and all(
            o.call.input_tokens is not None and o.call.output_tokens is not None for o in observations)
            else 'UNKNOWN_OR_PARTIAL'}
