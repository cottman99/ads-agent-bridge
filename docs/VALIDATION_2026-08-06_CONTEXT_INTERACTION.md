# ADS Context interaction validation — 2026-08-06

## Scope

This record validates the `0.1.0a24` candidate's bounded `ADS_CONTEXT:v1`
registry and its real DE/DDS menu integrations. It does not promote the
candidate to a published release and does not grant context handles authority
to open, edit, simulate, or close ADS objects.

## Package and automated gates

- Candidate wheel: `ads_agent_bridge-0.1.0a24-py3-none-any.whl`.
- Final post-review wheel SHA-256:
  `f5b8be6ef8f9da986c9e306fbdbbd685f5aa0a8ee10689dc9b57e9c823048d64`.
- Cross-platform live gates used the behavior-equivalent candidate4 wheel,
  SHA-256
  `6f9f0cbcf911c92b4364e731e68036acaacf82a849acd7d96fe6c6794f64a5bc`.
  The final rebuild removed an unused menu-search helper, added deterministic
  managed-instance identity propagation, and added this validation
  documentation. The final wheel then repeated the Linux DE right-click gate
  and returned `ads-2026-u2-1-70d4e416` as its instance ID.
- A post-review rebuild added fail-closed slot/profile validation for complete
  handles and made the 50-item serialization bound a traversal bound. Those
  changes do not alter the validated menu/callback paths; dedicated registry
  and server-command regressions cover the new boundaries.
- Unit tests: 91 passed.
- `compileall`, `pip check`, `git diff --check`, sdist build, and wheel build:
  passed.
- The installed add-on uses distinct `de_entrypoint.py` and
  `dds_entrypoint.py` files; DDS does not export DE's `generate_menu` hook.

## Linux live gate

Environment:

- a private Linux EDA server reached through SSH;
- ADS 2026 Update 2.1;
- isolated slot `a24_context_d4`, candidate HOME/state/workspace, and
  `DISPLAY=:4`;
- the server's canonical `ads-agent` remained `0.1.0a23`.

Observed evidence:

1. DE opened the exact disposable workspace and reported no modal blocker.
2. The Folder View workspace-root right-click menu visibly contained
   **Copy ADS Context** and produced a structured `workspace` envelope.
3. `context-get` accepted the copied handle; `context-refresh` advanced its
   generation from 1 to 2; `context-drop` removed it.
4. DDS registered exactly one window callback and one popup callback through
   their returned handles.
5. A bounded DDS readback created `ads_agent_dds_readback.dds`, evaluated
   `agent_readback=R1_v` as valid, and read 31 rows.
6. Opening the DDS file produced a DDS-owned top-level **ADS Context** menu.
   Its action captured the selected equation as structured data.
7. Right-clicking an empty DDS page produced a `dds-page` envelope with
   `selection.count=0`, without an error or modal dialog.
8. The candidate session exited through native safe shutdown. Existing
   display4/display2 ADS process trees remained alive.

During the first DDS live run, modifying ADS's existing dynamic **Tools** menu
encountered a deleted PySide `QAction`. The implementation was changed to the
official DDS window-callback pattern: each opened DDS window owns a top-level
menu. Candidate4 repeated the live gate with `last_error=null`.

## Windows live gate

Environment:

- ADS 2026 Update 2 on Windows;
- isolated candidate state, workspace, and slot `a24_context_windows`;
- temporary candidate registration in the normal ADS add-on XML files, with
  byte-for-byte backups taken before launch.

Observed evidence:

1. Candidate DE PID 15500 and DDS PID 29832 were nonce/slot-owned and separate
   from the pre-existing user DE/DDS processes.
2. UI Automation targeted the exact candidate workspace `TreeItem`, invoked
   its **Copy ADS Context** menu action, and produced a structured `workspace`
   envelope.
3. DDS readback again passed with 31 rows and `last_error=null`.
4. The DDS-owned top-level menu captured the selected equation. The DDS page
   right-click action also captured an empty selection as `dds-page`.
5. DDS refresh advanced the generation and drop removed the context.
6. Native safe shutdown removed only the candidate slot and processes.
7. Pre-existing user PIDs 56928 and 38020 remained alive.
8. `eesof_addons.xml` and `dds_addons.xml` were restored to their exact
   pre-test SHA-256 values:
   `D6A2F6CD69DB57EB155A97F2422D80914463BC74625EE3FFB4BD4C694F26AC05`
   and
   `3B5D89BE2B7690E455A3FF26BB33E821685E96B7E7E6F56076AC5BB46BCC3CA8`.

## Remaining boundary

The ADS **Get Started** dialog exposes a visible `Close` label but not a
clickable Qt button through the current dialog enumerator. For this isolated
gate, the exact candidate PID/title window was closed with one verified native
window-close message before the existing session was reused to open the
workspace. General welcome-page/window-close support remains separate from the
context-menu feature and should be addressed in the window lifecycle layer.
