# Consilium

A local AI council that keeps the user in charge of the question, continuation,
and final judge. It preserves independent answers, peer criticism, dissent,
uncertainty, and an auditable history.

The current implementation is an offline kernel using SQLite and a mock
transport, with a first-class manual input pipeline. Real API and browser
integrations for ChatGPT, Claude, Gemini, DeepSeek, and Qwen remain required
for V1 and are scheduled in P08–P11. Manual input does not replace browser support.

## Try the offline demonstration

Use Python 3.12 in a virtual environment:

```sh
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps --no-build-isolation
python -m consilium demo --scripted
```

`--scripted` explicitly selects synthetic, prewritten demonstration decisions.
For interactive decisions, run `python -m consilium demo` in a terminal.
The demo makes zero live or paid calls. It prints its output directory,
exports versioned Markdown and JSON, preserves objections, and checks that
reopening the database reproduces the final state. `--output NEW_DIRECTORY`
chooses a destination and refuses an existing directory.

## Architecture and reliability

Pure contracts and analyzers live in `src/consilium/core`. SQLite persistence
and orchestration live in `src/consilium/shell`; transport contracts are in
`src/consilium/ports`. Council SQL is encapsulated by `SQLiteCouncilRepository`.
The operation ledger records intent before dispatch. `UNKNOWN_DELIVERY`
requires verification rather than a blind resend. Model text cannot authorize
a round, select a judge, or grant a transfer. Consensus is not a truth probability.

Tests include genuine subprocess termination, migration rollback, stale
revision rejection, exact replay, and bounded generated event sequences.
New review inputs have persisted, balanced aliases and a versioned rubric.
Optional critique spans bind to exact UTF-8 answer bytes and quote hashes.

## Current state and evidence

Historical P00–P05 acceptance is preserved. Approved quality improvements are
on a local development branch; fresh Windows verification and publication
remain pending. P06 has an eight-task preregistered pilot and manual recording
tools. Real pilot outputs have not yet been collected. Mock test success does
not establish model quality, live provider capability, or full V1 conformance.

`CONFORMANCE_MAP.yaml` traces all thirty protected requirements across
protection, contract, implementation, and final verification. Its JSON syntax
is valid YAML. Run `python tools/check_conformance.py` to verify references and
generate `evidence/conformance/DASHBOARD.md`. The immutable baseline package
remains the authority; direct protected projections are byte-checked.

## Development checks

```sh
python -m pip install -r requirements.lock -r requirements-dev.lock
python tools/qualityctl.py navigation
python tools/development_supervisor.py local
```

The five-minute supervisor watches completed work, not heartbeat output. Checks
have bounded timeouts and measured durations. Strict type checking and coverage
are currently scoped to three new reliability modules, not the whole product.
Native Windows and Linux reports must match the actual source digest. Security
advisory checks require network access; a timeout remains unverified.

See [Persian guide](README_FA.md), [contribution guide](CONTRIBUTING.md),
[security reporting](SECURITY.md), and [licensing status](LICENSING.md).
