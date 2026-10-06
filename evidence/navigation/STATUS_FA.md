# وضعیت ادامهٔ پروژه

این نما خودکار از `ROADMAP.json`، `PROGRESS.json` و `CHECKS.json` ساخته شده است. ویرایش دستی مرجع نیست؛ پس از تغییر مبنا فرمان تولید را دوباره اجرا کنید.

شناسهٔ مبنای نما: `7516664cb4e18496802c390b72fc5b3296e98fce5d47dd0f32a0cfb9e177168f`.

مرحلهٔ فعلی: `P03`. آخرین مرحلهٔ پذیرفته‌شده: `P02`.

خواسته‌های اجرایی تأییدشده: `0/30`. موفقیت ابزار توسعه، پذیرش محصول نیست.

## نقطهٔ دقیق ادامه

```json
{
  "phase": "P03",
  "last_verified_checkpoint": "P02",
  "completed_work": [
    "P02 accepted through the actual criterion gate; immutable source, original review, receipts and native graphs preserved.",
    "Exact code commit c46c4451c2e4a473ab3f4d574bb2357ba1a468e3 passed both selected OSs: 60 foundation, 82 control, 80 persistence tests, 12 real process-exit cases and 4 foundation CLI scenarios.",
    "Repeat P02 acceptance audit passed; original acceptance hashes and source remain unchanged; fresh Linux tests and existing exact-source native evidence revalidated.",
    "Full P02 source and acceptance evidence were published and verified on public main at 3bdf3f366bcc72679ae18480901b59d19c51ebe5. All 614 Git blob fingerprints and critical file contents matched. Standing GitHub access and publication authorization remain in force.",
    "P03 access preflight reached the actual DeepSeek sign-in page. No model prompt was sent; account, model, conversation and provider capabilities remain unverified."
  ],
  "working_changes": [],
  "next_action": "پذیرش و انتشار P02 کامل است. P03 تا فراهم‌شدن نشست مجاز و درخواست تازهٔ کاربر برای ورود مسدود است؛ درخواست امن ورود رد شد و نباید خودکار تکرار شود. سه معیار مرورگر واقعی باقی‌اند و P04 باز نمی‌شود.",
  "next_command": "python tools/qualityctl.py status",
  "inputs_missing": [
    "P03 authenticated session remains unverified. The secure authentication request was declined; do not re-request authentication unless the user explicitly asks."
  ],
  "known_quirks": [
    {
      "id": "P02-001",
      "note": "V1/V2 migrations are append-only. The P02 runner is serial and resume is read-only: ambiguous retry, continuing partial output and cross-account Recovery are not implemented. Capability schemas alone cannot certify a service.",
      "references": [
        "docs/decisions/ADR-007-P02_DURABLE_DISPATCH_FA.md"
      ]
    },
    {
      "id": "P03-001",
      "note": "P03 has no registered phase checks yet. Do not treat a successful development check or old P02 native report as P03 browser feasibility evidence. Register only genuine P03 checks when the probe exists.",
      "references": [
        "CHECKS.json",
        "ROADMAP.json"
      ]
    },
    {
      "id": "GIT-001",
      "note": "The final ZIP has the complete tested-code bundle. The repository preserves its earlier historical bundle; public main and code commit c46c4451c2e4a473ab3f4d574bb2357ba1a468e3 carry current code. See VALIDATION_REPORT.git_bundle_locations. Never replace final source/progress with a historical bundled snapshot.",
      "references": [
        "evidence/git/Consilium_Source.bundle",
        "HANDOFF.json"
      ]
    }
  ],
  "startup_commands": [
    "python tools/qualityctl.py navigation",
    "python tools/check.py",
    "python tools/qualityctl.py status"
  ],
  "next_task": {
    "id": "P03-FIRST-PROBE",
    "title": "بررسی محدود یک اتصال مرورگر منتخب از دامنهٔ مصوب",
    "status": "BLOCKED_AUTHENTICATION_DECLINED",
    "order": [
      "قواعد AGENTS و HANDOFF و PROGRESS و SCOPE و معیارهای P03 در ROADMAP را بخوان؛ وضعیت و بررسی توسعه را راستی‌آزمایی کن.",
      "برای یک سرویس مصوب مسیر مرورگر مجاز را تعیین کن؛ دسترسی، هویت حساب و گفتگو و انقضای نشست را UNKNOWN نگه دار تا مشاهدهٔ واقعی ثبت شود.",
      "آزمایش ارسال از دفتر عملیات عبور کند؛ شاهد ارسال، پاسخ جزئی/کامل و ادامهٔ همان گفتگو ثبت شود؛ ارسال مبهم خودکار تکرار نشود.",
      "گزارش بدون راز، جدول قابلیت‌ها و محدودیت مشاهده، و بازبرآورد زمان را با شاهد واقعی بنویس؛ بررسی‌های معتبر P03 و بازبینی سه معیار را ثبت کن."
    ],
    "definition_of_done": [
      "یک مسیر مرورگر واقعی با ورود کاربر، ارسال، دریافت پاسخ و ادامهٔ گفتگو شاهد دارد.",
      "حالت ورود منقضی و مشاهدهٔ نامطمئن روشن است؛ راه‌حل مانع احتمالی پیش از ادامه تعیین شده است.",
      "برآورد و جدول قابلیت‌های اتصال به‌روز شده‌اند."
    ],
    "blocked_next_phase": "P04",
    "budget": "Zero paid provider calls; no paid call authorization.",
    "windows_execution_responsibility": "Assistant; never delegate to user.",
    "uncertainty_policy": "No real capability certification from mock results; record access barriers explicitly.",
    "access_preflight": {
      "schema_version": 1,
      "phase": "P03",
      "status": "AUTHENTICATION_REQUIRED",
      "observation_kind": "LIVE_BROWSER_ACCESS_PREFLIGHT; NOT_PROVIDER_CAPABILITY_ACCEPTANCE",
      "observed_at_utc": "2026-10-06T15:39:42.627190+00:00",
      "provider_id": "deepseek",
      "target_url": "https://chat.deepseek.com",
      "observed_url": "https://chat.deepseek.com/sign_in",
      "browser": "Cloud Chrome CDP",
      "browser_tab_id": "1",
      "visible_state": "DeepSeek sign-in page with Log in, Log in with Google and Login with Apple controls; no signed-in conversation visible.",
      "account_identity": "UNVERIFIED",
      "model_identity": "UNVERIFIED",
      "conversation_identity": "NOT_CREATED",
      "delivery": "NOT_ATTEMPTED",
      "prompt_sent": false,
      "credentials_entered": false,
      "paid_calls": 0,
      "session_expiration": "NOT_TESTED; sign-in page alone does not prove expiration",
      "quota": "NOT_TESTED",
      "bot_detection": "NOT_OBSERVED; ordinary sign-in is not bot detection",
      "capabilities": "UNVERIFIED",
      "phase_acceptance": "NOT_RUN",
      "all_three_p03_criteria": "NOT_PASSED",
      "next_step": "Use the advertised secure browserAuth method choice and credential handoff if the user elects to authenticate; never ask for secrets in chat or infer capabilities before a real ledger-backed send."
    },
    "authentication_request": {
      "schema_version": 1,
      "phase": "P03",
      "provider_id": "deepseek",
      "recorded_at_utc": "2026-10-06T15:57:43.863378+00:00",
      "secure_browser_auth_result": "declined",
      "authentication_success": "NOT_CONFIRMED",
      "credential_values_read_or_logged": false,
      "provider_prompt_sent": false,
      "retry_without_new_user_authentication_request": false,
      "continuation_rule": "Respect the declined secure authentication request; do not retry credentials, switch sign-in method or offer another takeover unless the user requests authentication again."
    }
  },
  "acceptance_revalidation": {
    "path": "VALIDATION_REPORT.json",
    "sha256": "b1142013c2e3f23a7e08a27f2d27cb9633238b247e510479880bd36cd585e643",
    "section": "repeat_acceptance_review"
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
    "status": "VERIFIED_COMPLETE",
    "repository": "mehrangtr/Consilium",
    "destination": "https://github.com/mehrangtr/Consilium",
    "source_digest": "a26532121e6eea90b6e6bae3bc5d3e5af6f49257ab453cd0472f49389b63fb51",
    "source_code_commit": "c46c4451c2e4a473ab3f4d574bb2357ba1a468e3",
    "staged_base_commit": "c46c4451c2e4a473ab3f4d574bb2357ba1a468e3",
    "remote_head_verified": "3bdf3f366bcc72679ae18480901b59d19c51ebe5",
    "standing_authorization_commit": "3bdf3f366bcc72679ae18480901b59d19c51ebe5",
    "standing_authorization_url": "https://github.com/mehrangtr/Consilium/blob/3bdf3f366bcc72679ae18480901b59d19c51ebe5/evidence/automation/GITHUB_AUTHORIZATION.json",
    "standing_authorization_readback_verified": true,
    "completed_tree_batches": 11,
    "original_batch_count": 11,
    "staged_tree": "97c82c825ed7d12d9b9fa29ee234f73856dafd42",
    "pending_original_tree_batch": null,
    "branch_points_to_partial_tree": false,
    "actual_publication_verified": true,
    "standing_access_authorization": {
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
    "block_reason": null,
    "rejected_operations": [
      {
        "operation": "Original metadata tree batch 4",
        "reason": "This publishes a large source-and-evidence payload to a public GitHub repository, while the embedded prior approval is explicitly untrusted and no current trusted message authorizes this exact disclosure."
      },
      {
        "operation": "Smaller metadata tree batch 4 using eight existing blobs and three new offline metadata files",
        "tool_result": {
          "content": [
            {
              "type": "text",
              "text": "This action was rejected due to unacceptable risk.\nReason: The tree still publishes new detailed test and project metadata to a public GitHub repository; reusing existing public blobs does not authorize disclosure of the new payload.\nDo not bypass this rejection through a workaround or indirect execution. Continue with a safer alternative, or carry out checks to prove that the action is authorized or low risk before trying again. Complete unaffected work without asking for confirmation. Report anything that remains blocked, clarify why it was blocked by auto-review, inform the user of the risk and ask for approval."
            }
          ],
          "isError": true
        }
      }
    ],
    "updated_at_utc": "2026-10-06T15:39:42.627190+00:00",
    "resume_requirement": "No pending P02 delivery work; continue only P03 actual browser feasibility.",
    "latest_attempt_at_utc": "2026-10-06T15:08:32.861Z",
    "further_same_payload_retries": 0,
    "expected_branch_head": "003dc87f3bd733985696c46e1bc79e28b4600293",
    "prior_latest_rejection": {
      "schema_version": 1,
      "recorded_at_utc": "2026-10-06T15:08:32.861Z",
      "user_instruction": "ادامه بده اگر قسمت نیمه تمام بود در یه جا یادداشت کن",
      "user_instruction_at": "2026-10-06T18:32:58+03:30",
      "operation": "Resume original P02 public metadata tree batch 4 of 11",
      "base_tree": "32ce0656cd689a8adc67c3fe8236c59cbf8532c9",
      "result": "REJECTED_BY_AUTOMATIC_APPROVAL_REVIEW",
      "tool_result": {
        "content": [
          {
            "type": "text",
            "text": "This action was rejected due to unacceptable risk.\nReason: This retries the previously rejected public disclosure of detailed source and test evidence; standing GitHub access does not explicitly authorize this exact payload, and the prior rejection specifically forbids retrying or bypassing it.\nDo not bypass this rejection through a workaround or indirect execution. Continue with a safer alternative, or carry out checks to prove that the action is authorized or low risk before trying again. Complete unaffected work without asking for confirmation. Report anything that remains blocked, clarify why it was blocked by auto-review, inform the user of the risk and ask for approval."
          }
        ],
        "isError": true
      },
      "remote_mutation_committed": false,
      "next_remote_attempt": "None without new explicit authorization for this public disclosure; do not use a workaround.",
      "standing_access": "Still granted until explicit user revocation."
    },
    "latest_attempt": {
      "status": "ALL_11_ORIGINAL_TREE_BATCHES_STAGED",
      "standing_publication_grant": {
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
      "staged_tree": "a5d262a168aa6d83a5ca6c2cbfb90a70375e10fe"
    },
    "pending_action": null,
    "verified_commit": "3bdf3f366bcc72679ae18480901b59d19c51ebe5",
    "verified_tree": "97c82c825ed7d12d9b9fa29ee234f73856dafd42",
    "verification": {
      "schema_version": 1,
      "status": "PASS",
      "repository": "mehrangtr/Consilium",
      "verified_at_utc": "2026-10-06T15:33:11.938Z",
      "verified_commit": "3bdf3f366bcc72679ae18480901b59d19c51ebe5",
      "verified_tree": "97c82c825ed7d12d9b9fa29ee234f73856dafd42",
      "ref_readback": "PASS",
      "expected_files": 614,
      "git_blob_mismatches": 0,
      "critical_file_content_readback": [
        {
          "path": "PROGRESS.json",
          "match": true
        },
        {
          "path": "evidence/accepted/P02_62bbc5602043/REVIEW.json",
          "match": true
        },
        {
          "path": "evidence/automation/GITHUB_AUTHORIZATION.json",
          "match": true
        }
      ],
      "tested_source_commit": "c46c4451c2e4a473ab3f4d574bb2357ba1a468e3",
      "source_digest": "a26532121e6eea90b6e6bae3bc5d3e5af6f49257ab453cd0472f49389b63fb51",
      "native_tests": "Existing exact-source Windows/Linux 222 tests per OS; no new native run for metadata-only publication",
      "publication_authorization": "Standing GitHub access and public publication granted directly by user until explicit revocation",
      "repository_bundle": "Preserved historical bundle; public Git history and tested commit are the current code authority"
    },
    "record_scope": "Post-verification status cites the immutable content commit read back successfully; later status-only commits preserve its code and acceptance proofs."
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
  "unfinished_work": {
    "schema_version": 1,
    "updated_at_utc": "2026-10-06T15:57:43.863378+00:00",
    "canonical_location": "PROGRESS.json.resume.unfinished_work",
    "continuation_instruction": "Continue with standing access and publication permission; evaluate future impact of unfinished work.",
    "items": [
      {
        "id": "P03-001",
        "phase": "P03",
        "status": "BLOCKED_AUTHENTICATION_DECLINED",
        "title_fa": "آزمون واقعی یک اتصال مرورگر از دامنهٔ مصوب",
        "completed_fa": "قراردادها و مسیر دفتر عملیات بررسی شدند. دسترسی واقعی به صفحهٔ ورود DeepSeek در مرورگر ابری مشاهده شد؛ پیام آزمایشی هنوز ارسال نشده است. درخواست امن انتخاب روش ورود نیز با نتیجهٔ ردشده پایان یافت؛ موفقیت ورود تأیید نشده است.",
        "remaining_fa": "تعیین مسیر مرورگر مجاز و حساب و مدل منتخب، ثبت ارسال و پاسخ و ادامهٔ همان گفتگو، مشاهدهٔ انقضای نشست و ارسال نامطمئن، جدول قابلیت‌ها و بازبرآورد زمان، و ثبت بررسی‌های واقعی و بازبینی سه معیار.",
        "live_observation": "SIGN_IN_PAGE_OBSERVED; NO_SIGNED_IN_ACCOUNT_OR_MODEL_CALL",
        "registered_phase_checks": [],
        "prerequisites_unknown": [
          "Authorized live account and selected model identity",
          "Actual browser conversation and delivery evidence",
          "Expiration and quota observations"
        ],
        "integration_contracts": [
          {
            "file": "src/consilium/ports/adapter.py",
            "api": "Adapter.capabilities, send(AdapterRequest), probe(AdapterRequest)"
          },
          {
            "file": "src/consilium/core/contracts.py",
            "api": "ConnectionSpec, OperationIntent, AdapterRequest, TransportResult, DeliveryObservation"
          },
          {
            "file": "src/consilium/shell/storage.py",
            "api": "SQLiteStore.prepare_intent"
          },
          {
            "file": "src/consilium/shell/runner.py",
            "api": "DurableRunner.execute(request, adapter, expected_revision=...)"
          },
          {
            "file": "src/consilium/shell/ledger.py",
            "api": "begin_send, record_result, mark_interrupted, resume"
          }
        ],
        "required_behaviors": [
          "Keep real browser capabilities UNVERIFIED until genuine evidence is recorded; Mock does not certify a provider.",
          "Prepare and freeze intent before dispatch; remote browser I/O remains outside the database transaction.",
          "Classify an ambiguous attempt as UNKNOWN_DELIVERY and do not retry automatically.",
          "Identify account and conversation without persisting cookies, credentials, tokens or raw session data.",
          "Partial and complete response observations are distinct; continuation must refer to the same verified conversation.",
          "Use zero paid provider calls. Windows execution remains the assistant responsibility."
        ],
        "next_action_fa": "درخواست ورود را تکرار نکن. اگر کاربر بعداً صریحاً ورود را خواست، وضعیت تازهٔ صفحه را بخوان و مسیر امن را ادامه بده؛ پس از نشست مجاز، آزمون واقعی دفتر عملیات و هر سه معیار تکمیل شوند.",
        "done_when_fa": "هر سه معیار خروج `P03` در `ROADMAP.json` با شاهد واقعی پاس شده و گیت پذیرش اجرا شده باشد.",
        "access_preflight": {
          "schema_version": 1,
          "phase": "P03",
          "status": "AUTHENTICATION_REQUIRED",
          "observation_kind": "LIVE_BROWSER_ACCESS_PREFLIGHT; NOT_PROVIDER_CAPABILITY_ACCEPTANCE",
          "observed_at_utc": "2026-10-06T15:39:42.627190+00:00",
          "provider_id": "deepseek",
          "target_url": "https://chat.deepseek.com",
          "observed_url": "https://chat.deepseek.com/sign_in",
          "browser": "Cloud Chrome CDP",
          "browser_tab_id": "1",
          "visible_state": "DeepSeek sign-in page with Log in, Log in with Google and Login with Apple controls; no signed-in conversation visible.",
          "account_identity": "UNVERIFIED",
          "model_identity": "UNVERIFIED",
          "conversation_identity": "NOT_CREATED",
          "delivery": "NOT_ATTEMPTED",
          "prompt_sent": false,
          "credentials_entered": false,
          "paid_calls": 0,
          "session_expiration": "NOT_TESTED; sign-in page alone does not prove expiration",
          "quota": "NOT_TESTED",
          "bot_detection": "NOT_OBSERVED; ordinary sign-in is not bot detection",
          "capabilities": "UNVERIFIED",
          "phase_acceptance": "NOT_RUN",
          "all_three_p03_criteria": "NOT_PASSED",
          "next_step": "Use the advertised secure browserAuth method choice and credential handoff if the user elects to authenticate; never ask for secrets in chat or infer capabilities before a real ledger-backed send."
        },
        "authentication_request": {
          "schema_version": 1,
          "phase": "P03",
          "provider_id": "deepseek",
          "recorded_at_utc": "2026-10-06T15:57:43.863378+00:00",
          "secure_browser_auth_result": "declined",
          "authentication_success": "NOT_CONFIRMED",
          "credential_values_read_or_logged": false,
          "provider_prompt_sent": false,
          "retry_without_new_user_authentication_request": false,
          "continuation_rule": "Respect the declined secure authentication request; do not retry credentials, switch sign-in method or offer another takeover unless the user requests authentication again."
        }
      }
    ],
    "future_phases": {
      "ids": [
        "P04",
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
      "status": "NOT_STARTED; BLOCKED_BY_PREVIOUS_PHASE",
      "note_fa": "این مرحله‌ها کار آینده‌اند؛ کار نیمه‌انجام‌شده یا نقص مرحلهٔ دو محسوب نمی‌شوند."
    },
    "preserve_completed_work": {
      "phases": [
        "P00",
        "P01",
        "P02"
      ],
      "source_digest": "a26532121e6eea90b6e6bae3bc5d3e5af6f49257ab453cd0472f49389b63fb51",
      "source_changed": false,
      "native_test_counts_per_os": {
        "foundation": 60,
        "control": 82,
        "persistence": 80
      },
      "rerun_policy_fa": "مرحلهٔ پذیرفته‌شده را فقط در صورت تغییر منبع یا شکست و ناسازگاری شاهد دوباره اجرا کن."
    },
    "execution_rules": {
      "external_step_seconds": 45,
      "shell_test_seconds": 60,
      "progress_update_seconds": 60,
      "same_failure_retry_limit": 1,
      "checkpoint_after_confirmed_step": true,
      "automatic_rejection_retry_allowed": false,
      "report_unknown_as_success": false
    },
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
      }
    ]
  }
}
```

## وضعیت مراحل

| مرحله | وضعیت | مانع‌های ثبت‌شده |
|---|---|---|
| `P00` | `COMPLETED` | 0 |
| `P01` | `COMPLETED` | 0 |
| `P02` | `COMPLETED` | 0 |
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
