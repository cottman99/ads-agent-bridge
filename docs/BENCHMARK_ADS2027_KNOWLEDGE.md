# ADS 2027 knowledge reliability benchmark

This benchmark asks whether an Agent reaches a usable ADS 2027 answer from its
assigned knowledge surface without inventing capability. Three tasks isolate
route selection (K1), layout geometry signatures (K3), and the Python layout
DRC boundary (K6).

## Result

Each cell is the strict pass count from three serial repetitions on 2026-09-01.

| Agent and product surface | K1 route | K3 geometry | K6 DRC boundary | Total |
| --- | ---: | ---: | ---: | ---: |
| Codex · Bridge a29 | 3/3 | 2/3 | 3/3 | 8/9 |
| Codex · Bridge a48 | 3/3 | 2/3 | 3/3 | 8/9 |
| Codex · official ADS MCP | 3/3 | 3/3 | 0/3 | 6/9 |
| Pi Agent · Bridge a48 | 0/3 | 3/3 | 3/3 | 6/9 |
| Pi Agent · official ADS MCP | 3/3 | 3/3 | 0/3 | 6/9 |

![ADS 2027 knowledge reliability by case](assets/readme/ads2027-knowledge-benchmark.svg)

The result is not a one-number ranking:

- Bridge a48 rejected the unverified Python DRC route in all 6/6 current
  Codex/Pi runs. The official MCP presented `create_drc_job` as established in
  all 6/6 K6 runs and therefore passed 0/6.
- The official surface completed K1 in 6/6 current runs. Pi + Bridge selected
  the correct quickstart route but omitted the required dataset/finite-readback
  statement in all three repetitions, so those answers failed strictly.
- Both current surfaces were strong on K3 under Pi. Under Codex, Bridge a48 had
  one run that stopped without the requested geometry example.

## Timing

| Agent and product surface | Knowledge passes | Median wall time | Median total tokens |
| --- | ---: | ---: | ---: |
| Codex · Bridge a29 | 8/9 | 46.0 s | 124,680 |
| Codex · Bridge a48 | 8/9 | 43.2 s | **102,878** |
| Codex · official ADS MCP | 6/9 | **41.6 s** | 155,654 |
| Pi Agent · Bridge a48 | 6/9 | 28.8 s | 24,559 |
| Pi Agent · official ADS MCP | 6/9 | **26.8 s** | **15,188** |

Faster failed answers remain failures; latency is reported separately from
reliability. Pi used substantially less Agent context on both product surfaces,
but its shorter Bridge K1 answers omitted one required boundary detail.

## Controls

The model (`gpt-5.6-terra`), reasoning level (medium), ADS host, prompts,
three-run serial counterbalancing, output contracts, and deterministic
post-run validator were held constant. Every run used a fresh Agent home and
could access only its assigned product surface. Web, prior outputs, global
rules/memories, and cross-arm access were excluded; isolation violations were
zero.

Bridge arms used their packaged Skills and version-bound local docs index. The
official arms used the unchanged ADS 2027 MCP executable. Pi reached it through
a thin schema/call/result forwarding extension because Pi Agent does not ship a
built-in MCP client; the adapter supplied no ADS domain knowledge.

The public aggregate and identities are in
[`benchmarks/ads2027-v2-public-summary.json`](benchmarks/ads2027-v2-public-summary.json).
The previous
[`v1 summary`](benchmarks/ads2027-knowledge-v1-summary.json) remains available
as a frozen historical baseline.
