# ADS 2027 knowledge regression benchmark

This benchmark asks a practical release question: when a general-purpose Agent
must reason about ADS 2027 from the knowledge source it is given, does it reach
a usable, evidence-bounded answer without inventing an API?

It compares two knowledge routes:

- **ADS Agent Bridge**: the packaged `ads-kb-docs` Skill and its version-bound
  `ads-agent docs query/get` interface;
- **Official ADS MCP**: the ADS 2027 MCP executable and its bundled corpus.

The benchmark does not compare the full product surfaces. It deliberately
holds the Agent, host, prompts, and output contract constant so that the
knowledge route is the main changed variable.

## Result

Run on 2026-08-11, the suite contained three tasks repeated three times per
arm: 18 runs in total.

| Metric | ADS Agent Bridge | Official ADS MCP |
| --- | ---: | ---: |
| Strictly completed runs | **9/9 (100%)** | 6/9 (66.7%) |
| First-pass completed runs | **9/9** | 6/9 |
| Total tokens, all runs | **1,000,338** | 1,116,503 |
| Median tokens per run | 147,056 | **133,453** |
| Median wall time | 66.8 s | **63.5 s** |
| Mean wall time | 77.2 s | **60.2 s** |
| Isolation violations | 0 | 0 |

Across these nine matched tasks, Bridge used 10.4% fewer total tokens and
closed three more runs. It was not faster overall: median wall time was 5.2%
higher, and mean wall time was 28.2% higher because one geometry run took
183.7 seconds.

The public machine-readable result is
[`benchmarks/ads2027-knowledge-v1-summary.json`](benchmarks/ads2027-knowledge-v1-summary.json).

## Tasks

| ID | Question tested | Strict success condition |
| --- | --- | --- |
| K1 | Choose the supported ADS execution route for a constrained task. | Select the documented route and state its boundary without unsupported API claims. |
| K3 | Write ADS 2027 Python for layout rectangle, polygon, and path creation. | Use documented geometry and layer APIs with the required receiver and constructor signatures. |
| K6 | Determine whether Python can execute layout DRC and provide a safe route. | Do not invent a runnable Python DRC API; report the verified boundary, next verification step, and bounded fallback. |

K1 and K3 were completed by both arms in all repetitions. On K6, all three
official-MCP runs emitted the unverified `create_drc_job` route and failed the
strict boundary checks. All three Bridge runs stopped at the documented
boundary and supplied a verification/fallback path instead of presenting
unverified code as runnable.

## Controls

- ADS version: ADS 2027.
- Agent: Codex CLI 0.145.0, `gpt-5.6-terra`, medium reasoning.
- Same remote host and prompts for both arms.
- Three serial, counterbalanced repetitions per task and arm.
- Every run used a new ephemeral `CODEX_HOME`.
- User configuration, rules, skills, memories, and shell startup files were
  masked inside the run sandbox.
- The official arm could use only the official MCP. The Bridge arm could use
  only the packaged Docs Skill and selected Bridge CLI.
- Web access, external repositories, and earlier run outputs were excluded.
- Telemetry and isolation checks completed for all 18 runs.

The benchmarked Bridge wheel was `ads-agent-bridge==0.1.0a29`, SHA-256
`5064f70cdb21de57b10a73cd305f4e48467513be700980fd770d3d558bc0fc40`.
The official MCP executable SHA-256 was
`b68afcc4e904fae576a3c139898f877261fe9266a5235313ec46d48a2d0e4783`.

## Validation and evidence policy

Each answer was checked against an authored task contract. A post-run validator
audit expanded only arm-neutral language aliases (for example, equivalent ways
to say that a capability was not established) and documented valid ADS
signatures. It did not add an exception for either product. The final validator
was then applied to all 18 outputs.

The complete run bundle is retained privately because it contains local paths
and vendor documentation returned by the official MCP. This repository
publishes the task definitions, protocol, hashes, aggregate metrics, and a
sanitized row for every run, but does not redistribute Keysight documentation.

## Interpretation boundary

This is a small **engineering regression benchmark**, not a blind held-out
evaluation. Earlier pilot failures on these tasks informed Bridge improvements,
so the result proves that the current release closes these known failure modes;
it does not establish universal superiority over the official MCP. Token and
latency measurements are specific to the named model, runtime, host, and
prompts. Future releases should add held-out tasks and more repetitions before
making a broader claim.
