# Operation classification audit

This audit applies the shared EDA capability model to the current ADS Bridge.
It records product role, not removal status. Existing accepted workflows remain
compatible while common mechanisms are extracted.

## Runtime-facing operations

| Operation | Class | Decision |
| --- | --- | --- |
| `docs.status/query/get` | Bridge infrastructure | Keep; this supplies version-matched knowledge evidence |
| `experience.list/get` | Bridge infrastructure | Keep as a read-only advisory gateway; missing assets degrade guidance, never execution |
| `workspace.create` | Bridge infrastructure | Keep; workspace identity and non-overwrite creation are lifecycle foundations |
| `session.launch/status/shutdown` | Bridge infrastructure | Keep; ownership, Context, and safe lifecycle are core |
| `native.execute` | Generic native execution | Primary official ADS Python extension path; governed scope, staging, timeout, fresh-process validation, promotion, and opaque content-bound continuation Context |
| `design.apply` | Compatibility shortcut | Keep callable for experience-referenced background recipes; do not present it as the default schematic route or add more schematic verbs |
| `circuit.simulate` | Provisional compiled shortcut | Keep compatible while its experience binding and same-task advantage remain evidenced; generalize only job, timeout, artifact, and dataset validation mechanics |
| `dds.create` | Provisional compiled shortcut | Keep v1/v2 compatible only as an experience-referenced macro; do not add one wrapper field per DDS widget or plot kind |
| `momentum.run_generated` | Provisional compiled shortcut | Keep as an optional experience-referenced solver macro with retained process and artifact evidence; it is not the Bridge core or blank-layout EM coverage |

## Embedded add-on commands

| Command family | Class | Decision |
| --- | --- | --- |
| `ping`, `status`, `capabilities`, `runtime_snapshot` | Bridge infrastructure | Keep |
| `context_*` | Bridge infrastructure | Keep; selection and freshness belong to Context |
| `dialog_snapshot/action` | Bridge infrastructure / bounded GUI fallback | Keep under fingerprint and approval gates |
| `open_workspace`, `safe_shutdown` | Bridge infrastructure | Keep under ownership and identity checks |
| `eval`, `exec`, `ael_call` | Generic native execution precursor | Removed; `native.execute` is the sole official-code entry point |
| `dds_readback`, `ael_workspace_path` | Acceptance probe | Keep for compatibility and tests, but stop presenting them as the measure of product capability |

## Coverage status after the audit

- **Knowledge coverage:** maintained, version-scoped ADS documentation retrieval.
- **Official API reach:** Python DE/DDS/dataset/emtools plus AEL interoperability
  exist, but their public governance is uneven.
- **Generic execution coverage:** governed official ADS Python now supports
  observe and staged mutation with source fingerprint, total timeout,
  fresh-process validation, artifacts, and non-overwriting promotion. AEL and a
  hostile-code sandbox are not claimed.
- **Default supported coverage:** infrastructure plus the maintained certified
  workflows above.
- **Validated workflow coverage:** limited to the exact retained ADS acceptance
  journeys; it does not cap official API reach.
