# نتیجهٔ نهایی شورا

```text
{
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "2ac6385b-f0f7-40d4-a977-ccb31d55960c",
  "judge": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "previous_round_id": "37d9e8e9-6373-4753-b635-621cb6fffc60",
    "synthesis_round": {
      "round_id": "2ac6385b-f0f7-40d4-a977-ccb31d55960c",
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
      "provider_id": "mock",
      "model_id": "mock-v1",
      "mode": "API",
      "account_binding_id": null
    },
    "connection_revision": 0,
    "selected_revision": 51,
    "user_action_id": "777f0e50-45f2-4b2e-a6e0-8721f37c3b44",
    "actor": "EXPLICIT_OFFLINE_TEST_USER",
    "participated_in_rounds": [
      "84713164-9083-416b-beb3-878232b23d19",
      "534bb650-a91f-4257-8fc6-d2ced74c8c4c",
      "37d9e8e9-6373-4753-b635-621cb6fffc60"
    ],
    "bias_mitigation": "BLIND_ALL_EVIDENCE_WITH_DISSENT"
  },
  "judge_source_hash": "bc07285d29d0682f3f861f04bdae9515f7ecb2c0cd70fd6759122077da3ed8e7",
  "input_source_hashes": [
    "6fd77fb2283832945aeda2a5b08da74db1ea09cc5ffae369dd00eb4d835f363f",
    "c055b1d67fbd3b17369dd43fa6b2dc285755fc379be55f391db4baffbbd44a91",
    "31c30c656c9b0c9701d5aeb918b912d48846815555c1cc7cfb2106b3dc359165",
    "c9ff6dff9d369dbb0c757642aca04fb75385079b4bcf3cbe6982cf4e329592b9",
    "47a54206cdc166ee98a38b6753e0d98e6a03659a3dd5f0a03ef5fc50e05ecaf6",
    "60a84de8acbf42ea89b7c2c314007fb2df3f567af3a093134e62814098d26aba"
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
      "issue_id": "9d8062c6-25a3-5a47-af15-86f729e339bd",
      "source_hash": "31c30c656c9b0c9701d5aeb918b912d48846815555c1cc7cfb2106b3dc359165",
      "reference": "evidence",
      "reason": "MINORITY_DISSENT: independent evidence is missing",
      "verdict": "PARTIALLY_ACCEPT"
    },
    {
      "issue_id": "2a850720-20bc-5324-bbfe-f6d9152e54df",
      "source_hash": "c9ff6dff9d369dbb0c757642aca04fb75385079b4bcf3cbe6982cf4e329592b9",
      "reference": "evidence",
      "reason": "MINORITY_DISSENT: independent evidence is missing",
      "verdict": "PARTIALLY_ACCEPT"
    },
    {
      "issue_id": "474214d0-ecbf-538f-95dd-74e63aa98330",
      "source_hash": "6fd77fb2283832945aeda2a5b08da74db1ea09cc5ffae369dd00eb4d835f363f",
      "reference": "INDEPENDENT_ANSWER_DIFFERENCE",
      "reason": "MAJORITY",
      "verdict": "DIFFERENT_ANSWERS"
    },
    {
      "issue_id": "843c58a8-7d3c-5128-8152-721f65265ca3",
      "source_hash": "c055b1d67fbd3b17369dd43fa6b2dc285755fc379be55f391db4baffbbd44a91",
      "reference": "INDEPENDENT_ANSWER_DIFFERENCE",
      "reason": "MINORITY_DISSENT: missing evidence",
      "verdict": "DIFFERENT_ANSWERS"
    }
  ],
  "completed_revision": 58,
  "scope": "P05_OFFLINE_COUNCIL_NOT_LIVE_PROVIDER_CERTIFICATION"
}
```
