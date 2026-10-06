# وضعیت ادامهٔ پروژه

این نما خودکار از `ROADMAP.json`، `PROGRESS.json` و `CHECKS.json` ساخته شده است. ویرایش دستی مرجع نیست؛ پس از تغییر مبنا فرمان تولید را دوباره اجرا کنید.

شناسهٔ مبنای نما: `a03d9ee13bb1ae4acd475d89af3d8258dccda2c66b40cbf3331c0c5f142ee0c5`.

مرحلهٔ فعلی: `P02`. آخرین مرحلهٔ پذیرفته‌شده: `P01`.

خواسته‌های اجرایی تأییدشده: `0/30`. موفقیت ابزار توسعه، پذیرش محصول نیست.

## نقطهٔ دقیق ادامه

```json
{
  "phase": "P02",
  "last_verified_checkpoint": "P01",
  "completed_work": [
    "P00 and P01 accepted; original acceptance evidence preserved.",
    "P02 storage/prepared-intent slice passed 29 persistence, 60 foundation and 82 control tests on actual Windows and Linux.",
    "Three real process-exit cases passed on each OS; Windows test-helper leaks and Git evidence normalization were repaired."
  ],
  "working_changes": [
    "Full P02 send-start, result recording, ambiguity-safe resume, stale-result/decision rejection and remaining crash points are not implemented."
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
