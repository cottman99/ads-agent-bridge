---
schema_version: "eda.experience-asset/v1"
asset_version: "1.0.0"
id: "ads.native.circuit-simulate-and-validate"
kind: "workflow"
status: "validated"
summary: "Build, simulate, and freshly validate an ADS 2027 circuit through one governed native program."
intents: ["simulate an ADS circuit", "produce an accepted ADS dataset"]
tags: ["ADS", "ADS 2027", "native program", "circuit simulation", "dataset"]
applies_to: {"eda":"keysight-ads","versions":["2027"],"profiles":["de"],"os":["linux"],"capabilities":["native.execute"]}
prerequisites: ["workspace.create continuation", "ADS 2027 native.execute capability", "license availability"]
recommendation: "Reuse these validated ADS 2027 mechanics directly; query official documentation only for a version, operation, or required behavior not established here."
steps: ["pass the opaque workspace continuation", "open the staged workspace", "open an existing schematic in DesignMode.WRITE", "build and save the circuit", "generate one netlist", "run CircuitSimulator once", "read and freshly validate the dataset", "promote the validated output"]
failure_signals: ["relative write path", "library not open", "read-only design", "simulation timeout", "missing or invalid dataset"]
validation: {"method":"real ADS 2027 native.execute simulation and fresh dataset readback","evidence":"docs/VALIDATION_2026-09-01_ADS2027_NATIVE_AC.md"}
official_refs: ["ads-docs://2027/simulation/python"]
evidence_refs: ["docs/VALIDATION_2026-09-01_ADS2027_NATIVE_AC.md"]
confidence: 0.95
last_verified: "2026-09-01"
supersedes: []
---

# Validated native mechanics

For a workspace returned by Runtime `workspace.create`, pass its opaque
`continuation_context` to the first `native.execute`. Declare one absolute sibling
output workspace; never reuse the source workspace returned by
`workspace.create` as that output. When the dataset is a retained artifact, also
declare one absolute artifact directory, list the dataset filename in
`scope.artifacts`, and write/read it below `context["artifact_root"]`.

For this greenfield route, the `workspace.create` payload needs only the
absolute `workspace`, `library`, and `cell`. Do not set its optional `instance`
field to `"schematic"`; that field selects an ADS installation instance, not a
design view. Use a wait timeout no greater than `300000` milliseconds.

Pass the short continuation inside the vendor payload, never beside it in the
Runtime tool call. This compact envelope shows every required plan section;
replace placeholders with task values and the programs described below:

```json
{
  "payload": {
    "continuation_context": "<workspace.create continuation_ref>",
    "plan": {
      "schema_version": "eda.native-program/v1",
      "mode": "background",
      "runtime": "ads.python.de",
      "effect": "mutate",
      "program": {"language": "python", "source": "def run(api, context): ..."},
      "scope": {
        "resource_kind": "ads-workspace",
        "selectors": {},
        "read_paths": [],
        "write_paths": ["<distinct output workspace>", "<artifact directory>"],
        "artifacts": ["<cell_name>.ds"]
      },
      "transaction": {
        "strategy": "adapter_staging",
        "source_fingerprints": {},
        "fresh_reopen": true,
        "promotion": "on_validation"
      },
      "validation": {
        "program": {"language": "python", "source": "def validate(api, context): ..."},
        "required_artifacts": ["<cell_name>.ds"]
      },
      "limits": {"timeout_seconds": 300, "max_output_bytes": 1048576}
    }
  }
}
```

The continuation materializes the bound source read path and fingerprint, so
the empty `read_paths` and `source_fingerprints` placeholders above are valid
only when that continuation is present in `payload`. Both write paths must be
new, absolute, and distinct from the source.

In external ADS automation, open the staged workspace before opening its design.
An existing schematic intended for mutation must be opened with
`api.de.db.DesignMode.WRITE`; the default `open_design` mode is not a writable
mutation contract. For the empty schematic returned by `workspace.create`, the
validated opening pattern is:

```python
api.de.open_workspace(context["workspace"])
design = api.db.open_design(returned_top_design, api.de.db.DesignMode.WRITE)
```

Here `returned_top_design` means the literal `bridge.top_design` string returned
by `workspace.create` (for example `my_lib:my_cell:schematic`). It is not a
`context` key: `context["top_design"]` is invalid. Compile that returned string
into the program source while constructing the typed plan.

Do not call `de.Workspace.open(path)`, and do not clear the already-empty design.
The validated component identifiers for the maintained AC example are
`("ads_sources", "V_AC", "symbol")`, `("ads_rflib", "R", "symbol")`,
`("ads_rflib", "C", "symbol")`, `("ads_rflib", "GROUND", "symbol")`, and
`("ads_simulation", "AC", "symbol")`. Their relevant parameter keys are `R`,
`C`, `Start`, `Stop`, `Dec`, and `Step`.

For this maintained example, preserve the validated placement and connection
pattern instead of inventing alternate pin coordinates or label APIs:

```python
design.add_instance(("ads_sources", "V_AC", "symbol"), (-2, 0), name="SRC1", angle=-90)
r1 = design.add_instance(("ads_rflib", "R", "symbol"), (0, 0), name="R1", angle=0)
c1 = design.add_instance(("ads_rflib", "C", "symbol"), (2, 0), name="C1", angle=-90)
design.add_instance(("ads_rflib", "GROUND", "symbol"), (-2, -1), name="G1", angle=-90)
design.add_instance(("ads_rflib", "GROUND", "symbol"), (2, -1), name="G2", angle=-90)
design.add_wire([(-2.0, 0.0), (0.0, 0.0)])
wire = design.add_wire([(1.0, 0.0), (2.0, 0.0)])
wire.add_wire_label("R1_v")
ac1 = design.add_instance(("ads_simulation", "AC", "symbol"), (-4, 1), name="AC1", angle=0)
```

Set each documented parameter through its scalar parameter object's `value`,
then call `save_design()` before generating the netlist. Assigning a string to a
parameter entry or assigning a complete `parameters` mapping is invalid. The
validated maintained example uses:

```python
r1.parameters["R"].value = "3.0 kOhm"
c1.parameters["C"].value = "1.0 uF"
ac1.parameters["Start"].value = "1 Hz"
ac1.parameters["Stop"].value = "1 MHz"
ac1.parameters["Dec"].value = "5"
ac1.parameters["Step"].value = ""
design.save_design()
netlist = design.generate_netlist()
```

Do not call `design.save()`. In particular, `R1_v` was validated through
`wire.add_wire_label`; a different net-label API or coordinate pattern is not
evidence-equivalent.

Generate the netlist from the design, run exactly one
`keysight.edatoolbox.ads.CircuitSimulator.run_netlist`, and validate the
persisted dataset in the separate validation program. A successful
`run_netlist()` may return `None`; do not index or otherwise interpret its
return value as simulation evidence. The generated dataset plus the separate
fresh validation are the evidence. The validation return must contain
`{"status": "passed"}`. Do not use native observe calls to rediscover these
validated mechanics.

Import the simulator submodule exactly; importing the parent and then accessing
an `ads` attribute is not equivalent:

```python
from keysight.edatoolbox import ads

simulator = ads.CircuitSimulator()
simulator.run_netlist(netlist, context["artifact_root"])
```

Use string concatenation below the pre-created artifact root; `os` and `open`
are intentionally outside this governed program policy. By default,
`CircuitSimulator.run_netlist` names the dataset after the schematic cell, not
after the simulation-controller instance. In the validated example the cell is
`ac_minimal`, so the file is `ac_minimal.ds`; `AC1.AC` is the varblock inside
that dataset. The validated dataset readback is:

```python
import keysight.ads.dataset as dataset

path = context["artifact_root"] + "/ac_minimal.ds"
with dataset.open(path) as data:
    frame = data["AC1.AC"].to_dataframe().reset_index()
    sample = float(abs(frame["R1_v"].iloc[0]))
```

In the fresh validation program, open the persisted design with the default
read mode as shown above. `DesignMode.READ` is not an ADS 2027 member; do not
invent or pass it.

For another schematic cell, replace `ac_minimal.ds` with `<cell_name>.ds`; do
not derive the filename from the controller name. For the maintained AC
example, set `Dec` to `"5"` and `Step` to the empty string. Put
`required_artifacts` inside the `validation` object, and use the same relative
dataset filename in `scope.artifacts` and `validation.required_artifacts`.
