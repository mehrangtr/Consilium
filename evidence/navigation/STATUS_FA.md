# وضعیت ادامهٔ پروژه

این نما خودکار از `ROADMAP.json`، `PROGRESS.json` و `CHECKS.json` ساخته شده است. ویرایش دستی مرجع نیست؛ پس از تغییر مبنا فرمان تولید را دوباره اجرا کنید.

شناسهٔ مبنای نما: `dbb5995cd4db731161f2d16a1831ffcac0ae069cba52d2165dbe692df0c35343`.

مرحلهٔ فعلی: `P01`. آخرین مرحلهٔ پذیرفته‌شده: `P00`.

خواسته‌های اجرایی تأییدشده: `0/30`. موفقیت ابزار توسعه، پذیرش محصول نیست.

## نقطهٔ دقیق ادامه

```json
{
  "phase": "P01",
  "last_verified_checkpoint": "P00",
  "completed_work": [
    "دامنه و موجودی مرحلهٔ صفر پذیرفته شدند.",
    "قراردادهای داده، اتصال ساختگی و مرز خصوصی پیاده و در لینوکس آزموده شدند.",
    "نقص‌های بازبینی پایان مرحله با آزمون قرمز اصلاح شدند؛ نصب وابستگی در محیط مجازی تازه و ساخت و ورود بستهٔ نصب‌شده روی لینوکس موفق بود."
  ],
  "working_changes": [
    "گردش‌کار بومی دو محیط و بررسی تجمیعی آماده است؛ انتشار عمومی هنوز مجاز نشده و آزمون واقعی ویندوز انجام نشده است."
  ],
  "next_action": "دستیار پس از اجازهٔ انتشار عمومی همین بسته در مخزن متصل mehrangtr/Consilium، گردش‌کار دو محیط را اجرا و گزارش‌های واقعی را دریافت کند؛ کار ویندوز به کاربر واگذار نشود. پس از بررسی شواهد و بازبینی نهایی، گیت P01 بررسی شود؛ پیش از پذیرش P02 شروع نشود.",
  "next_command": "REMOTE_ACTION: Publish approved checkpoint; run .github/workflows/check.yml; download combined-P01-evidence",
  "inputs_missing": [
    "Permission to publish this checkpoint publicly in mehrangtr/Consilium",
    "Native Windows execution evidence for this exact source snapshot"
  ],
  "known_quirks": [
    {
      "id": "DEV-003",
      "note": "شواهد پذیرش معیار به‌صورت تصویر ثابت حفظ می‌شوند؛ فایل جاری در مرحله بعد می‌تواند تغییر کند.",
      "references": [
        "tools/qualityctl.py::freeze_review_evidence",
        "tests/test_qualityctl.py::test_accepted_criterion_bytes_survive_later_changes"
      ]
    },
    {
      "id": "P01-001",
      "note": "DELIVERY و RESPONSE دو محور جدا هستند؛ مشاهده به ورودی و اتصال قبلی وابسته است.",
      "references": [
        "src/consilium/core/contracts.py",
        "src/consilium/adapters/mock.py"
      ]
    },
    {
      "id": "P01-002",
      "note": "موفقیت check یا دادهٔ ساختگی، پذیرش بومی Windows نیست. نبود شاهد، کد خروج 2 برای گیت دارد.",
      "references": [
        "tools/check_target_matrix.py",
        "docs/RUNBOOK_FA.md"
      ]
    },
    {
      "id": "DEV-004",
      "note": "ثبت‌کنندهٔ بومی خروجی‌های قابل بازنویسی را پیش از اجرا پاک و شکست یا پایان مهلت را ثبت می‌کند. چهار سناریو و جزئیات گزارش باید سازگار باشند.",
      "references": [
        "tools/record_target_checks.py",
        "tools/check_target_matrix.py",
        "tests/test_native_recording.py"
      ]
    },
    {
      "id": "DEV-005",
      "note": "آزمون‌های کنترل از test_*.py کشف می‌شوند؛ خروجی‌های build و dist و egg-info وارد هش منبع نمی‌شوند.",
      "references": [
        "tools/run_control_tests.py",
        "tools/qualityctl.py"
      ]
    },
    {
      "id": "DEV-006",
      "note": "کار ویندوز به کاربر واگذار نمی‌شود. مخزن متصل عمومی و خالی است؛ داشتن دسترسی فنی، اجازهٔ انتشار این بسته نیست. گردش‌کار شواهد کهنه را در پوشهٔ موقت کنار می‌گذارد و مرحله را خودکار نمی‌پذیرد.",
      "references": [
        "docs/AUTOMATED_WINDOWS_FA.md",
        ".github/workflows/check.yml",
        "docs/decisions/ADR-005-AUTONOMOUS_NATIVE_TESTS_FA.md"
      ]
    }
  ]
}
```

## وضعیت مراحل

| مرحله | وضعیت | مانع‌های ثبت‌شده |
|---|---|---|
| `P00` | `COMPLETED` | 0 |
| `P01` | `IN_PROGRESS` | 2 |
| `P02` | `BLOCKED` | 1 |
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
