---
schema_version: "eda.experience-asset/v1"
asset_version: "1.0.0"
id: "ads.dds.create-native-display"
kind: "workflow"
status: "validated"
summary: "Create an editable native ADS DDS display without overwriting an existing file and verify it in a fresh DDS process."
intents: ["create an ADS data display", "plot accepted simulation data in native DDS"]
tags: ["ADS DDS", "native plot", "fresh-reopen"]
applies_to: {"eda":"keysight-ads","versions":["2026"],"profiles":["dds"],"os":["linux"],"capabilities":["dds.create"]}
prerequisites: ["existing dataset", "non-existing DDS output", "declared pages and plots"]
recommendation: "Use the accepted DDS plan as a compact shortcut; do not extend it one widget at a time when official DDS APIs can be run through governed native execution."
steps: ["validate dataset and plan", "create native DDS file", "save and close", "fresh-process reopen", "read back pages and plots"]
failure_signals: ["output already exists", "dataset expression missing", "fresh-process DDS mismatch"]
validation: {"method":"native DDS fresh-process readback","evidence":"docs/VALIDATION_2026-08-30_CIRCUIT_TO_DDS.md"}
official_refs: ["ads-docs://2026/dds/python-api"]
evidence_refs: ["docs/VALIDATION_2026-08-30_CIRCUIT_TO_DDS.md"]
confidence: 0.88
last_verified: "2026-08-30"
supersedes: []
---

# Evidence boundary

Rectangular and polar plots are validated examples, not the extent of DDS.
Smith charts, markers, tables, and future controls should not each become a new
Bridge wrapper.
