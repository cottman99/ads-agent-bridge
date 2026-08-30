---
schema_version: "eda.experience-asset/v1"
asset_version: "1.0.0"
id: "ads.circuit.simulate-and-validate"
kind: "workflow"
status: "validated"
summary: "Run a bounded ADS circuit simulation and accept the job only when its dataset and declared artifacts validate."
intents: ["simulate an ADS circuit", "produce an accepted ADS dataset"]
tags: ["ADS", "circuit simulation", "dataset", "job"]
applies_to: {"eda":"keysight-ads","versions":["2026"],"profiles":["de"],"os":["linux"],"capabilities":["circuit.simulate"]}
prerequisites: ["accepted workspace and cell", "simulation plan", "license availability"]
recommendation: "Use for the accepted circuit-to-dataset lifecycle; preserve the durable receipt and validate dataset contents rather than process exit alone."
steps: ["stage workspace", "run official simulator", "bound timeout", "validate dataset and artifacts", "preserve source", "promote output"]
failure_signals: ["license failure", "simulation timeout", "missing or invalid dataset"]
validation: {"method":"real ADS simulation and dataset assertions","evidence":"docs/VALIDATION_2026-08-30_CIRCUIT_TO_DDS.md"}
official_refs: ["ads-docs://2026/simulation/python"]
evidence_refs: ["docs/VALIDATION_2026-08-30_CIRCUIT_TO_DDS.md"]
confidence: 0.9
last_verified: "2026-08-30"
supersedes: []
---

# Evidence boundary

This workflow compiles one accepted simulation lifecycle. Other controllers,
engines, or analyses use version-matched documentation and governed native code.
