---
schema_version: "eda.experience-asset/v1"
asset_version: "1.0.0"
id: "ads.schematic.apply-transaction"
kind: "action_pattern"
status: "validated"
summary: "Apply a bounded schematic plan to a staged ADS workspace and accept it only after fresh-process readback."
intents: ["modify an ADS schematic safely", "batch several known schematic edits"]
tags: ["ADS Python", "schematic", "staging", "fresh-reopen"]
applies_to: {"eda":"keysight-ads","versions":["2026"],"profiles":["de"],"os":["linux"],"capabilities":["design.apply"]}
prerequisites: ["exact source workspace and cell", "source fingerprint", "complete registered plan and assertions"]
recommendation: "Use this compiled shortcut only for its accepted plan vocabulary; generate governed ADS Python or AEL for other official schematic APIs."
steps: ["verify source", "copy workspace to staging", "apply known operations", "save and close", "fresh-process readback", "promote output"]
failure_signals: ["unexpected existing instance", "unsupported operation", "fresh-process assertion failure"]
validation: {"method":"fresh-process design readback and source preservation","evidence":"docs/VALIDATION_2026-08-29_STRUCTURED_DESIGN.md"}
official_refs: ["ads-docs://2026/python-api/design-environment"]
evidence_refs: ["docs/VALIDATION_2026-08-29_STRUCTURED_DESIGN.md"]
confidence: 0.9
last_verified: "2026-08-29"
supersedes: []
---

# Evidence boundary

The fixed operation vocabulary is a compiled fast path, not a replacement for
the ADS schematic API. Unsupported edits must use governed native execution.
