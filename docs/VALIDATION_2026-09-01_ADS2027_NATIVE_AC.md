# ADS 2027 governed native AC validation

On 2026-09-01, the existing `native.batch` staged-mutation path was exercised on
`eda-server` with ADS 2027 and no GUI session. The source was a fresh workspace
created by `workspace.create`; the batch opened its existing schematic in
`DesignMode.WRITE`, built the maintained V_AC/R/C/AC example, generated one
netlist, ran `CircuitSimulator.run_netlist` once, and read `AC1.AC` through
`keysight.ads.dataset`.

The persisted dataset was `ac_minimal.ds`, named after the schematic cell
`ac_minimal`. `AC1.AC` was the varblock inside that file; `AC1.ds` was not the
validated filename. Future experience guidance must preserve this distinction.

The successful external-automation opening sequence was
`api.de.open_workspace(context["workspace"])` followed by
`api.db.open_design(top_design, api.de.db.DesignMode.WRITE)`. The class-style
`de.Workspace.open(path)` form is not equivalent for this use.

The batch passed fresh-process validation, preserved the source fingerprint,
promoted a distinct output workspace and dataset artifact, and returned the
finite first-sample magnitude `0.9998223944475859`. The direct end-to-end adapter
call completed in about 3.3 seconds. This is calibration evidence for the ADS
2027 native workflow, not a Codex/Pi or Runtime/official benchmark result.
