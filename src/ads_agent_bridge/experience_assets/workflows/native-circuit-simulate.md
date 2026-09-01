---
schema_version: "eda.experience-asset/v1"
asset_version: "1.0.0"
id: "ads.native.circuit-simulate-and-validate"
kind: "workflow"
status: "validated"
summary: "Build, simulate, and freshly validate an ADS 2027 circuit through one governed native batch."
intents: ["simulate an ADS circuit", "produce an accepted ADS dataset"]
tags: ["ADS", "ADS 2027", "native batch", "circuit simulation", "dataset"]
applies_to: {"eda":"keysight-ads","versions":["2027"],"profiles":["de"],"os":["linux"],"capabilities":["native.batch"]}
prerequisites: ["workspace.create continuation", "version-matched official ADS Python API", "license availability"]
recommendation: "Use the workspace continuation, one declared staged output, one simulator call, and fresh-process dataset validation."
steps: ["pass the opaque workspace continuation", "open the staged workspace", "open an existing schematic in DesignMode.WRITE", "build and save the circuit", "generate one netlist", "run CircuitSimulator once", "read and freshly validate the dataset", "promote the validated output"]
failure_signals: ["relative write path", "library not open", "read-only design", "simulation timeout", "missing or invalid dataset"]
validation: {"method":"real ADS 2027 native.batch simulation and fresh dataset readback","evidence":"docs/VALIDATION_2026-09-01_ADS2027_NATIVE_AC.md"}
official_refs: ["ads-docs://2027/simulation/python"]
evidence_refs: ["docs/VALIDATION_2026-09-01_ADS2027_NATIVE_AC.md"]
confidence: 0.95
last_verified: "2026-09-01"
supersedes: []
---

# Validated native mechanics

For a workspace returned by Runtime `workspace.create`, pass its opaque
`continuation_context` to the first `native.batch`. Declare one absolute sibling
output workspace. When the dataset is a retained artifact, also declare one
absolute artifact directory, list the dataset filename in `scope.artifacts`, and
write/read it below `context["artifact_root"]`.

In external ADS automation, open the staged workspace before opening its design.
An existing schematic intended for mutation must be opened with
`api.de.db.DesignMode.WRITE`; the default `open_design` mode is not a writable
mutation contract. Generate the netlist from the design, run exactly one
`keysight.edatoolbox.ads.CircuitSimulator.run_netlist`, and validate the
persisted dataset in the separate validation program. The validation return must
contain `{"status": "passed"}`. Do not use native observe calls to rediscover
these validated mechanics.
