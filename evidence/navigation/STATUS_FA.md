# وضعیت ادامهٔ پروژه

این نما خودکار از `ROADMAP.json`، `PROGRESS.json` و `CHECKS.json` ساخته شده است. ویرایش دستی مرجع نیست؛ پس از تغییر مبنا فرمان تولید را دوباره اجرا کنید.

شناسهٔ مبنای نما: `630dfc526e314008bb1afc5308a8c60968038436ce9aa02e89382e109bc016c4`.

مرحلهٔ فعلی: `P06`. آخرین مرحلهٔ پذیرفته‌شده: `P05`.

خواسته‌های اجرایی تأییدشده: `0/30`. موفقیت ابزار توسعه، پذیرش محصول نیست.

## نقطهٔ دقیق ادامه

```json
{
  "phase": "P06",
  "last_verified_checkpoint": "P05",
  "completed_work": [
    "P00–P05 acceptance snapshots and all 30 protected requirements remain unchanged.",
    "P05 PR13 merged at af60bdfa70046a75ce9bd4c5f6c56ae7cd4f9e2f; original accepted source c01c0633 retains 622 tests/39 product process exits per OS.",
    "P05 repaired-source CI 37803460536 passed 624 tests per OS before merge.",
    "Current quality source 5c44278b passed all four CI jobs at 37804861086: 656 tests per native OS, both report graphs, and dependency advisory audit.",
    "P06 preregistration and atomic private observation journal passed 17 accounting/protocol/crash tests on both OSs; preflight passes."
  ],
  "working_changes": [
    "PR16 manual-output.v2 fix is merged; its 698-test native evidence is historical after the control-test-only deadline change.",
    "PR17 initial Windows run 37905506414 failed one timing-sensitive control test. Failure and a deterministic pre-fix reproduction are retained; test fixture deadlines changed without changing production limits.",
    "Private actual prompts/responses and pending UI boundaries remain outside public repository."
  ],
  "next_action": "Verify the control-test deadline correction on fresh native Windows and Linux runs, then reconcile the blocked P06 browser boundaries without blind resend. P06 remains unaccepted; P07 must not start.",
  "next_command": "python runtime_driver.py status # در فضای خصوصی اجرای P06",
  "startup_commands": [
    "python tools/qualityctl.py status",
    "python tools/qualityctl.py navigation --check",
    "python tools/development_supervisor.py check"
  ],
  "next_task": {
    "id": "P06-001",
    "phase": "P06",
    "status": "BLOCKED_REAL_EVIDENCE_AND_BROWSER_APPROVAL",
    "title_fa": "پایلوت زودهنگام کیفیت",
    "next_action_fa": "ابتدا رسیدهای خصوصی و مرزهای ارسال را بخوان. نقد کوئن در PILOT-007/COUNCIL نامعلوم است. نقد کوئن در PILOT-015/COUNCIL یک بار ارسال شده ولی مشاهدهٔ پایان با رد خودکار ابزار مسدود شد؛ فقط همان برگهٔ موجود بدون ناوبری یا ارسال دوباره باید پس از رفع رد بررسی شود. در PILOT-020/REPEATED_SINGLE دو پاسخ مستقل پذیرفته شده‌اند؛ نقد اول دارای STARTED منطقی است اما پرکردن کادر رد شد و Enter اجرا نشد. قبل از ادامه وضعیت همان صفحه را بررسی کن. چهار گروه چندمرحله‌ای 001/005 با سقف اصلی شش فراخوانی مسدودند. شورای 020 هنوز پس از معمار شروع نشده است. هیچ مرز مبهم را دوباره نفرست و هیچ سقف یا شکست را حذف نکن. شواهد بومی تازهٔ قالب دستی برای هر محیط 698 آزمون موفق دارند. P06 بدون خروجی‌های کامل، ارزیابی کور، بررسی خطاهای کنترل و بازبرآورد پذیرفته نیست.",
    "completed_fa": "P00–P05 پذیرفته‌شده‌اند؛ 66 فراخوانی واقعی مشاهده‌شده و 16 خروجی نهایی P06 ثبت شده است. آزمون‌های 003، 008 و 010 در هر سه روش کامل‌اند. روش مستقل و تکرار 015 و روش مستقل 020 کامل‌اند.",
    "remaining_fa": "نقد و جمع‌بندی باقی‌مانده، رفع رد خودکار دو اقدام مرورگر، حل چهار مانع سقف اصلی و مرز نامعلوم 007، ارزیابی کور و بازبرآورد.",
    "done_when_fa": "هر سه معیار اصلی پایان P06 با شواهد واقعی بررسی و پذیرفته شوند."
  },
  "inputs_missing": [
    "Measured prior engineering hours, or a reviewed treatment of their genuine absence",
    "Reviewed resolution of original six-call ceiling for four blocked PILOT-001/PILOT-005 multiround groups",
    "Resolution of automatic approval rejection for existing-tab Qwen completion observation and Claude prompt fill; no indirect workaround",
    "Read-only reconciliation of unknown Qwen PILOT-007 review submission before any resend"
  ],
  "unfinished_work": {
    "phase": "P06",
    "items": [
      {
        "id": "P06-001",
        "status": "BLOCKED_BROWSER_APPROVAL_AND_RECORDED_BUDGET_GATES",
        "instruction": "ابتدا رسیدهای خصوصی و مرزهای ارسال را بخوان. نقد کوئن در PILOT-007/COUNCIL نامعلوم است. نقد کوئن در PILOT-015/COUNCIL یک بار ارسال شده ولی مشاهدهٔ پایان با رد خودکار ابزار مسدود شد؛ فقط همان برگهٔ موجود بدون ناوبری یا ارسال دوباره باید پس از رفع رد بررسی شود. در PILOT-020/REPEATED_SINGLE دو پاسخ مستقل پذیرفته شده‌اند؛ نقد اول دارای STARTED منطقی است اما پرکردن کادر رد شد و Enter اجرا نشد. قبل از ادامه وضعیت همان صفحه را بررسی کن. چهار گروه چندمرحله‌ای 001/005 با سقف اصلی شش فراخوانی مسدودند. شورای 020 هنوز پس از معمار شروع نشده است. هیچ مرز مبهم را دوباره نفرست و هیچ سقف یا شکست را حذف نکن. شواهد بومی تازهٔ قالب دستی برای هر محیط 698 آزمون موفق دارند. P06 بدون خروجی‌های کامل، ارزیابی کور، بررسی خطاهای کنترل و بازبرآورد پذیرفته نیست."
      }
    ],
    "updated_at_utc": "2026-10-09T08:24:28.879772+00:00"
  },
  "native_evidence": {
    "phase": "P01",
    "scope": "HISTORICAL_MANUAL_OUTPUT_CONTRACT_NATIVE_VERIFICATION_NOT_CURRENT_SOURCE_NOT_P06_ACCEPTANCE",
    "source_digest": "bbf23b0737d444deaa1013737263a77a755c5e9cf6e1c3be731ed475afdfcf0f",
    "targets": [
      {
        "target": "Windows",
        "status": "PASS",
        "control_tests": 117,
        "foundation_tests": 60,
        "persistence_tests": 104,
        "browser_probe_tests": 44,
        "architect_tests": 264,
        "council_tests": 41,
        "quality_tests": 15,
        "pilot_tests": 53,
        "evidence": {
          "path": "evidence/targets/Windows/20261009T005939Z_875bc0e2/RUN.json",
          "sha256": "7709422d816c9002986f5edb014a99d66e0f044404466a412935a8054a7d7e3b"
        }
      },
      {
        "target": "Linux",
        "status": "PASS",
        "control_tests": 117,
        "foundation_tests": 60,
        "persistence_tests": 104,
        "browser_probe_tests": 44,
        "architect_tests": 264,
        "council_tests": 41,
        "quality_tests": 15,
        "pilot_tests": 53,
        "evidence": {
          "path": "evidence/targets/Linux/20261009T005909Z_4dc6b628/RUN.json",
          "sha256": "973781bd01505d88a7cf517ba58cd0396fbfc220115dd09b7a441099fd4967f3"
        }
      }
    ],
    "status": "PASS",
    "workflow_run_id": 37867476416,
    "tests_per_target": 698,
    "phase_accepted": false,
    "code_commit": "e15601f9bd2985f5795649b836ad763261acd8ee",
    "source_matches_current": false,
    "current_source_digest": "009e61d15ce3bd85ab5afff6879b96b1ae87230f5dd9e6649b5fcb1cb063a06e",
    "current_source_verification": "PENDING_NATIVE_WINDOWS_AND_LINUX"
  },
  "last_verified_in_phase_checkpoint": {
    "phase": "P05",
    "path": "evidence/accepted/P05_9d8a5cb47cca/REVIEW.json",
    "sha256": "3b829a028ce1a1fa3d79cf5562b9352fc85109deed89c2e4d7adf3bd3ab50c35",
    "source_digest": "c01c0633233eb7b35a9cf6319f75497771632ddf7b3fe3ad6e0f7300bdf6dad8",
    "phase_accepted": true
  },
  "final_p04_checkpoint": {
    "phase": "P04",
    "status": "FULL_PHASE_ACCEPTED",
    "source_digest": "a8cb0b5371a5cf89c917b2039e5756bdc4c9875d7aff8a69ed65ab8d1d5001a4",
    "code_commit": "10c27c56187299120b2545ddca65014ec17bacff",
    "native_run_id": 37689915269,
    "target_reports": [
      {
        "target": "Windows",
        "report": {
          "path": "evidence/targets/Windows/20261007T213134Z_852f5a32/RUN.json",
          "sha256": "53b928a14137cd954a022851ec31ccd9ab3c86f9e6dbb58fceb5fca1a3183acf"
        },
        "status": "PASS",
        "source_matches_current": true,
        "scope": "RECORDED_TARGET_ARTIFACTS_NOT_PHASE_ACCEPTANCE"
      },
      {
        "target": "Linux",
        "report": {
          "path": "evidence/targets/Linux/20261007T213059Z_f6ac87c9/RUN.json",
          "sha256": "e177aefd4993f30a420735d85c26c07678090ecff0959e3723eb81e8bacd27cb"
        },
        "status": "PASS",
        "source_matches_current": true,
        "scope": "RECORDED_TARGET_ARTIFACTS_NOT_PHASE_ACCEPTANCE"
      }
    ],
    "tests_per_native_target": 579,
    "product_process_exit_cases_per_native_target": 33,
    "configured_receipt": "evidence/runs/20261007T214338Z_b2beabd35a/RUN.json",
    "accepted_review": "evidence/accepted/P04_1113045dc1c2/REVIEW.json",
    "reviewer_independent": false,
    "all_original_exit_criteria_pass": true,
    "phase_accepted": true,
    "live_provider_calls": 0,
    "paid_calls": 0,
    "source_publication_journal_blob": "ed036121ab6ced7dd1b6f4b87d70a9bf4d127482",
    "native_supervisor_receipts": [
      {
        "path": "evidence/development-supervisor/0fb407c4062842a8ad4fd2f6f4b8798a/STATE.json",
        "sha256": "f27dba2e19bde0eb46fe152094e31ffad49203988971d7c283b656665779a8ed"
      },
      {
        "path": "evidence/development-supervisor/f3630088602b473bbc3db487ab52525f/STATE.json",
        "sha256": "651a4b020e1efe7f70713889d92e5b71707a448b70f42cb4a3990a41c5b31ad3"
      }
    ],
    "next_phase": "P05",
    "remaining_in_P04": []
  },
  "final_p05_checkpoint": {
    "phase": "P05",
    "status": "FULL_PHASE_ACCEPTED",
    "source_digest": "c01c0633233eb7b35a9cf6319f75497771632ddf7b3fe3ad6e0f7300bdf6dad8",
    "code_commit": "ddf33b24f41aa2c5ee0609800bd9f440165b72b5",
    "native_run_id": 37756543373,
    "native_run_conclusion": "success",
    "targets": [
      {
        "target": "Windows",
        "report": {
          "path": "evidence/targets/Windows/20261008T092548Z_c743026e/RUN.json",
          "sha256": "a397686ffd0f7d9785f01a959ccf93a18ee6e670857d64e0fc7459007108d345"
        },
        "status": "PASS",
        "source_matches_current": true,
        "scope": "RECORDED_TARGET_ARTIFACTS_NOT_PHASE_ACCEPTANCE"
      },
      {
        "target": "Linux",
        "report": {
          "path": "evidence/targets/Linux/20261008T092538Z_270c21cd/RUN.json",
          "sha256": "3c403515a4843c634efd259f13c8d66af9d92a068cc988db2866a8c5f54fa703"
        },
        "status": "PASS",
        "source_matches_current": true,
        "scope": "RECORDED_TARGET_ARTIFACTS_NOT_PHASE_ACCEPTANCE"
      }
    ],
    "tests_per_target": 622,
    "council_tests_per_target": 40,
    "product_process_exit_cases_per_target": 39,
    "supervisor_receipts": [
      {
        "path": "evidence/development-supervisor/5c46770cd8514b6080c561e0fbfdf9d8/STATE.json",
        "sha256": "d85cea99a9c7ef51c488a5f5a64f216ce869b6c8a55ae0321db32a811117d38b",
        "steps": [
          "native"
        ]
      },
      {
        "path": "evidence/development-supervisor/a757ba25d02749588492f2bc92707aaa/STATE.json",
        "sha256": "55d9bf20564dc2f5819505384138cb5bdd659f49da2c1c4921d3efcc5ae408be",
        "steps": [
          "native"
        ]
      }
    ],
    "reviewer_independent": false,
    "phase_accepted": true,
    "live_provider_calls": 0,
    "paid_calls": 0,
    "configured_receipt": "evidence/runs/20261008T093202Z_2c8a59775c/RUN.json",
    "accepted_review": "evidence/accepted/P05_9d8a5cb47cca/REVIEW.json",
    "accepted_review_sha256": "3b829a028ce1a1fa3d79cf5562b9352fc85109deed89c2e4d7adf3bd3ab50c35",
    "all_original_exit_criteria_pass": true,
    "remaining_in_P05": [],
    "next_phase": "P06",
    "formal_supervisor_receipt": {
      "path": "evidence/development-supervisor/cfd01dfef867402ca7648f9dcd308c50/STATE.json",
      "sha256": "3838810b319b19b3d8ec2a7ae72d9c5a3d1ac4c49df9a15e3492b9d9f024e68d"
    }
  },
  "known_quirks": [
    "No real P06 model quality comparison has run: 0/24 final outputs. Copied/manual origin claims are not authenticated by the journal alone.",
    "Only offline mock policy-managed sends are enabled. Live API/browser drivers retain P08/P09 gates; real P06 responses use the authorized manual product flow.",
    "Named peer review needs explicit authorization. FINISH metadata is blinded separately; answer text is not identity-scrubbed.",
    "300s idle/900s hard limits supervise owned processes, not ChatGPT/MCP. External calls use 25s waits and ambiguous writes are read/reconciled; server commits never auto-retry.",
    "P03 historical browser sends/sign-out must not be replayed without a new scoped reason.",
    "P06 checker blocks until live protocol outputs, blind scoring, actual product-flow review, error findings and measured-hours reestimate are registered.",
    "Failed Windows run 37801218935 is retained. Resolved 8.3 paths and the measured 90s architect deadline passed on both native OSs; aggregate 240s and 300/900 supervisor limits remain.",
    "License choice and scheduled/conditional enhancements remain open; native test success does not close them or establish full 30-requirement conformance.",
    "Original P05 acceptance c01c0633 remains immutable; current P06 source 72926f3b has separate native verification.",
    "Pinned development tools and advisory audit passed on native CI 37827407312; the failed local runtime check and earlier native lint failures remain preserved."
  ],
  "developer_supervisor": {
    "idle_seconds": 300,
    "hard_seconds": 900,
    "native_verified": true,
    "scope": "OWNED_PROCESSES_NOT_CHATGPT_OR_MCP_CANCELLATION",
    "native_scope": "CURRENT_P06_OFFLINE_SOURCE_BOTH_NATIVE_TARGETS_VERIFIED",
    "native_run_id": 37827407312
  },
  "transfer_reviewed_file_count": null,
  "latest_followup_recheck": {
    "path": "evidence/p06/offline-native-37827407312/REVIEW.json",
    "sha256": "cb794a8e63a943b4913fd2952af033aade917c5095eca2e70b113422833cf831",
    "tests_per_target": 692,
    "whole_native_check_status": "PASS",
    "fresh_windows_status": "PASS",
    "scope": "CURRENT_SOURCE_OFFLINE_ONLY_NOT_P06_ACCEPTANCE"
  },
  "historical_checkpoint_note": "Fields inside final_p04_checkpoint/final_p05_checkpoint describe their original acceptance-time source comparisons; they do not certify the current working source.",
  "previous_local_quality_source": {
    "source_digest": "9a61ab6bf1da54fe5a8e7ce219ed01d4f8772b4627dfe79fc7d5d05032951c8e",
    "linux_report": {
      "path": "evidence/targets/Linux/20261008T143749Z_4f24d565/RUN.json",
      "sha256": "bf5119206b29e143508592eb87a436642bc76e052b16792f2d725090b6a3b8a6"
    },
    "passed_cases": 639,
    "whole_native_status": "FAIL",
    "scope": "HISTORICAL_LOCAL_CHECK"
  },
  "p05_publication": {
    "status": "MERGED",
    "pr_number": 13,
    "pr_url": "https://github.com/mehrangtr/Consilium/pull/13",
    "merge_commit": "af60bdfa70046a75ce9bd4c5f6c56ae7cd4f9e2f",
    "fresh_repaired_source": "af3aa954cb47da32effbe281005925fbaa448b93bb38f242636276f4d7a25875",
    "fresh_native_run_id": 37803460536,
    "tests_per_target": 624
  },
  "approved_enhancement_verification": {
    "source_manifest": "APPROVED_ENHANCEMENTS.json",
    "manifest_scope": "FROZEN_IMPLEMENTATION_CHECKPOINT_BEFORE_NATIVE_VERIFICATION",
    "current_native_status": "PASS_WITH_RECORDED_SCOPE_LIMITS",
    "evidence": {
      "path": "evidence/quality-improvements/native-37804861086/RECHECK.json",
      "sha256": "a559ce5eed513407858952e5f4a98071c99c8708d8d9742e587a22e67e53107f"
    },
    "still_pending_ids": [
      "E08",
      "E16",
      "E19",
      "E24",
      "E25",
      "E26"
    ],
    "full_v1_conformance": "NOT_RUN"
  },
  "previous_quality_native_evidence": {
    "scope": "CURRENT_QUALITY_SOURCE_NOT_P06_ACCEPTANCE",
    "source_digest": "5c44278b5f6a52c4276e4d7d7c17af2f3633cca8ae8db44cce4420be830767f7",
    "whole_native_status": "PASS",
    "fresh_linux_status": "PASS",
    "fresh_windows_status": "PASS",
    "workflow_run_id": 37804861086,
    "tests_per_target": 656,
    "targets": [
      {
        "target": "Windows",
        "status": "PASS",
        "source_matches_current": true,
        "report": {
          "path": "evidence/targets/Windows/20261008T155730Z_fefd9f7e/RUN.json",
          "sha256": "861c5456e8a62fc970af870ae03a1b15ef9ea65bc10a60357fcfcfea7f60baaa"
        },
        "test_counts": {
          "control": {
            "tests": 117,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "foundation": {
            "tests": 60,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "persistence": {
            "tests": 104,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "browser_probe": {
            "tests": 44,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "architect": {
            "tests": 259,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "council": {
            "tests": 40,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "quality": {
            "tests": 15,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "pilot": {
            "tests": 17,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          }
        },
        "tests_total": 656
      },
      {
        "target": "Linux",
        "status": "PASS",
        "source_matches_current": true,
        "report": {
          "path": "evidence/targets/Linux/20261008T155709Z_225bf944/RUN.json",
          "sha256": "8ff0a877cd345aabcb80181a97fb6321b06b762bf614482a18a5549d9d488d37"
        },
        "test_counts": {
          "control": {
            "tests": 117,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "foundation": {
            "tests": 60,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "persistence": {
            "tests": 104,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "browser_probe": {
            "tests": 44,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "architect": {
            "tests": 259,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "council": {
            "tests": 40,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "quality": {
            "tests": 15,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          },
          "pilot": {
            "tests": 17,
            "failures": 0,
            "errors": 0,
            "skipped": 0
          }
        },
        "tests_total": 656
      }
    ],
    "dependency_audit": {
      "path": "evidence/security-audit/native-37804861086/RUN.json",
      "sha256": "44328f797469cf17d84517417893ee035db35a0861cf2903d21f9f080cda9cfc"
    },
    "historical_P05_evidence": "resume.final_p05_checkpoint; acceptance-time snapshot only",
    "supervisor_receipts": [
      {
        "path": "evidence/development-supervisor/61497e98197d4c3f9c618045ecabe3b5/STATE.json",
        "sha256": "73aa3544ad01b24a9ac1cd393514121c4d94ae0ebe8c1e37dccbe008f1f151a0"
      },
      {
        "path": "evidence/development-supervisor/0cae1ee92e96492392f5c1e62d3286f0/STATE.json",
        "sha256": "18f26eeda7ba2f1f8f855b8dd8599a4a5419590bcd46774a5abfa9d84155b986"
      }
    ]
  },
  "p06_offline_work": {
    "status": "VERIFIED_OFFLINE_ONLY",
    "real_model_runs": 0,
    "real_final_outputs": 0,
    "required_final_outputs": 24,
    "browser_used": false,
    "new_scope": [
      "Failure and linked repair accounting within unchanged budgets",
      "Shared architect actual-call accounting",
      "Immutable blinded material and complete score validation",
      "Descriptive paired comparisons and crash-safe private registration"
    ],
    "real_evaluation_status": "BLOCKED_ACCESS_AND_MEASURED_ENGINEERING_HOURS",
    "source_digest": "72926f3b9597fd1487babd4ec80ebe1cd990960eeedf73d401e62615429cbd64",
    "local_pilot_tests": {
      "tests": 53,
      "failures": 0,
      "errors": 0,
      "skipped": 0
    },
    "local_whole_check_status": "FAIL_MISSING_PINNED_DEV_TOOLS",
    "local_failure_receipt": {
      "path": "evidence/development-supervisor/e78fdd10ee9d447a92be5596fe4fcf8e/STATE.json",
      "sha256": "cc3df7bc79ca64c87dc30ac1786033c2a653b14f5a8d9babfe514479e98cdb95"
    },
    "code_commit": "1609b614c42d954cae48f5cc863bcc58a5919de9",
    "native_run_id": 37827407312,
    "pilot_tests_per_target": 53,
    "whole_native_tests_per_target": 692,
    "review": {
      "path": "evidence/p06/offline-native-37827407312/REVIEW.json",
      "sha256": "cb794a8e63a943b4913fd2952af033aade917c5095eca2e70b113422833cf831"
    }
  },
  "p06_offline_publication": {
    "pr_number": 15,
    "pr_url": "https://github.com/mehrangtr/Consilium/pull/15",
    "status": "REVIEWED_AND_NATIVE_VERIFIED",
    "phase_accepted": false
  },
  "p06_live_work": {
    "status": "BLOCKED_BROWSER_APPROVAL_AND_RECORDED_BUDGET_GATES",
    "real_model_calls": 66,
    "real_final_outputs": 16,
    "required_final_outputs": 24,
    "selected_judge": "CLAUDE_BY_DIRECT_USER_CHOICE",
    "participants": [
      "CLAUDE",
      "QWEN"
    ],
    "external_origin_authenticated": false,
    "token_accounting": "UNKNOWN_OR_PARTIAL",
    "observed_cost": 0,
    "blocked_groups": [
      "PILOT-001/COUNCIL",
      "PILOT-001/REPEATED_SINGLE",
      "PILOT-005/COUNCIL",
      "PILOT-005/REPEATED_SINGLE"
    ],
    "phase_accepted": false,
    "private_response_records_persisted": true,
    "observed_elapsed_seconds": 3081.218,
    "unknown_submission_groups": [
      "PILOT-007/COUNCIL",
      "PILOT-015/COUNCIL"
    ],
    "counts_exclude_unresolved_submission_boundary": true,
    "snapshot_note": "Counts at this evidence checkpoint; two unresolved Qwen submissions are excluded from committed responses and retained. Logical STARTED for blocked Claude fill is not a provider invocation."
  },
  "p06_local_contract_check": {
    "status": "PRODUCT_TESTS_PASS_TOOLING_BLOCKED",
    "source_digest": "bbf23b0737d444deaa1013737263a77a755c5e9cf6e1c3be731ed475afdfcf0f",
    "supervisor_state": "evidence/development-supervisor/a3b10c522de943dc8860185d1561484d/STATE.json",
    "architect_tests": 264,
    "council_tests": 41,
    "pilot_tests": 53,
    "missing_tools": [
      "ruff",
      "mypy",
      "coverage"
    ],
    "native_verification_pending": false,
    "phase_accepted": false
  },
  "p06_manual_output_contract": {
    "status": "MERGED_AND_NATIVE_VERIFIED",
    "source_digest": "bbf23b0737d444deaa1013737263a77a755c5e9cf6e1c3be731ed475afdfcf0f",
    "code_commit": "e15601f9bd2985f5795649b836ad763261acd8ee",
    "merge_commit": "e567ee926794ca2547f7214942b9633b3c9b16d7",
    "pr_number": 16,
    "pr_url": "https://github.com/mehrangtr/Consilium/pull/16",
    "native_run_id": 37867476416,
    "tests_per_target": 698,
    "review": {
      "path": "evidence/p06/manual-output-native-37867476416/REVIEW.json",
      "sha256": "b68ee197122989a3e9ebdd024d7e90ee17d7862d758a0c6edb038833754a78e8"
    },
    "phase_accepted": false
  },
  "p06_browser_approval_blocks": {
    "status": "AUTOMATIC_REVIEW_REJECTED",
    "QWEN": {
      "call": "PILOT-015_COUNCIL_REVIEW_1",
      "submission_invoked_once": true,
      "blocked_action": "READ_CURRENT_EXISTING_TAB_COMPLETION",
      "reason": "Reviewer classified observation as opening the origin and risking an in-progress response. Code contained no navigation. No alternate observation surface or resend attempted."
    },
    "CLAUDE": {
      "call": "PILOT-020_REPEATED_SINGLE_REVIEW_0",
      "submission_invoked": false,
      "blocked_action": "FILL_PROMPT_BEFORE_ENTER",
      "reason": "Reviewer reported an uncaptured submitted review; fill failed before Enter. Last positive observation was a fresh /new page. No bypass attempted."
    },
    "recovery": "Resolve rejection; observe current existing pages and immutable private receipts before dependent action. Unknown is not non-delivery proof."
  },
  "p06_supervisor_deadline_correction": {
    "scope": "TEST_FIXTURE_ONLY",
    "production_idle_seconds": 300,
    "production_hard_seconds": 900,
    "fixture_idle_seconds": 3,
    "fixture_hard_seconds": 15,
    "reproduction_status": "FAIL_BEFORE_DEADLINE_CORRECTION",
    "reproduction_evidence": "evidence/p06/supervisor-deadline-history/reproduction-20261009/RUN.json",
    "original_failure_run": 37905506414,
    "native_verification": "PENDING",
    "local_control_check": {
      "path": "evidence/control-tests/RUN.json",
      "sha256": "3a8fd86bd542b59875174f54c1c053ebfc46d0a2a9f4fb324f0fc8a741906397",
      "status": "PASS",
      "tests": 118,
      "failures": 0,
      "skipped": 0,
      "source_digest": "009e61d15ce3bd85ab5afff6879b96b1ae87230f5dd9e6649b5fcb1cb063a06e"
    },
    "local_complete_check": {
      "path": "evidence/maintenance-check/RUN.json",
      "sha256": "56729d77c51e05af9250ea7039176ec83f8a78c59c4f87e56a6853d4f161634f",
      "status": "FAIL",
      "failed_checks": [
        "approved_quality_checks"
      ],
      "native_check_required": true
    }
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
| `P04` | `COMPLETED` | 0 |
| `P05` | `COMPLETED` | 0 |
| `P06` | `BLOCKED` | 4 |
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
