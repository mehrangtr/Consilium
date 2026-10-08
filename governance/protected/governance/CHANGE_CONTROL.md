# Consilium Change Control Policy

## 1. Priority order

1. **Explicit user-origin requirements (`UR-*`)**
2. Safety / security constraints that are truly mandatory
3. Approved architecture decisions (ADRs)
4. AI/researcher recommendations (`AR-*`)
5. Implementation convenience

An item lower in this list cannot silently override an item above it.

## 2. Protected requirement rule

Any `UR-*` with `priority: MUST` is locked. A proposed change that removes, postpones, weakens, inverts, or substitutes that behavior requires:

- an ADR;
- the affected `UR-*` IDs;
- the proposed delta;
- the technical reason;
- alternatives considered;
- impact on UX, reliability, security, data, and compatibility;
- migration/backward-compatibility implications;
- explicit user approval.

Until approval exists, the canonical architecture remains unchanged.

## 3. Compatible implementation changes

The following do **not** require changing the requirement if behavior is preserved:

- replacing internal persistence mechanics;
- refactoring modules;
- changing schemas with migration;
- adding tests/telemetry;
- adding optional features;
- making a feature more reliable.

Example: changing Markdown from canonical state to a **derived, regenerable artifact** is compatible because Markdown remains available to the user.

## 4. Incompatible examples

These changes are blocked without explicit user approval:

- moving Browser support from V1 to V2;
- replacing Browser V1 with Manual-only operation;
- automatically selecting the final Judge;
- starting a normal next round without the user decision gate;
- creating a new provider thread on every round while a valid conversation exists;
- deleting per-model cumulative histories;
- removing Markdown/JSON because SQLite exists;
- silently rotating accounts, conversations, models, or judges.

## 5. Required decision record

Use `ADR_USER_REQUIREMENT_CHANGE_TEMPLATE.md`.

A change is not approved merely because:
- several models agree;
- a benchmark favors another design;
- implementation becomes easier;
- a researcher labels the alternative 'best practice'.

Those are evidence inputs, not authorization.

## 6. Executable governance scope in v1.3

The original `UR-001..UR-030` identities and original requirement text remain protected. Audit labels such as `UR-R01` are aliases/aggregations and MUST NOT create new USER-origin requirements. New technical obligations derived from an existing requirement are linked as contract details or conformance invariants.

Protection, contract coverage, application implementation and runtime verification are separate fields. Historical assessments are retained as unverified historical context. A passing document checker MUST NOT be reported as a passing application requirement.

`CONTRACT_ADDENDUM_USER_GUARD_v1.3.md`, `TRACEABILITY_MATRIX.md` and the conformance report are generated views. CI checks their exact correspondence to canonical records, not just a `normative_level` metadata value. The archive's original requirement baseline is preserved as a read-only provenance fixture.

The manifest verifies the inventory and file contents of the current revision. A new legitimate revision changes its manifest; historical version differences are not automatically source drift. Without a supplied Git checkout the source commit remains null. On integration, package from an actual reviewed commit and record that observed SHA.

This archive intentionally refuses runtime `PASS` declarations. When the application repository becomes available, integrate concrete module ownership, collected test IDs, current-commit CI runs and artifacts before claiming runtime conformance. That integration must not weaken any protected requirement. Required branch checks must be configured in the hosting service; merely adding a workflow file is not that configuration.
