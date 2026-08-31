# ADS supervised live-edit validation

The `0.1.0a48` candidate was exercised against ADS 2026 Update 2.1 on Linux
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
- The a48 extension activated the disposable schematic through ADS internal APIs,
  then created one `ads_rflib:R:symbol` instance with a `75 Ohm` value and one
  labeled wire in the already-open process. The first call completed in about
  253 ms of Bridge round-trip time.
- Repeating the same patch ID returned `preserved` in about 3 ms and created no
  duplicate objects. `rollback_patch` then deleted only the created instance and
  wire through a second ADS-native transaction in about 21 ms.
- Pi Agent independently exercised the same component-plus-wire contract through
  Runtime only: create `run_4a51d07546c646cb9b655cd8b391529c`, idempotent replay
  `run_9e52dde4e649439ca368b17c64dcb584`, and rollback
  `run_b7f6590a69ba4927845e60847e6246e6` all passed. It did not save or release
  the design implicitly; the disposable session was explicitly discarded and
  shut down after acceptance.

## Safety boundary

The active design identity must match exactly. Existing-value edits supply the
expected prior value; creation checks that the requested instance name is absent.
Each patch is committed as one ADS transaction, followed by readback. Saving,
discarding, and patch rollback require an explicit decision; a Context continues
to identify the target and is not mutation authority by itself.
