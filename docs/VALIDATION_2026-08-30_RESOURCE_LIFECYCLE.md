# ADS 2026 Update 2.1 resource-lifecycle acceptance

The `0.1.0a40` candidate was installed in the isolated ADS environment on `eda-server` and tested
with `DISPLAY=:4.0`. The test created one disposable empty workspace and a unique managed slot; it
did not touch existing ADS sessions and did not simulate.

- `session.launch` returned an `eda-runtime.resource/v1` resource for the new ADS process, including
  its stable managed-session id and the typed `session.shutdown` release payload.
- The live bridge verified the requested workspace, ownership nonce, process, display, and absence
  of a blocking modal dialog before reporting the session ready.
- `session.shutdown` accepted only the exact agent-owned slot, used the native bounded shutdown
  route, observed process exit, and removed only that slot's managed records.
- Existing refusal tests continue to cover user-owned sessions, conflicting slot selectors, modal
  dialogs, and incomplete native shutdown. No general process-kill operation was added.
