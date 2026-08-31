# ADS supervised live-edit validation

The `0.1.0a47` candidate was exercised against ADS 2026 Update 2.1 on Linux
virtual display 4. The acceptance used a disposable schematic and did not use
customer data or run a solver.

## Result

- Both Codex and Pi Agent captured the exact active design Context, changed one
  instance parameter in the already-open GUI session, read the new value back,
  and discarded the unsaved change.
- A fresh capture after discard observed the original saved value, proving that
  the explicit discard path restored the saved design state.
- Repeated edits reused the same ADS process and design window. No project copy,
  new permanent generation, or ADS restart was created per patch.
- Observed end-to-end edit calls were about 93-187 ms; after transport reuse,
  Bridge execution accounted for about 4-38 ms of that interval.

## Safety boundary

The active design identity must match exactly. Each patch supplies the expected
prior value and is committed as one ADS transaction, followed by readback.
Saving and discarding require an explicit finalization decision; a Context
continues to identify the target and is not mutation authority by itself.
