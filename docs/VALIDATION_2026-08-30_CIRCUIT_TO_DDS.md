# ADS 2026 Circuit-to-DDS Validation

## User outcome

A clean disposable workspace progressed through four independent typed gates on
ADS 2026 Update 2.1 for Linux with `DISPLAY=:4.0`:

1. create the workspace and empty schematic;
2. build a six-instance AC low-pass circuit in a non-overwriting candidate;
3. simulate it and read the numeric dataset into a CSV artifact;
4. create a native DDS equation and rectangular plot, then reopen the saved
   report before accepting it.

No customer project, arbitrary Python/AEL payload, GUI coordinate action, or
Momentum solve was used.

## Observed evidence

| Gate | Runtime state | Evidence | Client-visible time |
| --- | --- | --- | ---: |
| Workspace | passed | exact ADS instance and display; starter design returned as Context | 0.813 s |
| Circuit build | passed | 6 instances, 4 parameter assertions, 30 netlist lines, source hash preserved, fresh reopen | 0.859 s |
| Circuit simulation | passed | 31 rows; `freq`, `R1_v`, and `SRC1.i`; native dataset, netlist, and CSV; simulator time 1.037 s | 2.016 s |
| DDS report | passed | `output_db` equation valid; requested plot created; native report page confirmed after fresh reopen | 1.906 s |

The first DDS attempt exposed two real API-contract defects: the documented
`Rect` constructor is keyword-only at the Python layer, while its native
coordinates must be integers. The Bridge now validates integer coordinates
before execution and uses documented keyword arguments. The final fresh-reopen
run passed.

Runtime run identifiers for audit are `run_16356e0d8a684bbbbfc148bd73b93372`,
`run_32cde9a74c384de090ffc7746fa02fd4`,
`run_2744ae47e336430384985e8efb23797c`, and
`run_4d03a74b39ab4eafb797499b3db5354b`.

## One-plan composability acceptance

The follow-up release acceptance added an optional bounded `dataset_name` to
the simulation plan. The Bridge gives the simulator-selected native dataset
that predetermined filename only after the dataset exists, refuses overwrite,
and returns the accepted path as the dataset artifact. This keeps vendor output
normalization in the vendor Bridge instead of adding general scripting or
cross-step expression evaluation to Runtime.

One independent `eda.run_plan` call then completed all four stages without an
Agent round trip between simulation and DDS:

| Stage | Result | Client-visible Runtime time | Key acceptance |
| --- | --- | ---: | --- |
| Workspace | passed | 0.750 s | New disposable source and empty schematic |
| Circuit build | passed | 0.797 s | 6 instances, 14 assertions, source preserved, fresh reopen |
| Simulation | passed | 1.859 s | 31 finite rows; `accepted.ds`, netlist, and CSV |
| DDS report | passed | 1.032 s | Valid `output_db`, one plot, native DDS fresh reopen |
| Whole Runtime plan | passed | 4.469 s | Four ordered Runs, stopped-on-failure semantics, no GUI or raw code |

The four Run identities are `run_963c72a1950b4489af8ada051761df60`,
`run_b1fbd5262025471e8ed9ad856693cf72`,
`run_d41d47980d4e4ed49778f59d053305d2`, and
`run_523b98951cc04bb88a214f788ca42bf8`.

The first candidate attempt also proved failure isolation: a standalone-worker
import error stopped the plan at simulation before DDS creation. The preserved
source and already-verified candidate were reused after the packaging fix;
neither workspace was rebuilt from scratch.
