# تاریخچهٔ شورا

شناسهٔ بحث: `00000000-0000-0000-0000-000000000001`

پرسش اصلی:

```text
  انتخاب روش پژوهش
با حفظ محدودیت‌ها  
```

وضعیت: `COMPLETED`

توافق به معنی احتمال درستی نیست.


## دور `1`

منشأ: `MOCK`

```text
MAJORITY
```


## دور `1`

منشأ: `MANUAL`

```text
MINORITY_DISSENT: missing evidence
```


## دور `2`

منشأ: `MOCK`

```text
{
  "critique_id": "520b43f3-8a40-5cf0-ac6c-7799a9954a9c",
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "e1928e2c-4455-4840-9e97-ac9dea6e2828",
  "reviewer_id": "00000000-0000-0000-0000-000000000002",
  "target_answer_id": "259c8c0a-7bd3-54e5-acc7-57d06c099a49",
  "points": [
    {
      "verdict": "PARTIALLY_ACCEPT",
      "reference": "evidence",
      "reason": "MINORITY_DISSENT: independent evidence is missing"
    },
    {
      "verdict": "ACCEPT",
      "reference": "cost",
      "reason": "constraint preserved"
    }
  ],
  "score": 6,
  "scoring_reason": "Explicit rubric; missing evidence reduces confidence",
  "rubric_version": "council-rubric.v1",
  "strengths": [
    "constraint preserved"
  ],
  "weaknesses": [
    "missing evidence"
  ]
}
```


## دور `2`

منشأ: `MANUAL`

```text
{
  "critique_id": "cd455ec0-9f8c-5a01-b757-9623d1250b19",
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "e1928e2c-4455-4840-9e97-ac9dea6e2828",
  "reviewer_id": "00000000-0000-0000-0000-000000000003",
  "target_answer_id": "c00281bb-5cae-53b4-b0b7-e0d52e60d714",
  "points": [
    {
      "verdict": "PARTIALLY_ACCEPT",
      "reference": "evidence",
      "reason": "MINORITY_DISSENT: independent evidence is missing"
    },
    {
      "verdict": "ACCEPT",
      "reference": "cost",
      "reason": "constraint preserved"
    }
  ],
  "score": 6,
  "scoring_reason": "Explicit rubric; missing evidence reduces confidence",
  "rubric_version": "manual-rubric.v1",
  "strengths": [
    "constraint preserved"
  ],
  "weaknesses": [
    "missing evidence"
  ]
}
```


## دور `3`

منشأ: `MOCK`

```text
MAJORITY
```


## دور `3`

منشأ: `MANUAL`

```text
MINORITY_DISSENT persists
```


## دور `4`

منشأ: `MOCK`

```text
{"schema_version": 1, "conclusion": "Recommendation with uncertain evidence", "evidence": ["local comparison"], "uncertainty": ["not independently verified"], "unresolved_issues": ["evidence gap"], "dissent": ["MINORITY_DISSENT"], "agreement_is_truth_probability": false}
```


## تصمیم‌های کاربر


```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "a5c327f9-a2c4-4579-b460-1beccc00bc41",
    "expected_revision": 13,
    "instruction": null,
    "kind": "PAUSE",
    "round_id": "29c1d791-3a57-4800-b16e-112949ebf720"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```

```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "9804a02d-28ca-4d14-952f-9d1abe58ba96",
    "expected_revision": 15,
    "instruction": null,
    "kind": "CONTINUE",
    "round_id": "29c1d791-3a57-4800-b16e-112949ebf720"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```

```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "3453f876-3fab-4be3-a884-031c8c55c4c0",
    "expected_revision": 25,
    "instruction": "Resolve only missing evidence",
    "kind": "CUSTOM",
    "round_id": "e1928e2c-4455-4840-9e97-ac9dea6e2828"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```

```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "b13f5145-fa17-4537-a2ed-b6b2ceb4921c",
    "expected_revision": 35,
    "instruction": null,
    "kind": "FINISH",
    "round_id": "5860c875-c827-4b2c-ae3a-b4c9b81eea98"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```


## تحلیل دور

```text
{
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "29c1d791-3a57-4800-b16e-112949ebf720",
  "input_revision": 12,
  "source_hashes": [
    "58f977a64ccbc86009e3aba6e0e83994f432315da136d0b73fb69ed1bbd7b2d9",
    "fc4dd5be779a04c58d1ea1c7b6bb84e7875a007d9ad7386f8fe8079b6b8c8d76"
  ],
  "objections": [
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
  "recommendation": "REVIEW",
  "recommendation_authorizes_round": false,
  "agreement_is_truth_probability": false,
  "method": "DETERMINISTIC_REPORTED_DIFFERENCES_NOT_SEMANTIC_TRUTH"
}
```


## تحلیل دور

```text
{
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "e1928e2c-4455-4840-9e97-ac9dea6e2828",
  "input_revision": 24,
  "source_hashes": [
    "58f977a64ccbc86009e3aba6e0e83994f432315da136d0b73fb69ed1bbd7b2d9",
    "fc4dd5be779a04c58d1ea1c7b6bb84e7875a007d9ad7386f8fe8079b6b8c8d76",
    "2b34667cb7955109bd55f02fd83dc94eee0742cc855573ac969961e3e64807bc",
    "cce5d6274ad28b07b84e42ab935a9239d14104229c09846dff942a80831df1e1"
  ],
  "objections": [
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
  "recommendation": "TARGETED",
  "recommendation_authorizes_round": false,
  "agreement_is_truth_probability": false,
  "method": "DETERMINISTIC_REPORTED_DIFFERENCES_NOT_SEMANTIC_TRUTH"
}
```


## تحلیل دور

```text
{
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "5860c875-c827-4b2c-ae3a-b4c9b81eea98",
  "input_revision": 34,
  "source_hashes": [
    "58f977a64ccbc86009e3aba6e0e83994f432315da136d0b73fb69ed1bbd7b2d9",
    "fc4dd5be779a04c58d1ea1c7b6bb84e7875a007d9ad7386f8fe8079b6b8c8d76",
    "2b34667cb7955109bd55f02fd83dc94eee0742cc855573ac969961e3e64807bc",
    "cce5d6274ad28b07b84e42ab935a9239d14104229c09846dff942a80831df1e1",
    "616651bc43f6434ccf81ecda1bd0df27668f74a91f13f95caa37fb2a0547939a",
    "975192474e66fd4889beb9f5c2534c2df388ab70526d48c8253985b1e34cb89e"
  ],
  "objections": [
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
  "recommendation": "TARGETED",
  "recommendation_authorizes_round": false,
  "agreement_is_truth_probability": false,
  "method": "DETERMINISTIC_REPORTED_DIFFERENCES_NOT_SEMANTIC_TRUTH"
}
```


## نتیجهٔ نهایی و افشای داور

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
