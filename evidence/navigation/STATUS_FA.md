# وضعیت ادامهٔ پروژه

این نما خودکار از `ROADMAP.json`، `PROGRESS.json` و `CHECKS.json` ساخته شده است. ویرایش دستی مرجع نیست؛ پس از تغییر مبنا فرمان تولید را دوباره اجرا کنید.

شناسهٔ مبنای نما: `1bc6ce4717f4b369ec023d49e1c0703d2f092a8920b159598562ae79f61be30a`.

مرحلهٔ فعلی: `P04`. آخرین مرحلهٔ پذیرفته‌شده: `P03`.

خواسته‌های اجرایی تأییدشده: `0/30`. موفقیت ابزار توسعه، پذیرش محصول نیست.

## نقطهٔ دقیق ادامه

```json
{
  "phase": "P04",
  "last_verified_checkpoint": "P03",
  "completed_work": [
    "P00-P02 acceptance preserved",
    "P03 current-context defect fixed; 44 probe tests and 272 total per actual native OS",
    "P03 actual positive/observer-loss/controlled sign-out evidence and corrected five-provider estimate accepted",
    "P04 contract draft and adversarial test matrix prepared; no P04 implementation yet"
  ],
  "working_changes": [
    "P04 question contracts and independent context: 18 offline tests; native proof recording extended"
  ],
  "next_action": "مهاجرت نسخه‌دار پایگاه داده برای ثبت پیشنهاد و تأیید کاربر را با آزمون بازگشایی و تعارض نسخه بساز؛ سپس سیاست ارسال را تکمیل کن. دور مستقل هنوز به ارسال زنده متصل نیست.",
  "next_command": "python tools/qualityctl.py status",
  "startup_commands": [
    "python tools/qualityctl.py status",
    "python tools/qualityctl.py navigation --check",
    "python tools/check.py"
  ],
  "inputs_missing": [],
  "known_quirks": [
    "start() now requires current_context; CLI start requires --current-context; never use cached initial_context as live proof",
    "Current Claude session signed out by controlled test; offline P04 needs no login",
    "Natural expiration, quota and full recovery uncertified; preserve UNKNOWN_DELIVERY without resend",
    "P03 acceptance-only evidence check validates historical records; exclude it from P04 regressions, keep offline safety tests",
    "Prior estimate 294-502 excluded extra scoped connections and is superseded; current scoped reserve estimate 420-718 hours",
    "P03 immutable accepted source is 70e86a...; current cb9928... differs only in transfer allowlist maintenance and is independently native-tested. Do not rewrite historical live evidence source stamps.",
    "Historical Git bundle is a pre-P03 backup, not current application code. It now matches the existing public file. Prior local checkpoint remains in archive/pre-public-source-sync-20261006; current checkout aligned with verified public main."
  ],
  "next_task": {
    "id": "P04-001",
    "phase": "P04",
    "status": "OFFLINE_SLICE_AND_BOTH_NATIVE_TARGETS_VERIFIED_INTEGRATION_PENDING",
    "title_fa": "قرارداد اصل پرسش، پیشنهاد معمار و پذیرش نسخهٔ جدید",
    "completed_fa": "پرسش و پیشنهاد و پذیرش نسخه و زمینهٔ اولیهٔ مستقل و بازیابی دقیق ورودی پیاده شدند؛ هجده آزمون محلی پاس شدند.",
    "remaining_fa": "ثبت پایدار تأیید کاربر، مهاجرت پایگاه داده، سیاست حریم خصوصی و بودجه، تاریخچهٔ دوردست و پذیرش کامل مرحله باقی است. شاهد بومی این برش در هر دو محیط پاس شده است.",
    "next_action_fa": "مهاجرت نسخه‌دار پایگاه داده برای ثبت پیشنهاد و تأیید کاربر را با آزمون بازگشایی و تعارض نسخه بساز؛ سپس سیاست ارسال را تکمیل کن. دور مستقل هنوز به ارسال زنده متصل نیست.",
    "done_when_fa": "اصل متن و قیود دقیق محفوظ؛ پیشنهاد ناسازگار و پذیرش نامعتبر رد؛ تغییرهای مجاز قابل مقایسه؛ آزمون‌های واقعی و رگرسیون سبز؛ تحویل به‌روز."
  },
  "unfinished_work": {
    "schema_version": 1,
    "updated_at_utc": "2026-10-06T23:29:08.363475+00:00",
    "canonical_location": "PROGRESS.json:resume.unfinished_work",
    "continuation_instruction": "Continue implemented P04 slice; do not replay P03 browser probes. Native evidence for the new source remains pending.",
    "items": [
      {
        "id": "P04-001",
        "phase": "P04",
        "status": "OFFLINE_SLICE_AND_BOTH_NATIVE_TARGETS_VERIFIED_INTEGRATION_PENDING",
        "title_fa": "قرارداد اصل پرسش، پیشنهاد معمار و پذیرش نسخهٔ جدید",
        "completed_fa": "پرسش و پیشنهاد و پذیرش نسخه و زمینهٔ اولیهٔ مستقل و بازیابی دقیق ورودی پیاده شدند؛ هجده آزمون محلی پاس شدند.",
        "remaining_fa": "ثبت پایدار تأیید کاربر، مهاجرت پایگاه داده، سیاست حریم خصوصی و بودجه، تاریخچهٔ دوردست و پذیرش کامل مرحله باقی است. شاهد بومی این برش در هر دو محیط پاس شده است.",
        "next_action_fa": "مهاجرت نسخه‌دار پایگاه داده برای ثبت پیشنهاد و تأیید کاربر را با آزمون بازگشایی و تعارض نسخه بساز؛ سپس سیاست ارسال را تکمیل کن. دور مستقل هنوز به ارسال زنده متصل نیست.",
        "done_when_fa": "اصل متن و قیود دقیق محفوظ؛ پیشنهاد ناسازگار و پذیرش نامعتبر رد؛ تغییرهای مجاز قابل مقایسه؛ آزمون‌های واقعی و رگرسیون سبز؛ تحویل به‌روز."
      }
    ],
    "completed_items": [
      {
        "id": "PUB-P02-001",
        "phase": "P02_DELIVERY",
        "status": "COMPLETED",
        "title_fa": "ثبت کامل عمومی پذیرش و بستهٔ تحویل مرحلهٔ دو",
        "completed_fa": "همهٔ بخش‌ها روی شاخهٔ اصلی منتشر شدند؛ اثرانگشت ۶۱۴ فایل، نسخهٔ شاخه و محتوای فایل‌های اصلی دوردست تطبیق داشتند.",
        "remaining_fa": "هیچ کار باز در انتشار پذیرش مرحلهٔ دو باقی نمانده است.",
        "reason_fa": "مجوز صریح انتشار دریافت شد و بررسی خودکار انتقال را پذیرفت.",
        "checkpoint": {
          "staged_tree": "a5d262a168aa6d83a5ca6c2cbfb90a70375e10fe",
          "completed_batches": 11,
          "total_batches": 11,
          "remote_head_verified": "003dc87f3bd733985696c46e1bc79e28b4600293",
          "source_digest": "a26532121e6eea90b6e6bae3bc5d3e5af6f49257ab453cd0472f49389b63fb51"
        },
        "next_action_fa": "برای انتشار مرحلهٔ دو دوباره از ابتدا شروع نکن؛ مرحلهٔ سه را از شاهد دسترسی واقعی ادامه بده.",
        "done_when_fa": "تمام کد و شواهد مورد نظر روی شاخهٔ مقصد ثبت و بایت فایل‌های دوردست با بستهٔ نهایی تطبیق داده شده باشد.",
        "verified_publication_commit": "3bdf3f366bcc72679ae18480901b59d19c51ebe5"
      },
      {
        "id": "P03-PREP-001",
        "phase": "P03_PREPARATION",
        "status": "COMPLETED",
        "title_fa": "ابزار ثبت و بررسی آفلاین آزمون مرورگر",
        "completed_fa": "کد و راهنمای اجرا و آزمون‌های منفی و قطع پردازه تکمیل شدند؛ بررسی واقعی ویندوز و لینوکس و گراف گزارش‌ها پاس شد. این نتیجه پذیرش مرورگر زنده نیست.",
        "remaining_fa": "هیچ کار باز در این برش آماده‌سازی باقی نمانده است؛ اجرای زنده در P03-001 حفظ شده است.",
        "code_commit": "db2ef3073d84d560de00738cd9878df47e4f6dc4",
        "source_digest": "a14e4bcfaf7cd9f982bb52d96037d099608e12c1d541855041a4491e25723c19"
      },
      {
        "id": "P03-001",
        "phase": "P03",
        "status": "COMPLETED_LIMITED_FEASIBILITY",
        "title_fa": "پذیرش مستند امکان‌سنجی مرورگر و اصلاح آغاز با شاهد تازه",
        "acceptance": {
          "source_digest": "70e86ab5179e978f8d0dcdc387647689412493f05ac750569bd3d764c1d22118",
          "receipt": {
            "path": "evidence/runs/20261006T232625Z_9d9f3ac539/RUN.json",
            "sha256": "e8a177f7a9ff3ea6e9ed2285429c64d6f07db581d653868bf26a5417784ed256"
          },
          "review": {
            "path": "evidence/accepted/P03_a1134261e9ea/REVIEW.json",
            "sha256": "b9e731c218467e7ab0755bba011ce49369efac921d63da08b92931f61b05304b"
          },
          "checkpoint": {
            "path": "evidence/browser-probe/P03_FEASIBILITY_CHECKPOINT.json",
            "sha256": "eb3a8dd9a24b420b4830030cdce7bf40babaefb766f28a404a22d3c591a48b20"
          },
          "native_matrix": {
            "path": "evidence/target-matrix/RUN.json",
            "sha256": "65e4c4d02c9b5109a4c691d87e9fee736c856298c074ccac011292966357cb54"
          },
          "code_commit": "21bb52523072bd6f0193602b94ffb1387d5bc2ea",
          "natural_expiration": "UNKNOWN_NOT_CERTIFIED",
          "full_driver_and_recovery": "NOT_IMPLEMENTED_OR_CERTIFIED"
        },
        "preserve_policy": "Keep two confirmed operations and one unknown attempt; no automatic resend; private raw trace stays private; current session signed out."
      },
      {
        "id": "PUB-P03-001",
        "phase": "P03_DELIVERY",
        "status": "COMPLETED",
        "title_fa": "ثبت پذیرش و تحویل مرحلهٔ سه و طرح آغاز مرحلهٔ چهار روی شاخهٔ اصلی",
        "verified_commit": "baceaf1291818be695b65565756c948c81e43651",
        "verified_files": 194,
        "source_digest": "cb99286e53059e175bb409da98be8e0805efe7ac1dc327430f2cae8c201a2d4f",
        "remaining_fa": "هیچ کار باز در این انتشار باقی نمانده است؛ اجرای کد مرحلهٔ چهار در P04-001 ثبت است."
      }
    ],
    "future_phases": {
      "ids": [
        "P05",
        "P06",
        "P07",
        "P08",
        "P09",
        "P10",
        "P11",
        "P12",
        "P13",
        "P14",
        "P15",
        "P16"
      ],
      "status": "NOT_STARTED; BLOCKED_BY_PREVIOUS_PHASE"
    },
    "execution_rules": {
      "external_step_seconds": 45,
      "shell_test_seconds": 60,
      "progress_update_seconds": 60,
      "same_failure_retry_limit": 1,
      "checkpoint_after_confirmed_step": true,
      "automatic_rejection_retry_allowed": false,
      "report_unknown_as_success": false
    }
  },
  "p03_acceptance": {
    "source_digest": "70e86ab5179e978f8d0dcdc387647689412493f05ac750569bd3d764c1d22118",
    "receipt": {
      "path": "evidence/runs/20261006T232625Z_9d9f3ac539/RUN.json",
      "sha256": "e8a177f7a9ff3ea6e9ed2285429c64d6f07db581d653868bf26a5417784ed256"
    },
    "review": {
      "path": "evidence/accepted/P03_a1134261e9ea/REVIEW.json",
      "sha256": "b9e731c218467e7ab0755bba011ce49369efac921d63da08b92931f61b05304b"
    },
    "checkpoint": {
      "path": "evidence/browser-probe/P03_FEASIBILITY_CHECKPOINT.json",
      "sha256": "eb3a8dd9a24b420b4830030cdce7bf40babaefb766f28a404a22d3c591a48b20"
    },
    "native_matrix": {
      "path": "evidence/target-matrix/RUN.json",
      "sha256": "65e4c4d02c9b5109a4c691d87e9fee736c856298c074ccac011292966357cb54"
    },
    "code_commit": "21bb52523072bd6f0193602b94ffb1387d5bc2ea",
    "natural_expiration": "UNKNOWN_NOT_CERTIFIED",
    "full_driver_and_recovery": "NOT_IMPLEMENTED_OR_CERTIFIED"
  },
  "current_authentication_handoff": {
    "schema_version": 1,
    "phase": "P03",
    "provider_id": "anthropic",
    "recorded_at_utc": "2026-10-06T23:21:34.886Z",
    "authentication_success": "SIGNED_OUT_AFTER_CONTROLLED_AUTHENTICATION_LOSS_TEST",
    "manual_login_completed_by_user": true,
    "manual_handoff_status": "COMPLETED_AND_VERIFIED",
    "credential_values_read_or_logged": false,
    "historical_preparation_record": "evidence/browser-probe/P03_CLAUDE_MANUAL_AUTH_PREPARATION.json",
    "server_account_id_verified": false,
    "authentication_evidence": "Positive UI observation preserved in private user evidence package; no account/conversation identity or raw text published",
    "private_evidence_package_sha256": "4fb4cf7ce4960d55e6a33edc15f3b7a73b5b1da3f27595f112d088c93db476fa",
    "current_evidence": {
      "path": "evidence/browser-probe/P03_AUTHLOSS_AFTER.json",
      "sha256": "92170baca991a19dca7f8df9a99093a378f79f517fdfcc3cf1df2327b9392c35"
    },
    "offline_p04_requires_login": false
  },
  "github_authorization": {
    "schema_version": 1,
    "status": "STANDING_GITHUB_ACCESS_AND_PUBLICATION_GRANTED",
    "repository": "mehrangtr/Consilium",
    "visibility": "public",
    "granted_at": "2026-10-06T18:50:57+03:30",
    "scope": "GitHub access and public publication of reviewed Consilium source, documents and non-secret test evidence",
    "valid_until": "Explicit later user stop or revocation",
    "reconfirm_routine_authorized_work": false,
    "direct_user_message": "بله دسترسی کامل به گیت هاب و انتشار را تا زمانی که متوقف نکردم برای همیشه داری"
  },
  "github_user_authorization_evidence": {
    "exact_user_message": "بله دسترسی کامل به گیت هاب و انتشار را تا زمانی که متوقف نکردم برای همیشه داری",
    "at": "2026-10-06T18:50:57+03:30",
    "access_and_publication_expires": "Only explicit later user revocation",
    "automatic_review_status": "AUTHORIZED_TREE_TRANSFERS_SUCCEEDED"
  },
  "execution_recovery_policy": {
    "task_step_timeout_seconds": 45,
    "shell_test_timeout_seconds": 60,
    "progress_report_interval_seconds": 60,
    "same_failure_retry_limit": 1,
    "checkpoint_after_confirmed_operation": true,
    "reconcile_remote_before_retry": true,
    "do_not_restart_passed_phases_without_changed_source_or_failed_evidence": true,
    "immutable_acceptance_records": true,
    "distinguish_execution_from_verified_result": true,
    "external_tool_timeout_caveat": "A local timer cannot guarantee cancellation of the external connector. An unresponsive operation must be abandoned/reconciled; it must not block already valid source or acceptance metadata.",
    "large_transfer_policy": "Keep large optional history artifacts in the verified deliverable. Publish code and acceptance metadata independently. Do not repeatedly submit multi-megabyte connector arguments.",
    "phase_barrier": "P02 accepted and publication verified. P03 is blocked by declined authentication; P04 remains blocked until genuine P03 criteria pass."
  },
  "public_publication": {
    "status": "COMPLETED_REVIEWED_SOURCE_AND_EVIDENCE_ON_MAIN",
    "tested_source_commit": "dead9ed58ee8bbefe7d2a425021dacc051aeb4d8",
    "tested_source_digest": "cb99286e53059e175bb409da98be8e0805efe7ac1dc327430f2cae8c201a2d4f",
    "standing_authorization": "ACTIVE",
    "private_raw_evidence_publication": "WITHHELD; prior automatic rejection retained",
    "verified_artifact_commit": "c53e33764219832deed92774184ede8f6f90383a",
    "verified_file_count": 194,
    "verification": "Exact remote UTF-8 content and Git blob SHA for every changed file; main head matched; source unchanged after publication",
    "verified_at_utc": "2026-10-06T23:41:32.996372+00:00",
    "target_branch": "main",
    "unfinished_publication_work": false,
    "portable_files_verified": 670,
    "legacy_backup_sync": "Exact published Git blob df5bbb1abd58b6f540c1793e0d2a75023a8a1a9a retrieved through ordinary authorized Git fetch; no replacement backup uploaded",
    "local_public_tree_reconciliation": "PASS; previous local checkpoint preserved"
  },
  "historical_resume_source": {
    "repository": "mehrangtr/Consilium",
    "commit": "c44e6352c0b45c6a81b0e7ba30b492e3089a2a28",
    "path": "PROGRESS.json",
    "meaning": "Historical login attempts and preflight checkpoint; current record supersedes pending-login/natural-wait instructions"
  },
  "last_tested_source_checkpoint": {
    "source_digest": "cb99286e53059e175bb409da98be8e0805efe7ac1dc327430f2cae8c201a2d4f",
    "code_commit": "dead9ed58ee8bbefe7d2a425021dacc051aeb4d8",
    "native_run_id": 37547041855,
    "native_matrix": {
      "path": "evidence/target-matrix/RUN.json",
      "sha256": "bc899c3b3a1d9be2995772eefd2641faa23fe795c14224b8bc1a891263e98dc2"
    },
    "tests_per_os": 272,
    "scope": "NATIVE_OFFLINE_REGRESSION; P04_IMPLEMENTATION_NOT_STARTED"
  },
  "native_checkpoint": {
    "schema_version": 1,
    "phase": "P04",
    "status": "OFFLINE_SLICE_VERIFIED_NOT_PHASE_ACCEPTED",
    "source_digest": "54424d1e1b4d8eec347fc67351ec3d3bb5f4cf705da82c1812076b0c14d804d5",
    "code_commit": "f150ffa2ac35f198a5fe5e102850e232995b51ce",
    "workflow_run_id": 37572086193,
    "workflow_url": "https://github.com/mehrangtr/Consilium/actions/runs/37572086193",
    "native_targets": [
      {
        "target": "Windows",
        "status": "PASS",
        "control_tests": 88,
        "foundation_tests": 60,
        "persistence_tests": 80,
        "browser_probe_tests": 44,
        "architect_tests": 18,
        "evidence": {
          "path": "evidence/targets/Windows/20261007T043439Z_53e985a1/RUN.json",
          "sha256": "5d53a321c4a49622d669d3b2d62bd9ece9f3791fa0fd4c679d2bf4ebd314a28a"
        }
      },
      {
        "target": "Linux",
        "status": "PASS",
        "control_tests": 88,
        "foundation_tests": 60,
        "persistence_tests": 80,
        "browser_probe_tests": 44,
        "architect_tests": 18,
        "evidence": {
          "path": "evidence/targets/Linux/20261007T043419Z_c14161ac/RUN.json",
          "sha256": "79cefdec0e882b46cd2a2e6f0def4168965c66932424990dd05c6b92540ca8c1"
        }
      }
    ],
    "phase_check_receipt": {
      "phase": "P04",
      "receipt": "evidence/runs/20261007T043611Z_86a8480a5a/RUN.json",
      "sha256": "a4bb9ac5a9ed3a0cf1a69e3137774b309d737c488812bca4f24aba269df611d0"
    },
    "review": "Separate author review: structural projection and recovery only; no independent reviewer; no live dispatch or remote-history guarantee.",
    "remaining": [
      "durable trusted-user adoption and versioned database migration",
      "dispatch privacy and budget policy",
      "remote conversation identity and history authorization",
      "full P04 exits and acceptance review"
    ],
    "continuation": "Implement durable adoption before connecting this context to live dispatch. Do not replay P03 sends."
  }
}
```

## وضعیت مراحل

| مرحله | وضعیت | مانع‌های ثبت‌شده |
|---|---|---|
| `P00` | `COMPLETED` | 0 |
| `P01` | `COMPLETED` | 0 |
| `P02` | `COMPLETED` | 0 |
| `P03` | `COMPLETED` | 0 |
| `P04` | `IN_PROGRESS` | 0 |
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
