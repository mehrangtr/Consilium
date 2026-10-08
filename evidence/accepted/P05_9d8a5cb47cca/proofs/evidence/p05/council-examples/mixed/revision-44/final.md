# نتیجهٔ نهایی شورا

```text
{
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "f4e57bcd-5b1c-4a9a-8153-b5da99fa812b",
  "judge": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "previous_round_id": "5860c875-c827-4b2c-ae3a-b4c9b81eea98",
    "synthesis_round": {
      "round_id": "f4e57bcd-5b1c-4a9a-8153-b5da99fa812b",
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
    "selected_revision": 37,
    "user_action_id": "79930bc2-72d4-44c3-9dd6-21089f7a555c",
    "actor": "EXPLICIT_OFFLINE_TEST_USER",
    "participated_in_rounds": [
      "29c1d791-3a57-4800-b16e-112949ebf720",
      "e1928e2c-4455-4840-9e97-ac9dea6e2828",
      "5860c875-c827-4b2c-ae3a-b4c9b81eea98"
    ],
    "bias_mitigation": "BLIND_ALL_EVIDENCE_WITH_DISSENT"
  },
  "judge_source_hash": "8e67d3266cf47169fd05a1d1e78f7d312757daabfbcc5d68f7862d9fcc60fcb3",
  "input_source_hashes": [
    "58f977a64ccbc86009e3aba6e0e83994f432315da136d0b73fb69ed1bbd7b2d9",
    "fc4dd5be779a04c58d1ea1c7b6bb84e7875a007d9ad7386f8fe8079b6b8c8d76",
    "2b34667cb7955109bd55f02fd83dc94eee0742cc855573ac969961e3e64807bc",
    "cce5d6274ad28b07b84e42ab935a9239d14104229c09846dff942a80831df1e1",
    "616651bc43f6434ccf81ecda1bd0df27668f74a91f13f95caa37fb2a0547939a",
    "975192474e66fd4889beb9f5c2534c2df388ab70526d48c8253985b1e34cb89e"
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
      "issue_id": "49383dd9-8926-54bb-9b5e-ab27e7b67f62",
      "source_hash": "2b34667cb7955109bd55f02fd83dc94eee0742cc855573ac969961e3e64807bc",
      "reference": "evidence",
      "reason": "MINORITY_DISSENT: independent evidence is missing",
      "verdict": "PARTIALLY_ACCEPT"
    },
    {
      "issue_id": "d3d026a6-9a53-5365-8cd7-18cd43ec4767",
      "source_hash": "cce5d6274ad28b07b84e42ab935a9239d14104229c09846dff942a80831df1e1",
      "reference": "evidence",
      "reason": "MINORITY_DISSENT: independent evidence is missing",
      "verdict": "PARTIALLY_ACCEPT"
    },
    {
      "issue_id": "45d7fe56-a4b4-50b1-853a-84bc454758f8",
      "source_hash": "58f977a64ccbc86009e3aba6e0e83994f432315da136d0b73fb69ed1bbd7b2d9",
      "reference": "INDEPENDENT_ANSWER_DIFFERENCE",
      "reason": "MAJORITY",
      "verdict": "DIFFERENT_ANSWERS"
    },
    {
      "issue_id": "fba56f69-3f24-57f6-a0b9-19bcbd214bf9",
      "source_hash": "fc4dd5be779a04c58d1ea1c7b6bb84e7875a007d9ad7386f8fe8079b6b8c8d76",
      "reference": "INDEPENDENT_ANSWER_DIFFERENCE",
      "reason": "MINORITY_DISSENT: missing evidence",
      "verdict": "DIFFERENT_ANSWERS"
    }
  ],
  "completed_revision": 44,
  "scope": "P05_OFFLINE_COUNCIL_NOT_LIVE_PROVIDER_CERTIFICATION"
}
```
