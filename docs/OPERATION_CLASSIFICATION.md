# Operation classification audit

This audit applies the shared EDA capability model to the current ADS Bridge.
It records product role, not removal status. Existing accepted workflows remain
compatible while common mechanisms are extracted.

## Runtime-facing operations

| Operation | Class | Decision |
| --- | --- | --- |
| `docs.status/query/get` | Bridge infrastructure | Keep; this supplies version-matched knowledge evidence |
| `workspace.create` | Bridge infrastructure | Keep; workspace identity and non-overwrite creation are lifecycle foundations |
| `session.launch/status/shutdown` | Bridge infrastructure | Keep; ownership, Context, and safe lifecycle are core |
| `design.apply` | Certified workflow | Keep compatible; extract copy/stage/fingerprint/idempotency/assertion/promotion mechanics instead of adding more schematic verbs |
| `circuit.simulate` | Certified workflow | Keep as an accepted circuit-to-data recipe; generalize job, timeout, artifact, and dataset validation mechanics |
| `dds.create` | Certified workflow | Keep v1/v2 compatible; do not add one wrapper field per DDS widget or plot kind |
| `momentum.run_generated` | Certified workflow | Keep as an optional generated-input solver recipe; it is not the Bridge core or blank-layout EM coverage |

## Embedded add-on commands

| Command family | Class | Decision |
| --- | --- | --- |
| `ping`, `status`, `capabilities`, `runtime_snapshot` | Bridge infrastructure | Keep |
| `context_*` | Bridge infrastructure | Keep; selection and freshness belong to Context |
| `dialog_snapshot/action` | Bridge infrastructure / bounded GUI fallback | Keep under fingerprint and approval gates |
| `open_workspace`, `safe_shutdown` | Bridge infrastructure | Keep under ownership and identity checks |
| `eval`, `exec`, `ael_call` | Generic native execution precursor | Replace the current safe-vs-unsafe binary with a governed official-code lane; retain explicit unrestricted unsafe compatibility separately |
| `dds_readback`, `ael_workspace_path` | Acceptance probe | Keep for compatibility and tests, but stop presenting them as the measure of product capability |

## Coverage status after the audit

- **Knowledge coverage:** maintained, version-scoped ADS documentation retrieval.
- **Official API reach:** Python DE/DDS/dataset/emtools plus AEL interoperability
  exist, but their public governance is uneven.
- **Generic execution coverage:** not yet complete; arbitrary official code is
  currently either unavailable through Runtime or classified wholly unsafe.
- **Default supported coverage:** infrastructure plus the maintained certified
  workflows above.
- **Validated workflow coverage:** limited to the exact retained ADS acceptance
  journeys; it does not cap official API reach.
