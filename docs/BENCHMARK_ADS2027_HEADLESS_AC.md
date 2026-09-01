# ADS 2027 headless AC execution benchmark

This benchmark measures one user-visible outcome: through the assigned MCP
surface, create a disposable ADS 2027 workspace, build the same bounded AC
circuit, run exactly one simulation without launching the GUI, reopen the
dataset, and return one finite `R1_v` sample.

## Result

The corrected 2026-09-01 comparison uses the current architecture on both
sides: EDA Runtime MCP plus the current Runtime/ADS Skills versus the ADS 2027
official MCP. Each row contains three fresh, serial, counterbalanced runs with
`gpt-5.6-terra` at medium reasoning.

| Agent and product surface | Completed | Median Agent time | Three-run range | Median total tokens |
| --- | ---: | ---: | ---: | ---: |
| Codex · EDA Runtime | 1/3 | 155.9 s | 129.1–187.1 s | 425,712 |
| Codex · official ADS MCP | **3/3** | **62.3 s** | 56.4–63.3 s | 326,704 |
| Pi Agent · EDA Runtime | **3/3** | 92.3 s | 74.8–190.4 s | 194,135 |
| Pi Agent · official ADS MCP | **3/3** | **50.6 s** | 48.7–59.1 s | **49,722** |

![ADS 2027 headless AC execution timing](assets/readme/ads2027-headless-ac-benchmark.svg)

The official MCP was faster and more reliable for this exact execution task.
Both Runtime failures were Codex-generated program defects: one validation
return used JSON-style `false` in Python; one run first imported the wrong
module and then declared the wrong dataset artifact. Runtime itself returned
bounded failure evidence and did not promote an unvalidated result.

## Where the time went

Agent time and tool execution are different measurements:

| Successful-run tool layer | Median observed time |
| --- | ---: |
| Runtime `workspace.create` | 0.784 s |
| Runtime governed `native.batch` | 2.379 s |
| Official `start_local_session` | 0.783 s |
| Official `execute_python` | 0.814 s |

Runtime `native.batch` includes staging, one ADS program, a separate fresh
validation process, and promotion. The official call performs the task in one
local automation process, so these calls do not carry identical governance.
The roughly 1.6 s tool-layer difference is real; the much larger Agent-time
difference is mostly capability discovery, documentation/experience reading,
typed-plan construction, and retries. Across all six E3 runs, the median was
142.5 s and 387,553 tokens for Runtime versus 57.7 s and 146,143 tokens for the
official MCP.

## Controls and acceptance

- Runtime used `workspace.create` followed by governed `native.batch`; it did
  not use the legacy product CLI path.
- The official MCP used `start_local_session` and `execute_python`.
- Every accepted run proved a persisted workspace below its assigned directory,
  one simulation, fresh `AC1.AC` readback, a finite first `R1_v` magnitude, and
  no GUI launch or cross-arm access.
- Every run used a fresh Agent home. Shell, browser, web, previous outputs,
  direct ADS processes, and the other product surface were unavailable.
- Pi's official arm used a thin schema/call/result forwarding extension because
  Pi Agent has no built-in MCP client; it added no ADS knowledge.

The sanitized aggregate is
[`benchmarks/ads2027-v3-public-summary.json`](benchmarks/ads2027-v3-public-summary.json).
The v1/v2 files remain frozen as historical results, but v2 is superseded for
current-product comparison because its Bridge arm did not use Runtime MCP and
its K6 oracle was factually wrong.

## Calibration disclosure

Calibration found and fixed existing-product issues rather than adding a new
execution path: natural-language `Python` no longer silently narrows the local
documentation domain; multi-topic search preserves relevant cross-topic pages;
and the validated experience now records that the dataset filename follows the
schematic cell while `AC1.AC` is the varblock. Formal runs began only after
Codex and Pi independently completed the corrected E3 route.
