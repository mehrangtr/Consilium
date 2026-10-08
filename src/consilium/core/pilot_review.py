"""Pure blinded pilot projections and descriptive, strictly bound score validation."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
import hashlib
import json
from itertools import combinations

from consilium.core.pilot import METHODS, PilotCall, summarize
from consilium.core.rubrics import get_rubric, rubric_payload


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def decoded(content: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('JSON field is repeated')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('Nonfinite JSON number is not a valid observation')
    return json.loads(content, object_pairs_hook=unique, parse_constant=invalid_constant)


def judge_references(plan: dict, dataset: bytes) -> bytes:
    if digest(dataset) != plan['dataset_sha256']:
        raise ValueError('Held-out references must match the preregistered dataset bytes')
    tasks = [task for task in decoded(dataset)['tasks'] if task['task_id'] in plan['task_ids']]
    if len(tasks) != len(plan['task_ids']) or {task['task_id'] for task in tasks} != set(plan['task_ids']):
        raise ValueError('Held-out references require exactly the preregistered tasks')
    return encoded({'version': 'p06-judge-references.v1', 'dataset_sha256': plan['dataset_sha256'],
        'rubric': rubric_payload(plan['rubric_id']), 'tasks': tasks})


def blinded_material(calls: tuple[PilotCall, ...], plan: dict,
                     responses: Mapping[str, bytes]) -> tuple[dict, dict, dict]:
    if summarize(calls, tuple(plan['task_ids']), plan['max_calls_per_task_method'])[
            'status'] != 'READY_FOR_BLINDED_REVIEW':
        raise ValueError('All real protocol observations and shared architect links are required')
    finals = sorted((c for c in calls if c.final), key=lambda c:
        digest(encoded([plan['blinding_seed'], c.task_id, c.method])))
    outputs = []
    mapping = {}
    for index, call in enumerate(finals, 1):
        content = responses[call.response_sha256]
        if digest(content) != call.response_sha256:
            raise ValueError('Final response bytes differ from their recorded digest')
        blind_id = f'BLIND-{index:03}'
        outputs.append({'blind_id': blind_id, 'task_id': call.task_id,
                        'response_sha256': call.response_sha256,
                        'response': content.decode('utf-8')})
        mapping[blind_id] = {'call_id': call.call_id, 'method': call.method,
                            'provider': call.provider, 'model_id': call.model_id}
    packet = {'version': 'p06-blinded.v1', 'dataset_sha256': plan['dataset_sha256'],
              'preregistration_sha256': digest(encoded(plan)),
              'observation_manifest_sha256': digest(encoded([asdict(call) for call in calls])),
              'rubric': rubric_payload(plan['rubric_id']), 'outputs': outputs}
    template = {'version': 'p06-scores.v1', 'packet_sha256': digest(encoded(packet)),
                'dataset_sha256': plan['dataset_sha256'], 'rubric_id': plan['rubric_id'],
                'evaluator': {'id': '', 'origin': '', 'relationship': ''},
                'scores': [{'blind_id': row['blind_id'], 'task_id': row['task_id'],
                    'response_sha256': row['response_sha256'],
                    'dimensions': {dimension: {'score': None, 'reason': ''}
                        for dimension in get_rubric(plan['rubric_id']).dimensions}}
                    for row in outputs]}
    return packet, mapping, template


def validate_scores(record: dict, packet: dict, mapping: dict) -> dict:
    if type(record) is not dict or set(record) != {
            'version', 'packet_sha256', 'dataset_sha256', 'rubric_id', 'evaluator', 'scores'}:
        raise ValueError('Score document has unknown or missing fields')
    if (record['version'] != 'p06-scores.v1'
            or record['packet_sha256'] != digest(encoded(packet))
            or record['dataset_sha256'] != packet['dataset_sha256']
            or record['rubric_id'] != packet['rubric']['id']):
        raise ValueError('Scores must bind the exact frozen packet, dataset and rubric')
    evaluator = record['evaluator']
    if (type(evaluator) is not dict or set(evaluator) != {'id', 'origin', 'relationship'}
            or type(evaluator['id']) is not str or not evaluator['id'].strip()
            or type(evaluator['origin']) is not str
            or evaluator['origin'] not in {'HUMAN_MANUAL', 'MODEL_MANUAL'}
            or type(evaluator['relationship']) is not str
            or evaluator['relationship'] not in {'SAME_AUTHOR', 'DECLARED_OTHER_EVALUATOR'}):
        raise ValueError('Evaluator identity, manual origin and relationship must be declared')
    rows = record['scores']
    expected = {row['blind_id']: row for row in packet['outputs']}
    if (type(rows) is not list or len(rows) != len(expected)
            or set(mapping) != set(expected)):
        raise ValueError('Every frozen blind output must be scored exactly once')
    rubric = get_rubric(record['rubric_id'])
    seen = set()
    totals = {}
    for row in rows:
        if type(row) is not dict or set(row) != {
                'blind_id', 'task_id', 'response_sha256', 'dimensions'}:
            raise ValueError('Score rows must contain only the blind identity and rubric judgments')
        identifier = row['blind_id']
        if type(identifier) is not str or identifier not in expected or identifier in seen:
            raise ValueError('Duplicate or foreign blind output')
        seen.add(identifier)
        if any(row[key] != expected[identifier][key] for key in ('task_id', 'response_sha256')):
            raise ValueError('Score row does not bind the exact task and response')
        dimensions = row['dimensions']
        if type(dimensions) is not dict or set(dimensions) != set(rubric.dimensions):
            raise ValueError('All preregistered dimensions require explicit judgments')
        values = {}
        for dimension, judgment in dimensions.items():
            if (type(judgment) is not dict or set(judgment) != {'score', 'reason'}
                    or type(judgment['reason']) is not str or not judgment['reason'].strip()):
                raise ValueError('Every dimension requires a score and a nonempty reference-based reason')
            values[dimension] = judgment['score']
        total = rubric.score(values)
        method = mapping[identifier]['method']
        key = (row['task_id'], method)
        if method not in METHODS or key in totals:
            raise ValueError('Blind map has duplicate or foreign method assignments')
        totals[key] = total
    tasks = sorted({task for task, _ in totals})
    if set(totals) != {(task, method) for task in tasks for method in METHODS}:
        raise ValueError('Paired comparison requires all three methods for each task')
    pairs = []
    for first, second in combinations(sorted(METHODS), 2):
        differences = [{'task_id': task, 'difference': round(
            totals[task, first] - totals[task, second], 2)} for task in tasks]
        values = [row['difference'] for row in differences]
        pairs.append({'first_method': first, 'second_method': second,
            'per_task': differences, 'mean_difference': round(sum(values) / len(values), 3),
            'observed_range': [min(values), max(values)],
            'positive_tasks': sum(value > 0 for value in values),
            'negative_tasks': sum(value < 0 for value in values),
            'tied_tasks': sum(value == 0 for value in values)})
    return {'status': 'VALIDATED_BLINDED_SCORES', 'packet_sha256': record['packet_sha256'],
        'score_document_sha256': digest(encoded(record)), 'task_count': len(tasks),
        'scored_outputs': len(rows), 'evaluator': evaluator,
        'evaluator_origin_authenticated': False, 'reviewer_independence_verified': False,
        'paired_differences': pairs, 'uncertainty': 'SMALL_SAMPLE_DESCRIPTIVE_ONLY_NO_POPULATION_INFERENCE',
        'model_superiority_claimed': False, 'phase_accepted': False}
