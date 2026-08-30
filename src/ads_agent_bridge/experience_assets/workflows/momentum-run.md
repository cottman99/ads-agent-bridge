---
schema_version: "eda.experience-asset/v1"
asset_version: "1.0.0"
id: "ads.momentum.run-generated"
kind: "workflow"
status: "validated"
summary: "Run a generated Momentum project through a bounded solver lifecycle and validate its CITI output artifacts."
intents: ["run a generated Momentum project", "produce validated Momentum S-parameters"]
tags: ["ADS Momentum", "EM", "CITI", "solver"]
applies_to: {"eda":"keysight-ads","versions":["2026"],"profiles":["de"],"os":["linux"],"capabilities":["momentum.run_generated"]}
prerequisites: ["generated project source", "source fingerprint", "new output directory", "license availability"]
recommendation: "Use this compiled workflow for its accepted generated-project contract; other Momentum setup and model operations remain governed native work."
steps: ["verify source fingerprint", "stage generated project", "run Momentum", "validate CITI artifacts", "preserve source", "promote output"]
failure_signals: ["source drift", "solver timeout", "missing or invalid CITI file"]
validation: {"method":"real Momentum run and CITI assertions","evidence":"docs/VALIDATION_2026-08-30_MOMENTUM_GOLDEN.md"}
official_refs: ["ads-docs://2026/momentum/command-line"]
evidence_refs: ["docs/VALIDATION_2026-08-30_MOMENTUM_GOLDEN.md"]
confidence: 0.9
last_verified: "2026-08-30"
supersedes: []
---

# Evidence boundary

The shortcut proves one generated-project solver path. It is not a complete
Momentum API and does not make generated projects the only supported workflow.
