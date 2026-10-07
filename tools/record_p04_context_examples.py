#!/usr/bin/env python3
"""Execute reproducible P04 exit examples; no network or real-provider claims."""
import datetime as dt
import difflib
import hashlib
from pathlib import Path
import sys
import tempfile
from uuid import UUID

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from consilium.core.architect_request import build_architect_request
from consilium.shell.architect_candidates import stage_architect_response
from consilium.core.contracts import ConnectionSpec, DebateSpec, GenerationParameters, OperationIdentity, RoundSpec, UserDecision
from consilium.core.context_observations import HistorySnapshot
from consilium.core.dispatch_policy import PrivacyDecision, destination_hash
from consilium.core.independent_context import build_independent_context, recover_independent_context
from consilium.core.question_contracts import ArchitectProposal, QuestionSnapshot
from consilium.core.round_context import JudgeSelection, TransferGrant, build_round_context
from consilium.shell.context_observers import observe_context
from consilium.shell.context_preparation import prepare_round_intent
from consilium.shell.storage import SQLiteStore


def execute_examples():
    params = GenerationParameters(max_output_tokens=256)
    debate = DebateSpec(debate_id=UUID(int=1), participant_ids=(UUID(int=2), UUID(int=3)),
        original_request="  روش ادامهٔ پژوهش را مقایسه کن.\nهزینه و خطر را روشن کن.  ",
        constraints=("بدون پرداخت", "مخالفت اقلیت حذف نشود", "تصمیم ادامه فقط با کاربر"))
    question = QuestionSnapshot.from_debate(debate)
    proposal = ArchitectProposal(snapshot_hash=question.content_hash, proposal_version=1,
        optimized_request="روش‌های ادامهٔ پژوهش را از نظر هزینه و خطر مقایسه کن و شواهد هر گزینه را مشخص کن.",
        constraints_exact=debate.constraints, constraint_coverage=(0, 1, 2), assumptions=("دامنهٔ نمونه محلی است",),
        visible_changes=("درخواست شاهد برای مقایسه افزوده شد",), origin="MANUAL")
    first = RoundSpec(round_id=UUID(int=4), debate_id=debate.debate_id, number=1,
                     kind="INDEPENDENT", participant_ids=debate.participant_ids)
    contexts = []
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "examples.sqlite3"
        with SQLiteStore(path) as store:
            revision = lambda: store.checkpoint(debate.debate_id).revision
            store.create_debate(debate)
            architect_request = build_architect_request(question,proposal_version=proposal.proposal_version,parameters=params)
            import json
            output={k:v for k,v in proposal.model_dump(mode="json").items() if k in {"optimized_request","constraints_exact","constraint_coverage","assumptions","visible_changes"}}
            output["schema_version"]=1
            proposal=stage_architect_response(store,request=architect_request,content=json.dumps(output,ensure_ascii=False),origin="MANUAL",expected_revision=0)
            adopted = store.questions.approve_proposal(debate.debate_id, proposal_hash=proposal.content_hash,
                user_action_id=UUID(int=5), actor="EXPLICIT_OFFLINE_EXAMPLE_USER", confirmed=True, expected_revision=0)
            store.register_round(first, expected_revision=revision())
            connection = ConnectionSpec(connection_id=UUID(int=6), provider_id="mock", model_id="mock-v1", mode="API")
            for index, participant in enumerate(debate.participant_ids):
                manual = ConnectionSpec(connection_id=UUID(int=10+index), provider_id="unverified-claimed-provider",
                                        model_id="unverified-claimed-model", mode="MANUAL")
                store.bind_connection(debate.debate_id, participant, manual, expected_revision=revision(), expected_connection_revision=None)
                context = build_independent_context(question=adopted, round_spec=first, participant_id=participant,
                    revision=adopted.adoption.adopted_revision, parameters=params)
                recovered = recover_independent_context(context, adopted, first, participant_id=participant,
                    expected_revision=adopted.adoption.adopted_revision, parameters=params)
                assert recovered.canonical_bytes() == context.frozen_input.canonical_bytes()
                candidate = store.manual_sources.stage_answer(candidate_id=UUID(int=20+index), round_spec=first,
                    participant_id=participant, actual_prompt=store.manual_sources._expected_prompt(first,participant),
                    round_seen=True, answer="پیشنهاد اکثریت" if index==0 else "MINORITY_DISSENT: هزینه و خطر هنوز نامطمئن است",
                    claimed_origin="Unverified manual origin", expected_revision=revision())
                store.manual_sources.accept_answer(candidate.candidate_id, candidate_hash=candidate.content_hash,
                    user_action_id=UUID(int=30+index), actor="EXPLICIT_OFFLINE_EXAMPLE_USER", confirmed=True, expected_revision=revision())
                assert "MINORITY_DISSENT" not in context.frozen_input.canonical_bytes().decode("utf-8")
                contexts.append({"kind":"INDEPENDENT", "recovered_identically":True, "context":context.model_dump(mode="json")})
            store.ledger.wait_for_decision(debate.debate_id,first.round_id,expected_revision=revision())
            decision = UserDecision(decision_id=UUID(int=40), debate_id=debate.debate_id, round_id=first.round_id,
                expected_revision=revision(), kind="CUSTOM", instruction="هر دو دیدگاه را بررسی کن و عدم‌قطعیت را نگه دار")
            store.ledger.record_decision(decision,actor="EXPLICIT_OFFLINE_EXAMPLE_USER")
            review = RoundSpec(round_id=UUID(int=41), debate_id=debate.debate_id, number=2,
                               kind="REVIEW", participant_ids=debate.participant_ids)
            store.register_round(review, expected_revision=revision())
            store.bind_connection(debate.debate_id,UUID(int=2),connection,expected_revision=revision(),
                expected_connection_revision=0,actor="EXPLICIT_OFFLINE_EXAMPLE_USER",reason="Observe an offline mock destination")
            sources = store.sources.context_sources(debate.debate_id,through_revision=revision())
            grants = tuple(TransferGrant(source_hash=s.content_hash,destination_hash=destination_hash(connection),
                ledger_revision=revision(),decision="ALLOW",trusted_user_action_id=UUID(int=50+i)) for i,s in enumerate(sources))
            args = dict(question=adopted,debate=debate,round_spec=review,participant_id=UUID(int=2),
                expected_revision=revision(),sources=sources,required_source_hashes=tuple(s.content_hash for s in sources),
                grants=grants,connection=connection,parameters=params,continuation_decision=decision)
            review_context = build_round_context(**args)
            contexts.append({"kind":"REVIEW", "context":review_context.model_dump(mode="json")})
            targeted = review.model_copy(update={"round_id":UUID(int=42),"number":3,"kind":"TARGETED","targets":("بررسی خطر حل‌نشده",)})
            contexts.append({"kind":"TARGETED", "scope":"PURE_PROJECTION_NOT_COMPLETED_ROUND",
                "context":build_round_context(**{**args,"round_spec":targeted,"continuation_decision":None}).model_dump(mode="json")})
            synthesis = targeted.model_copy(update={"round_id":UUID(int=43),"kind":"SYNTHESIS","targets":()})
            judge = JudgeSelection(debate_id=debate.debate_id,destination_hash=destination_hash(connection),
                ledger_revision=revision(),trusted_user_action_id=UUID(int=44),participant_id=UUID(int=2))
            contexts.append({"kind":"SYNTHESIS", "scope":"PURE_PROJECTION_NOT_COMPLETED_ROUND",
                "context":build_round_context(**{**args,"round_spec":synthesis,"judge_selection":judge,"continuation_decision":None}).model_dump(mode="json")})
            for item in contexts[2:]:
                assert "MINORITY_DISSENT" in item["context"]["frozen_input"]["messages"][1]["content"]
            privacy = PrivacyDecision(view_hash=review_context.content_hash, request_hash=review_context.frozen_input.content_hash,
                destination_hash=destination_hash(connection),ledger_revision=revision(),decision="ALLOW",contains_secret=False,
                trusted_user_action_id=UUID(int=60))
            snapshot = HistorySnapshot(debate_id=debate.debate_id,destination_hash=destination_hash(connection),
                                       conversation_id=None,complete=True,entries=())
            observation,budget,history = observe_context(store=store,context=review_context,connection=connection,
                expected_revision=revision(),expected_connection_revision=1,privacy=privacy,snapshot=snapshot,
                new_topic=False,preference="PREFER_CURRENT",user_action_id=None,grants=grants)
            identity = OperationIdentity(logical_operation_id=UUID(int=70),attempt_id=UUID(int=71))
            prepare_round_intent(store,debate_id=debate.debate_id,round_id=review.round_id,participant_id=UUID(int=2),
                context=review_context,connection=connection,identity=identity,expected_revision=revision(),expected_connection_revision=1,
                parameters=params,grants=grants,privacy=privacy,budget=budget,history=history,observation=observation)
            expected = store.admissions.get(identity.logical_operation_id)
        with SQLiteStore(path) as store:
            assert store.admissions.get(identity.logical_operation_id) == expected
            assert store.get_intent(identity.attempt_id).frozen_input == review_context.frozen_input
            assert store.ledger.resume(identity.attempt_id).automatic_send is False
            assert len(store.export_debate(debate.debate_id)["context_admissions"]) == 1
    return {"architect_request":architect_request.model_dump(mode="json"),"architect_candidate_staged_before_first_round":True,"original":question.model_dump(mode="json"),"proposal":proposal.model_dump(mode="json"),
            "display_diff":"\n".join(difflib.unified_diff(debate.original_request.splitlines(),proposal.optimized_request.splitlines(),
                                                         fromfile="original",tofile="candidate",lineterm="")),
            "contexts":contexts,"observation":observation.model_dump(mode="json"),
            "restart_exact":True,"independent_peer_leak":False,"dissent_preserved":True,
            "explicit_user_authority":True,"policy_managed_live_send_enabled":False}


def main():
    before = q.source_digest(ROOT)
    result = execute_examples()
    after = q.source_digest(ROOT)
    assert before == after
    report = {"phase":"P04","scope":"EXECUTED_OFFLINE_CONTEXT_EXIT_EXAMPLES_NOT_LIVE_PROVIDER_PROOF",
        "status":"PASS","source_digest_before":before,"source_digest_after":after,
        "date_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"live_provider_calls":0,"paid_calls":0,
        "full_v1_conformance_claimed":False,"examples":result}
    destination=ROOT/"evidence/p04/context-examples/RUN.json"
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(q.encoded(report))
    print(q.encoded({"status":"PASS","receipt":str(destination.relative_to(ROOT)),"source_digest":before}).decode())


if __name__ == "__main__":
    main()
