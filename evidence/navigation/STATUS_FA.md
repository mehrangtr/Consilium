# وضعیت ادامهٔ پروژه

این نما خودکار از `ROADMAP.json`، `PROGRESS.json` و `CHECKS.json` ساخته شده است. ویرایش دستی مرجع نیست؛ پس از تغییر مبنا فرمان تولید را دوباره اجرا کنید.

شناسهٔ مبنای نما: `3954f437d22121ca748d1f13fd4887cf01492210660dc7c630da8ee230af38b2`.

مرحلهٔ فعلی: `P02`. آخرین مرحلهٔ پذیرفته‌شده: `P01`.

خواسته‌های اجرایی تأییدشده: `0/30`. موفقیت ابزار توسعه، پذیرش محصول نیست.

## نقطهٔ دقیق ادامه

```json
{
  "phase": "P02",
  "last_verified_checkpoint": "P01",
  "completed_work": [
    "Published P00/P01 acceptance preserved.",
    "P02 durable dispatch, result validation/confirmation, guarded decisions/retry, restart and JSON path implemented.",
    "Local suite passed; six review defects reproduced and repaired."
  ],
  "working_changes": [
    "Current-source native Windows/Linux execution and final acceptance review are pending."
  ],
  "next_action": "Execute current-source native Windows/Linux checks, inspect actual evidence and finalize the P02 criterion review; do not start P03 before its gate passes.",
  "next_command": "python tools/run_persistence_tests.py",
  "inputs_missing": [],
  "known_quirks": [
    {
      "id": "P02-001",
      "note": "Migrations V1 and V2 are append-only after publication. P02 is serial; ambiguous retry and live continuation are deliberately blocked. Capability schemas cannot certify actual provider behavior.",
      "references": [
        "docs/decisions/ADR-007-P02_DURABLE_DISPATCH_FA.md",
        "src/consilium/shell/schema_v2.py"
      ]
    }
  ]
}
```

## وضعیت مراحل

| مرحله | وضعیت | مانع‌های ثبت‌شده |
|---|---|---|
| `P00` | `COMPLETED` | 0 |
| `P01` | `COMPLETED` | 0 |
| `P02` | `IN_PROGRESS` | 1 |
| `P03` | `BLOCKED` | 1 |
| `P04` | `BLOCKED` | 1 |
| `P05` | `BLOCKED` | 1 |
| `P06` | `BLOCKED` | 1 |
| `P07` | `BLOCKED` | 1 |
| `P08` | `BLOCKED` | 1 |
| `P09` | `BLOCKED` | 1 |
| `P10` | `BLOCKED` | 1 |
| `P11` | `BLOCKED` | 1 |
| `P12` | `BLOCKED` | 1 |
| `P13` | `BLOCKED` | 1 |
| `P14` | `BLOCKED` | 1 |
| `P15` | `BLOCKED` | 1 |
| `P16` | `BLOCKED` | 1 |
