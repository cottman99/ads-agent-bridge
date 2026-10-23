---
name: ads-agent-bridge
description: Operate an exact Keysight ADS DE or DDS session through official Python using EDA Runtime; use for live control, isolated workspaces, simulation, setup and diagnosis.
---

# ADS Agent Bridge

Use Runtime as the Agent execution path. The CLI supplies setup, administration
and direct diagnostics. Every operation carries a concise purpose.
Use `$ads-kb-docs` for documentation-only questions without launching ADS.

Preserve the exact ADS installation/version, workspace, and slot + profile. DE and DDS
are distinct runtimes. Launching a DE workspace neither launches nor proves a DDS runtime.
The word `dataset` alone never selects DDS.
Use `ads.python.de` for design and simulation API work and `ads.python.dds` for Data Display.
Both support `live` and `background` where the selected installation exposes the SDK.

`native.execute` accepts `eda.native-program/v1`. `mode` and `effect` are independent.
Always use `eda.submit` with a stable idempotency key, including observe programs.
There is no module allowlist or global unsafe toggle. Use official Python directly;
documented AEL calls can be made through `api.ael` in the same program.

| Mode | Target and verification |
| --- | --- |
| live | Exact captured DE/DDS Context; run on the application thread; validate in that session |
| background | Exact installation and source workspace; copy, execute and validate in fresh owned processes; promote to a distinct output |

The program defines `run(api, context)` and returns a JSON object. `api` exposes
`de`, `db` for DE, `dds` for DDS, and `ael`. Normal imports can reach other installed
official modules. `context` supplies workspace and declared selectors.
Mutations declare validation with `validate(api, context)` returning `status: passed`.
Live writes name the captured workspace and use transaction strategy `none`.
Background writes use `adapter_staging`, complete source fingerprints,
`fresh_reopen: true` and `promotion: on_validation`. Outputs must not already exist.

For a new workspace use `workspace.create`, then the returned `continuation_ref`
for background execution. GUI work uses the captured live Context. When a contract
is unknown, query capabilities for that operation only; the wrapper list does not
limit the official API. Matching experience is optional advice, and selected compiled
workflows use the same Runtime admission and evidence path.

Use `docs.query` and `docs.get` through `eda.read` for exact official symbols and
signatures. Docs prepare automatically; incomplete enrichment does not disable
execution. Domains are `ads`, `ael`, `python`, `dds`; omit filters for broad searches.
Only use source references actually returned by retrieval. `docs.symbol` reads
installed `.py`/`.pyi` signatures and docstrings without importing modules or
evaluating getters. Dynamic inspection uses a submitted native observation.

For setup, launch, dialogs and ownership see
[administration-and-live-sessions.md](references/administration-and-live-sessions.md).
For a complete background plan see
[background-native-workflows.md](references/background-native-workflows.md).

After timeout or disconnect, inspect the job/receipt instead of repeating a write.
An uncertain target needs fresh native observation before reconciliation. A live
validation failure does not promise rollback. Close only this task's owned session.
Keep proprietary manuals and project data outside public repositories.
