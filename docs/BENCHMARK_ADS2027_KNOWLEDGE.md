# ADS 2027 knowledge reliability benchmark

This benchmark asks whether an Agent reaches a usable ADS 2027 answer from its
assigned current product surface. K1 checks the complete no-GUI route, K3 checks
version-matched layout geometry signatures, and K6 checks the documented Python
layout-DRC flow.

## Result

Each cell is the audited strict pass count from three fresh repetitions on
2026-09-01.

| Agent and product surface | K1 route | K3 geometry | K6 Python DRC | Total |
| --- | ---: | ---: | ---: | ---: |
| Codex · EDA Runtime | 3/3 | 3/3 | 3/3 | **9/9** |
| Codex · official ADS MCP | 2/3 | 2/3 | 3/3 | 7/9 |
| Pi Agent · EDA Runtime | 3/3 | 3/3 | 3/3 | **9/9** |
| Pi Agent · official ADS MCP | 1/3 | 1/3 | 3/3 | 5/9 |

![ADS 2027 knowledge reliability by case](assets/readme/ads2027-knowledge-benchmark.svg)

Runtime completed all 18/18 knowledge runs; the official MCP completed 12/18.
The result is still case-specific:

- K6 is now 12/12 across both products and Agents. ADS 2027 does document
  Python DRC automation, through the experimental DVE API and an AEL-call flow.
  The earlier v2 benchmark's negative oracle was wrong.
- Runtime returned valid K3 code in 6/6. One answer used the documented
  `db_uu.Rect`, `Polygon`, and `Path` constructors; the audit corrected the
  original validator, which only recognized `Design.add_*` spelling.
- Three official K3 answers used `create_rect/create_polygon/create_path`, which
  are not the ADS 2027 interfaces returned by the version-matched reference.
- Three official K1 answers did not identify the complete
  `start_local_session` plus `execute_python` route, even when the surrounding
  headless plan was plausible.

## Timing

| Product surface | Knowledge passes | Median Agent time | Median total tokens |
| --- | ---: | ---: | ---: |
| EDA Runtime MCP + Skills | **18/18** | 43.2 s | 117,730 |
| Official ADS MCP | 12/18 | **32.6 s** | **69,043** |

Runtime was more reliable here, while the official MCP was materially lighter
and faster. Faster failed answers remain failures; knowledge latency is not ADS
solver latency.

## Controls and audit

The model, reasoning effort, ADS host, prompts, serial counterbalancing, output
schemas, and three repetitions were held constant. Every run had a fresh Agent
home and only its assigned MCP product surface. The audit preserved the raw
formal results, then corrected four validator false negatives: three K1 answers
used the explicit `.ds` artifact name instead of the word “dataset”, and one K3
answer used documented constructor receivers.

The sanitized aggregate and exact identities are in
[`benchmarks/ads2027-v3-public-summary.json`](benchmarks/ads2027-v3-public-summary.json).
Older v1/v2 summaries remain historical evidence and are not the current
architecture comparison.
