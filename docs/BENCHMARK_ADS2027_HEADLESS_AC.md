# ADS 2027 headless AC execution benchmark

This benchmark asks a narrow product question: when the same general-purpose
Agent must create, simulate, and read back a disposable ADS 2027 AC example,
how do the released Bridge and official ADS MCP execution surfaces behave?

It compares the natural execution route exposed by each product:

- **ADS Agent Bridge**: the public `ads-agent` headless example / quickstart
  route;
- **Official ADS MCP 0.7.0**: `start_local_session` followed by
  `execute_python`.

It is not a comparison of every Bridge or MCP capability. In particular, it
does not exercise the Bridge DE/DDS plug-in, GUI session management, dialog
handling, safe shutdown, or the broader official MCP documentation corpus.

## Result

The formal run on 2026-08-11 used one task repeated three times per arm: six
runs in total. Every run passed on its first attempt and produced an isolated
workspace, a completed simulation, a readable dataset, and a finite numeric
sample.

| Metric | ADS Agent Bridge | Official ADS MCP |
| --- | ---: | ---: |
| Strictly completed runs | **3/3 (100%)** | **3/3 (100%)** |
| First-pass completed runs | **3/3** | **3/3** |
| Total tokens, all runs | **585,993** | 1,034,887 |
| Uncached input tokens, all runs | **96,769** | 106,959 |
| Output tokens, all runs | **7,176** | 7,608 |
| Median wall time | **77.6 s** | 98.9 s |
| Mean wall time | **81.1 s** | 94.3 s |
| Isolation violations | 0 | 0 |

For this one task and environment, Bridge used 43.4% fewer Codex-reported
total tokens and had 21.5% lower median wall time. The total-token figure
includes cached input as reported by Codex. Looking only at uncached input,
Bridge used 9.5% fewer tokens; its output-token total was 5.7% lower.

The public machine-readable result is
[`benchmarks/ads2027-headless-ac-v1-summary.json`](benchmarks/ads2027-headless-ac-v1-summary.json).

## Task and acceptance gate

Each arm had to:

1. create a new workspace strictly below its assigned disposable run directory;
2. run a minimal ADS 2027 AC simulation without launching an ADS GUI;
3. read the resulting dataset and return a finite numeric sample;
4. prove `running_automation=true`, `is_pde_app=false`,
   `simulation_completed=true`, and `dataset_read_back=true`;
5. keep task artifacts inside the assigned run directory.

Claiming success without dataset readback, escaping the run directory, or using
the other arm's product surface was a hard failure.

## Controls

- Host: the same isolated Linux ADS server.
- ADS: ADS 2027, selected explicitly for both arms.
- Agent: Codex CLI 0.145.0, `gpt-5.6-terra`, medium reasoning.
- Runtime initialization: `DISPLAY=:4`; neither arm launched an ADS GUI.
- Same task contract, acceptance gate, host, model, ADS installation, and
  isolation policy; only the assigned product execution surface differed.
- Three serial repetitions with counterbalanced arm order.
- Every run used a fresh `CODEX_HOME`; global Agent configuration, skills,
  memories, rules, previous sessions, and shell startup files were masked.
- Web access, external repositories, prior run outputs, and cross-arm product
  access were excluded.
- Direct shell use of ADS Python or `hpeesofsim` was forbidden for both arms.
- Deterministic post-run validation checked the result schema, runtime context,
  workspace and dataset containment, numeric readback, telemetry, and arm
  isolation.

The benchmarked Bridge version was `ads-agent-bridge==0.1.0a29`; the official
server identified itself as `ads-mcp==0.7.0` and advertised the required
`start_local_session` and `execute_python` tools during preflight.

## Calibration disclosure

An initial official-arm calibration run exposed an incomplete Linux ADS
runtime library path: its local session started, but required ADS Python native
libraries were unavailable. That run was classified as harness calibration,
not as official-product failure. The shared ADS runtime environment was then
corrected, the official MCP was independently probed to confirm
`running_automation=true` and `is_pde_app=false`, and a clean pilot plus all six
formal runs were executed from new directories. No scored formal run used the
failed calibration state.

## Evidence and interpretation boundary

The full evidence bundle is retained privately because it includes host-local
paths, generated ADS workspaces, simulator artifacts, and complete Agent event
streams. The repository publishes the authored contract, versions, aggregate
metrics, per-run sanitized telemetry, and evidence booleans without those
payloads.

This is a **one-task execution microbenchmark**, not a universal speed or
quality ranking. Three repetitions can confirm repeatability for this gate but
cannot characterize all ADS workloads. The result supports the narrower claim
that the released Bridge headless path is both usable and efficient for this
minimal AC workflow under the named environment.
