# Experience-first ADS 2027 calibration

On 2026-09-01, the current Runtime E3 task was rerun on `eda-server` with ADS
2027, `eda-bridge-runtime` 0.1.0a39, the unreleased ADS Bridge candidate, Codex
and Pi Agent, `gpt-5.6-terra`, and medium reasoning. Each candidate used a fresh
run directory and the same E3 acceptance contract as the published
current-architecture comparison.

The first three candidates below are mechanism calibrations with one run per
Agent. After the experience stopped changing, the final candidate received
three fresh formal repetitions per Agent. The official-MCP arm was not rerun,
so comparisons with its frozen published median are cross-campaign context, not
a new simultaneous product comparison or a latency guarantee.

## Result

| Candidate | Agent | Status | Agent time | Tokens | Tool calls | Model-visible result payload | Docs calls | Native batches |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Experience-first ordering, incomplete mechanics | Codex | Pass | 159.894 s | 431,970 | 15 | 80,042 B | 4 | 4 |
| Experience-first ordering, incomplete mechanics | Pi | Fail | 199.591 s | 438,022 | 21 | 89,334 B | 9 | 5 |
| Added parameter, save, and simulator-return mechanics | Codex | Fail | 155.867 s | 326,890 | 12 | 38,884 B | 2 | 4 |
| Added parameter, save, and simulator-return mechanics | Pi | Pass | 100.202 s | 144,802 | 11 | 37,427 B | 1 | 2 |
| Completed exact workspace, import, timeout, and read mechanics | Codex | Pass | 73.143 s | 196,576 | 8 | 30,638 B | 0 | 1 |
| Completed exact workspace, import, timeout, and read mechanics | Pi | Pass | 66.204 s | 93,809 | 8 | 30,729 B | 0 | 1 |

## Formal candidate acceptance

| Agent | Passed | Times | Median time | Median tokens | Median calls | Median result payload | Docs calls across all runs |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| Codex | 3/3 | 62.673, 69.813, 135.421 s | 69.813 s | 183,452 | 8 | 30,578 B | 0 |
| Pi | 3/3 | 71.055, 71.154, 80.191 s | 71.154 s | 89,537 | 8 | 30,913 B | 0 |

The previous published Runtime E3 medians were 155.9 seconds for Codex and 92.3
seconds for Pi, with 4/6 passing. Against those frozen values, the candidate
formal medians are about 55% lower for Codex and 23% lower for Pi, and the
candidate passed 6/6. The frozen official-MCP medians remain 62.3 seconds and
50.6 seconds respectively; the candidate therefore does not establish that all
of the official-path latency difference has been removed.

The final candidate retained `workspace.create`, governed `native.batch`, source
separation, staging, promotion only after validation, and fresh-process dataset
readback. It did not remove an execution or safety gate.

## What the failures established

Changing only the retrieval order did not create a short path. Both Agents read
the applicable experience first, but the asset still omitted mechanics needed
to write a correct native program. The resulting logs established these exact
missing facts:

- assign scalar parameters through `.value`, not by replacing the parameter;
- call `save_design()`, not `save()`;
- import `ads` from `keysight.edatoolbox` instead of expecting an `ads`
  attribute on the parent module;
- do not index the possibly `None` return from `run_netlist()`;
- omit `instance="schematic"` from `workspace.create`; that field selects the
  ADS installation instance rather than a design view;
- use a distinct sibling output workspace and a wait no greater than 300000 ms;
- use the default read mode during fresh validation; `DesignMode.READ` is not an
  ADS 2027 member.

After those facts were recorded in the same experience asset, both Agents
stopped querying documentation and completed the accepted task through one
native batch.

The formal median path also used one native batch. One Codex repetition took
135.421 seconds after a continuation checksum error and an idempotency-key reuse
error caused three native-batch submissions before success. One Pi repetition
created the workspace twice after again interpreting `instance` as the
schematic view before reading the experience. These are residual Agent and
schema-clarity problems; neither run fell back to documentation.

## Boundary of the conclusion

Experience-first routing removes redundant discovery only when the applicable
asset contains enough verified mechanics to perform the task. It does not help
an uncovered task, eliminate Agent planning time, or remove the Bridge's staging
and validation cost. The formal candidate results are sufficient to retain the
experience-first change, but the published charts should not be replaced until
the release candidate is frozen and the comparison policy decides whether to
rerun the official arm or label the historical official median explicitly.
