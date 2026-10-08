# تاریخچهٔ شورا

شناسهٔ بحث: `00000000-0000-0000-0000-000000000001`

پرسش اصلی:

```text
  انتخاب روش پژوهش
با حفظ محدودیت‌ها  
```

وضعیت: `WAITING_DECISION`

توافق به معنی احتمال درستی نیست.


## دور `1`

منشأ: `MOCK`

```text
MAJORITY
```


## دور `1`

منشأ: `MOCK`

```text
MINORITY_DISSENT: missing evidence
```


## دور `2`

منشأ: `MOCK`

```text
{
  "critique_id": "55e2e9e1-f9d0-5c1b-8f3f-c2bb9030c420",
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "534bb650-a91f-4257-8fc6-d2ced74c8c4c",
  "reviewer_id": "00000000-0000-0000-0000-000000000002",
  "target_answer_id": "145e5302-fd7c-5560-b69f-75c00f6c1b30",
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

منشأ: `MOCK`

```text
{
  "critique_id": "2b32ef67-2396-5915-8d8a-1fab479f712b",
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "534bb650-a91f-4257-8fc6-d2ced74c8c4c",
  "reviewer_id": "00000000-0000-0000-0000-000000000003",
  "target_answer_id": "54105173-af54-58ef-aff3-c39505295f70",
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


## دور `3`

منشأ: `MOCK`

```text
MAJORITY
```


## دور `3`

منشأ: `MOCK`

```text
MINORITY_DISSENT: missing evidence
```


## تصمیم‌های کاربر


```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "13857d5a-aee6-46b9-874c-d109ca3070d4",
    "expected_revision": 17,
    "instruction": null,
    "kind": "PAUSE",
    "round_id": "84713164-9083-416b-beb3-878232b23d19"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```

```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "81cd49a6-e10d-4de3-9c48-e4592964d14c",
    "expected_revision": 19,
    "instruction": null,
    "kind": "CONTINUE",
    "round_id": "84713164-9083-416b-beb3-878232b23d19"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```

```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "b6501fce-b594-4eb4-8c07-4aee409f38ce",
    "expected_revision": 34,
    "instruction": "Resolve only missing evidence",
    "kind": "CUSTOM",
    "round_id": "534bb650-a91f-4257-8fc6-d2ced74c8c4c"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```


## تحلیل دور

```text
{
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "84713164-9083-416b-beb3-878232b23d19",
  "input_revision": 16,
  "source_hashes": [
    "6fd77fb2283832945aeda2a5b08da74db1ea09cc5ffae369dd00eb4d835f363f",
    "c055b1d67fbd3b17369dd43fa6b2dc285755fc379be55f391db4baffbbd44a91"
  ],
  "objections": [
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
  "round_id": "534bb650-a91f-4257-8fc6-d2ced74c8c4c",
  "input_revision": 33,
  "source_hashes": [
    "6fd77fb2283832945aeda2a5b08da74db1ea09cc5ffae369dd00eb4d835f363f",
    "c055b1d67fbd3b17369dd43fa6b2dc285755fc379be55f391db4baffbbd44a91",
    "31c30c656c9b0c9701d5aeb918b912d48846815555c1cc7cfb2106b3dc359165",
    "c9ff6dff9d369dbb0c757642aca04fb75385079b4bcf3cbe6982cf4e329592b9"
  ],
  "objections": [
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
  "round_id": "37d9e8e9-6373-4753-b635-621cb6fffc60",
  "input_revision": 48,
  "source_hashes": [
    "6fd77fb2283832945aeda2a5b08da74db1ea09cc5ffae369dd00eb4d835f363f",
    "c055b1d67fbd3b17369dd43fa6b2dc285755fc379be55f391db4baffbbd44a91",
    "31c30c656c9b0c9701d5aeb918b912d48846815555c1cc7cfb2106b3dc359165",
    "c9ff6dff9d369dbb0c757642aca04fb75385079b4bcf3cbe6982cf4e329592b9",
    "47a54206cdc166ee98a38b6753e0d98e6a03659a3dd5f0a03ef5fc50e05ecaf6",
    "60a84de8acbf42ea89b7c2c314007fb2df3f567af3a093134e62814098d26aba"
  ],
  "objections": [
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
  "recommendation": "TARGETED",
  "recommendation_authorizes_round": false,
  "agreement_is_truth_probability": false,
  "method": "DETERMINISTIC_REPORTED_DIFFERENCES_NOT_SEMANTIC_TRUTH"
}
```
