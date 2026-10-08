# Contributing

Read `AGENTS.md`, `PROGRESS.json`, and the protected governance projections first.
Keep all thirty user requirements, user decision gates, and original evidence.
Work on a branch and describe the trigger, resulting behavior, tests, and limits
in the pull request. Changes to protected user requirements need explicit user
approval; a researcher recommendation does not provide it.

Install the locked runtime and development dependencies and run the supervised
local checks described in README.md. Add meaningful negative cases for a changed
trust boundary. Do not mark mock runs as live verification or reuse historical
native evidence for changed source. Record separate author review honestly.

Keep credentials, browser profiles, private traces, and manual pilot workspaces
outside the checkout. Preserve raw source text; redact only diagnostic copies.
New large evidence should use content-addressed objects and small references.
Do not delete or rewrite historical accepted evidence.

The development lock pins direct tools; it is not a complete transitive hash lock.
Review dependency updates and rerun runtime environment checks before acceptance.
