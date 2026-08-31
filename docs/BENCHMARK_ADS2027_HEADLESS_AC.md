# ADS 2027 headless AC execution benchmark

This benchmark measures one user-visible outcome: create a disposable ADS 2027
workspace, run a minimal AC simulation without opening the GUI, read the
dataset, and return a finite number. It is a headless execution benchmark, not
a live-session or GUI-patch benchmark.

## Result

The 2026-09-01 run used `gpt-5.6-terra` at medium reasoning on one Linux ADS
host. Every row contains three serial, counterbalanced repetitions.

| Agent and product surface | Completed | Median wall time | Three-run range | Median total tokens |
| --- | ---: | ---: | ---: | ---: |
| Codex · Bridge a29 | 3/3 | 82.3 s | 66.6–101.5 s | 238,032 |
| Codex · Bridge a48 | 3/3 | 64.8 s | 62.7–78.7 s | 308,038 |
| Codex · official ADS MCP | 3/3 | **53.1 s** | 50.1–56.3 s | **221,590** |
| Pi Agent · Bridge a48 | 3/3 | 43.9 s | 40.9–52.8 s | 60,746 |
| Pi Agent · official ADS MCP | 3/3 | **37.7 s** | 36.2–38.2 s | **33,397** |

![ADS 2027 headless AC execution timing](assets/readme/ads2027-headless-ac-benchmark.svg)

For this exact task, the official MCP was faster than current Bridge a48 under
both Agents. Bridge a48 nevertheless improved the Codex median by 21.2% versus
the historical a29 package. Pi reduced Agent-side orchestration time for both
current product surfaces; that is an Agent comparison, not an ADS solver claim.

The new supervised live-session mechanism does not run in E3, so this result
does not measure live-patch latency or claim that live control is free. It does
show that adding the live/runtime mechanisms did not prevent the independent
headless route from completing, and that its current median did not regress
against a29 in the controlled Codex comparison.

## Product routes

- Bridge uses the packaged `quickstart` / `headless-minimal-ac` route.
- The official MCP uses `start_local_session` followed by `execute_python`.
- Pi Agent has no built-in MCP client. Its official-MCP arm used a thin
  transport extension that forwarded the official tool schemas, calls, and
  results without adding ADS knowledge.

## Acceptance and controls

Each successful run had to prove a new workspace below its assigned run
directory, automation mode, no PDE/GUI app, completed simulation, readable
dataset, finite numeric sample, and no cross-arm access. Direct shell use of
ADS Python or the simulator was forbidden.

Every run used a fresh Agent home with only authentication copied in. Global
rules, memories, sessions, auto-discovered Skills/extensions, web access,
external repositories, and previous outputs were excluded. Product indexes
were prepared before timing. There were zero isolation violations.

Identities: Bridge `0.1.0a29` and `0.1.0a48`; Codex CLI `0.145.0`; Pi Agent
`0.84.4`; official MCP executable SHA-256
`b68afcc4e904fae576a3c139898f877261fe9266a5235313ec46d48a2d0e4783`.

The public aggregate is
[`benchmarks/ads2027-v2-public-summary.json`](benchmarks/ads2027-v2-public-summary.json).
The earlier
[`v1 summary`](benchmarks/ads2027-headless-ac-v1-summary.json) remains frozen as
a historical result.

## Calibration disclosure

Calibration runs were excluded. They found and corrected three harness issues:
the official MCP child initially lacked the inherited ADS license variable;
Pi initially used an empty product HOME rather than the prepared read-only
index; and several validators recognized overly literal English phrases. All
formal outputs were revalidated with one arm-neutral validator. Initial errors
remain recorded whenever revalidation changed a result.
