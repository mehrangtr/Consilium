# نتیجهٔ نهایی شورا

```text
{
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "26cca672-5d8d-4c28-ba0f-df0cbf43f4da",
  "judge": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "previous_round_id": "b6f99e13-afa2-4166-9c62-8e3c2843dc74",
    "synthesis_round": {
      "round_id": "26cca672-5d8d-4c28-ba0f-df0cbf43f4da",
      "debate_id": "00000000-0000-0000-0000-000000000001",
      "number": 4,
      "kind": "SYNTHESIS",
      "participant_ids": [
        "00000000-0000-0000-0000-000000000002"
      ],
      "targets": []
    },
    "participant_id": "00000000-0000-0000-0000-000000000002",
    "connection": {
      "connection_id": "00000000-0000-0000-0000-00000000000a",
      "provider_id": "unverified-fixture",
      "model_id": "mock-v1",
      "mode": "MANUAL",
      "account_binding_id": null
    },
    "connection_revision": 1,
    "selected_revision": 23,
    "user_action_id": "7be2b87e-955d-4e19-a877-b4b926dadeee",
    "actor": "EXPLICIT_OFFLINE_TEST_USER",
    "participated_in_rounds": [
      "830a229a-7e38-4066-8a81-16987a620e9f",
      "582f60fe-1361-46fd-b959-ef225241c3c7",
      "b6f99e13-afa2-4166-9c62-8e3c2843dc74"
    ],
    "bias_mitigation": "BLIND_ALL_EVIDENCE_WITH_DISSENT"
  },
  "judge_source_hash": "3bab9932af9862448a9f87f2622c3b0199a946737e9b7fabfd248da40f61a851",
  "input_source_hashes": [
    "898b46c3cefb45691595d4e88282e94ff967ec0728448ecb646b247d1ed03908",
    "a1f94ddb0dfe69db3fb4ccf1792364936bdc86b91919e6c3c34a106918c66f9e",
    "220d5b6c931808de8d186003a44189c92f2ded1fe02af312ceae8e7706a8d251",
    "738d033092d953ff5fd624d88aa38e07b45eb71bfa2455b4b7aba8216c6ee07f",
    "87e885e108d225b76e76426ab25c5e9a3976e74e66eacb41305e49d8443504e0",
    "3528a2cb4b1dff4480a1674510ee2608bc3a81b7804968798c398d43b492aaa5"
  ],
  "output": {
    "schema_version": 1,
    "conclusion": "Recommendation with uncertain evidence",
    "evidence": [
      "local comparison"
    ],
    "uncertainty": [
      "not independently verified"
    ],
    "unresolved_issues": [
      "evidence gap"
    ],
    "dissent": [
      "MINORITY_DISSENT"
    ],
    "agreement_is_truth_probability": false
  },
  "preserved_objections": [
    {
      "issue_id": "51637c5b-09ca-5b5f-b4f4-e1aabe490d74",
      "source_hash": "220d5b6c931808de8d186003a44189c92f2ded1fe02af312ceae8e7706a8d251",
      "reference": "evidence",
      "reason": "MINORITY_DISSENT: independent evidence is missing",
      "verdict": "PARTIALLY_ACCEPT"
    },
    {
      "issue_id": "13c20ef4-51ef-57a8-8895-95a2e04dfacc",
      "source_hash": "738d033092d953ff5fd624d88aa38e07b45eb71bfa2455b4b7aba8216c6ee07f",
      "reference": "evidence",
      "reason": "MINORITY_DISSENT: independent evidence is missing",
      "verdict": "PARTIALLY_ACCEPT"
    },
    {
      "issue_id": "08684730-05a2-56e2-976f-74528c83fe0c",
      "source_hash": "898b46c3cefb45691595d4e88282e94ff967ec0728448ecb646b247d1ed03908",
      "reference": "INDEPENDENT_ANSWER_DIFFERENCE",
      "reason": "MAJORITY",
      "verdict": "DIFFERENT_ANSWERS"
    },
    {
      "issue_id": "e4c62cd9-afe6-55c1-a4d0-5d08ab089665",
      "source_hash": "a1f94ddb0dfe69db3fb4ccf1792364936bdc86b91919e6c3c34a106918c66f9e",
      "reference": "INDEPENDENT_ANSWER_DIFFERENCE",
      "reason": "MINORITY_DISSENT: missing evidence",
      "verdict": "DIFFERENT_ANSWERS"
    }
  ],
  "completed_revision": 25,
  "scope": "P05_OFFLINE_COUNCIL_NOT_LIVE_PROVIDER_CERTIFICATION"
}
```
