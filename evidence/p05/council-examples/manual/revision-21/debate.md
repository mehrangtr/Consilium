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

منشأ: `MANUAL`

```text
MAJORITY
```


## دور `1`

منشأ: `MANUAL`

```text
MINORITY_DISSENT: missing evidence
```


## دور `2`

منشأ: `MANUAL`

```text
{
  "critique_id": "9e9c967e-90bb-5022-a93a-a51bde4188d5",
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "582f60fe-1361-46fd-b959-ef225241c3c7",
  "reviewer_id": "00000000-0000-0000-0000-000000000002",
  "target_answer_id": "e06414aa-6455-5e15-b914-62b16cc4f5f9",
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


## دور `2`

منشأ: `MANUAL`

```text
{
  "critique_id": "0b37e64b-ae84-5d4a-ba7e-0857f5a67d81",
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "582f60fe-1361-46fd-b959-ef225241c3c7",
  "reviewer_id": "00000000-0000-0000-0000-000000000003",
  "target_answer_id": "692003c8-3403-54c1-8c54-f2f1276f2419",
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

منشأ: `MANUAL`

```text
MINORITY_DISSENT persists
```


## دور `3`

منشأ: `MANUAL`

```text
MINORITY_DISSENT persists
```


## تصمیم‌های کاربر


```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "988c5487-05be-4d56-b7d4-532f3975d3e0",
    "expected_revision": 9,
    "instruction": null,
    "kind": "PAUSE",
    "round_id": "830a229a-7e38-4066-8a81-16987a620e9f"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```

```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "7d9fa5f1-e5f9-4fd8-9b06-aa98aede60de",
    "expected_revision": 11,
    "instruction": null,
    "kind": "CONTINUE",
    "round_id": "830a229a-7e38-4066-8a81-16987a620e9f"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```

```text
{
  "decision": {
    "debate_id": "00000000-0000-0000-0000-000000000001",
    "decision_id": "295145f9-fee0-4915-91f9-8fce063de538",
    "expected_revision": 16,
    "instruction": "Resolve only missing evidence",
    "kind": "CUSTOM",
    "round_id": "582f60fe-1361-46fd-b959-ef225241c3c7"
  },
  "actor": "EXPLICIT_OFFLINE_TEST_USER"
}
```


## تحلیل دور

```text
{
  "debate_id": "00000000-0000-0000-0000-000000000001",
  "round_id": "830a229a-7e38-4066-8a81-16987a620e9f",
  "input_revision": 8,
  "source_hashes": [
    "898b46c3cefb45691595d4e88282e94ff967ec0728448ecb646b247d1ed03908",
    "a1f94ddb0dfe69db3fb4ccf1792364936bdc86b91919e6c3c34a106918c66f9e"
  ],
  "objections": [
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
  "round_id": "582f60fe-1361-46fd-b959-ef225241c3c7",
  "input_revision": 15,
  "source_hashes": [
    "898b46c3cefb45691595d4e88282e94ff967ec0728448ecb646b247d1ed03908",
    "a1f94ddb0dfe69db3fb4ccf1792364936bdc86b91919e6c3c34a106918c66f9e",
    "220d5b6c931808de8d186003a44189c92f2ded1fe02af312ceae8e7706a8d251",
    "738d033092d953ff5fd624d88aa38e07b45eb71bfa2455b4b7aba8216c6ee07f"
  ],
  "objections": [
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
  "round_id": "b6f99e13-afa2-4166-9c62-8e3c2843dc74",
  "input_revision": 20,
  "source_hashes": [
    "898b46c3cefb45691595d4e88282e94ff967ec0728448ecb646b247d1ed03908",
    "a1f94ddb0dfe69db3fb4ccf1792364936bdc86b91919e6c3c34a106918c66f9e",
    "220d5b6c931808de8d186003a44189c92f2ded1fe02af312ceae8e7706a8d251",
    "738d033092d953ff5fd624d88aa38e07b45eb71bfa2455b4b7aba8216c6ee07f",
    "87e885e108d225b76e76426ab25c5e9a3976e74e66eacb41305e49d8443504e0",
    "3528a2cb4b1dff4480a1674510ee2608bc3a81b7804968798c398d43b492aaa5"
  ],
  "objections": [
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
  "recommendation": "TARGETED",
  "recommendation_authorizes_round": false,
  "agreement_is_truth_probability": false,
  "method": "DETERMINISTIC_REPORTED_DIFFERENCES_NOT_SEMANTIC_TRUTH"
}
```
