# وضعیت ادامهٔ پروژه

این نما خودکار از `ROADMAP.json`، `PROGRESS.json` و `CHECKS.json` ساخته شده است. ویرایش دستی مرجع نیست؛ پس از تغییر مبنا فرمان تولید را دوباره اجرا کنید.

شناسهٔ مبنای نما: `3e9efee0f1f57d94da94c02cbbc31a1fc532906447666320d07a4687712e585f`.

مرحلهٔ فعلی: `P02`. آخرین مرحلهٔ پذیرفته‌شده: `P01`.

خواسته‌های اجرایی تأییدشده: `0/30`. موفقیت ابزار توسعه، پذیرش محصول نیست.

## نقطهٔ دقیق ادامه

```json
{
  "phase": "P02",
  "last_verified_checkpoint": "P01",
  "completed_work": [
    "P01 accepted with actual Windows/Linux evidence.",
    "P02 storage and prepared-intent slice implemented and locally tested."
  ],
  "working_changes": [
    "Native verification of the new P02 slice is pending."
  ],
  "next_action": "Implement the send-start ledger boundary, result persistence and guarded resume with real process-exit tests; no automatic retry for ambiguous delivery.",
  "next_command": "python tools/run_persistence_tests.py",
  "inputs_missing": [],
  "known_quirks": [
    {
      "id": "P02-001",
      "note": "Schema v1 supports PREPARED intents only; adding attempt states and retry attempts requires migration v2, never editing the checksum of v1.",
      "references": [
        "src/consilium/shell/storage.py",
        "docs/decisions/ADR-006-P02_STORAGE_SLICE_FA.md"
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
