# Security reporting

Do not put credentials, private browser traces, account details, or exploitable
security disclosures in public issues. The maintainer must configure and
publish a private reporting route before accepting sensitive submissions.
This repository does not currently claim that such a route is configured.

Public schemas reject credential fields and known secret values. Diagnostic
copies can redact credential fields, known secrets, and bearer tokens. These
checks do not detect every unknown secret and do not rewrite canonical answers.
Profiles and transport credentials remain outside source and shared artifacts.

GitHub Actions are pinned to full commits read from their official repositories.
Dependabot proposes updates, and a separate dependency advisory job is required
by the CI aggregate. Audit failures and network failures block that job; absence
of a known advisory is not a guarantee of security.
