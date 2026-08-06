# 0.1.0a23 onboarding recovery validation

## Scope

This validation covers the three first-user failures found in the published
`0.1.0a22` blind test: selecting a usable Python when the system default is too
old, retaining Linux ADS process identity after the public launcher changes
lifetime, and handing a pre-bridge native dialog to a host Agent without
misreporting the session as orphaned.

## Isolation

- Host: edaserver
- GUI lane: `DISPLAY=:4`
- ADS: 2026 Update 2.1
- Isolated HOME, `ADS_AGENT_HOME`, pipx bootstrap, package environment,
  add-on registration, documentation index, and workspace
- Final-artifact test slot: `a23_final_blind`
- Existing sessions were treated as protected and checked after safe exit

## Accepted evidence

1. Linux installer preflight ignored the default Python 3.9 and selected the
   available Python 3.11.15.
2. The selected interpreter was PEP 668 externally managed. The installer
   created an isolated pipx bootstrap virtual environment and installed the
   local candidate wheel without modifying that interpreter.
3. Setup selected ADS 2026 Update 2.1, indexed 9,422 installed documentation
   files, and installed the isolated add-on and Docs Skill.
4. Quickstart passed documentation index, documentation query, add-on
   registration, workspace creation, circuit simulation, and dataset readback.
5. A 15-second GUI launch timeout returned `waiting-for-host-ui`, not
   `orphaned`. The response identified `hpeesofde`, `hpeesofemx`, and the
   nonce-bound `aglmpsel_exe` candidate host process.
6. After the host Agent applied the previously authorized `ADS Inclusive`
   preference to the verified product-selection process, status advanced to
   `workspace-ready` with verified agent ownership and the exact workspace.
7. Public live-context and bounded AEL examples passed on the same code before
   the version-only final build; the exact `0.1.0a23` artifact separately
   passed quickstart and the complete GUI lifecycle with unsafe Python disabled.
8. Public safe shutdown exited only the test slot. The four protected ADS
   process IDs remained alive.

## Local regression gate

The complete local suite passed with 71 tests after these changes. The Windows
installer also passed its real no-change interpreter-selection preflight under
PowerShell with Python 3.12.3.

## Boundary

The package reports and binds the host-UI handoff; it does not guess a license
selection. A client Agent may act only after verifying a candidate process and
applying an explicit workflow preference or user authorization.
