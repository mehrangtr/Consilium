import json
import unittest
from uuid import UUID
import test_context_preparation as fixtures
from consilium.core.architect_request import build_architect_request, parse_architect_response
from consilium.core.contracts import DebateSpec, GenerationParameters
from consilium.core.question_contracts import QuestionSnapshot


class ArchitectRequestTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=QuestionSnapshot.from_debate(DebateSpec(debate_id=UUID(int=1),participant_ids=(UUID(int=2),),
            original_request="  اصل\nقابل حفظ  ",constraints=("بدون هزینه","حفظ مخالفت")))
        self.request=build_architect_request(self.snapshot,proposal_version=2,parameters=GenerationParameters(max_output_tokens=100))
        self.output=dict(schema_version=1,optimized_request="پرسش روشن",constraints_exact=list(self.snapshot.constraints_exact),
            constraint_coverage=[0,1],assumptions=["فرض آشکار"],visible_changes=["شفاف‌سازی"])

    def parse(self,**updates):return parse_architect_response(json.dumps({**self.output,**updates}),self.request,origin="MANUAL")

    def test_frozen_architect_input_preserves_exact_question_constraints_and_output_contract(self):
        data=json.loads(self.request.frozen_input.messages[1].content)
        self.assertEqual(data['original_request'],self.snapshot.original_request_exact)
        self.assertEqual(data['constraints_exact'],list(self.snapshot.constraints_exact))
        self.assertIn('output_schema',data)
        self.assertEqual(self.request,build_architect_request(self.snapshot,proposal_version=2,parameters=self.request.frozen_input.parameters))

    def test_checked_response_is_only_a_bound_versioned_candidate(self):
        result=self.parse();self.assertEqual(result.snapshot_hash,self.snapshot.content_hash)
        self.assertEqual(result.proposal_version,2);self.assertEqual(result.origin,"MANUAL")
        self.assertNotIn('trusted_user_action_id',result.model_dump())

    def test_control_identity_and_origin_fields_from_provider_are_rejected(self):
        for field in ('decision','trusted_user_action_id','judge','origin','snapshot_hash','proposal_version'):
            with self.subTest(field=field),self.assertRaises(ValueError):self.parse(**{field:'self-approved'})

    def test_changed_or_missing_constraint_is_rejected(self):
        for update in ({'constraints_exact':['بدون هزینه']},{'constraint_coverage':[0]},
                       {'constraints_exact':['حفظ مخالفت','بدون هزینه']},{'constraint_coverage':[0,0]}):
            with self.subTest(update=update),self.assertRaises(ValueError):self.parse(**update)

    def test_duplicate_keys_nonfinite_text_and_nonobject_json_are_rejected(self):
        for text in ('{"schema_version":1,"schema_version":1}', '[1,2]', 'NaN', 'not json'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_architect_response(text,self.request,origin="MOCK")

    def test_live_origin_cannot_be_self_certified(self):
        with self.assertRaises(ValueError):parse_architect_response(json.dumps(self.output),self.request,origin="LIVE_GENERATED")

    def test_boolean_or_text_versions_do_not_impersonate_integer_schema_version(self):
        for value in (True,False,"1",0,2):
            with self.subTest(value=value),self.assertRaises(ValueError):self.parse(schema_version=value)
        with self.assertRaises(ValueError):self.request.model_copy(update={"schema_version":True})


class ArchitectStageTests(unittest.TestCase):
    setUp=fixtures.ContextPreparationTests.setUp
    tearDown=fixtures.ContextPreparationTests.tearDown

    def test_response_cannot_be_staged_after_round_has_started(self):
        from consilium.shell.architect_candidates import stage_architect_response
        snapshot=QuestionSnapshot.from_debate(self.store.get_debate(self.debate.debate_id))
        request=build_architect_request(snapshot,proposal_version=2)
        payload=dict(schema_version=1,optimized_request='Late proposal',constraints_exact=list(snapshot.constraints_exact),
            constraint_coverage=list(range(len(snapshot.constraints_exact))),assumptions=[],visible_changes=[])
        with self.assertRaises(ValueError):stage_architect_response(self.store,request=request,
            content=json.dumps(payload),origin="MANUAL",expected_revision=3)
