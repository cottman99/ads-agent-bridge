# Session Manager validation — 2026-08-06

## Scope

This record covers the unreleased L3 ADS Session Manager slice:

```text
launch -> bridge ready -> exact workspace verified -> status
       -> disconnect without exit -> native safe shutdown
```

It does not promote generic non-modal window automation, unbounded dialog handling,
multi-client leases, forced termination, or remote transport to supported
capabilities.

## Automated gates

- Windows development suite: 63 tests passed.
- Source whitespace gate: `git diff --check` passed.
- The tests cover launch planning, `cwd=workspace`, ownership identity,
  different-workspace refusal, user-owned shutdown refusal, modal refusal,
  asynchronous prompt-before-exit behavior, shutdown cancellation and
  user-action states, recoverable startup, per-slot operation locking, bounded
  UI diagnostics, identity-checked stale record cleanup, and partial-slot
  refusal. Dialog tests additionally cover structured Qt observation, exact
  fingerprint and button binding, scheduling-time and actuation-time stale-dialog
  refusal, destructive and negative-role risk floors, selected ADS installation
  matching before session reuse, CLI image extraction, and the independent
  watcher entrypoint.

## Linux live gate

Environment:

- ADS 2026 Update 2.1 on Linux;
- GUI isolated to `DISPLAY=:4`;
- candidate wheel installed into a disposable virtual environment and state
  root;
- a distinct workspace and bridge slot were used;
- existing `:2` and `:4` ADS sessions were treated as externally owned.

Observed evidence:

1. Clean-wheel quickstart passed documentation index/query, add-on
   registration, disposable workspace creation, minimal AC simulation, and
   dataset readback.
2. `launch` selected the installation's `bin/ads` entrypoint, passed the
   workspace as an argument, used the same path as the working directory, and
   reported `workspace-ready`.
3. The live bridge returned the one-time managed session identity, exact
   workspace, `DISPLAY=:4`, `is_pde_app=true`, and no active modal dialog.
4. `disconnect` returned while ADS remained reachable.
5. Reusing the same slot and workspace was idempotent. Reusing the slot with a
   different workspace returned nonzero and left the active workspace intact.
6. A shutdown request against a pre-existing session returned nonzero with
   `ownership=user-owned`; the existing Linux sessions remained alive.
7. The managed session accepted
   `prompt_and_save_modified_workspace_then_exit_application`, exited without
   force termination, and removed its ownership record.
8. After stdout/stderr were redirected to the per-session log, an SSH launch
   completed and returned its full JSON result in 5.11 seconds instead of
   leaving the SSH channel open.
9. A separate ADS product-selection process blocked the candidate before the
   embedded bridge was reachable. Its PID, parent ADS PID, workspace,
   environment, window class, and `DISPLAY=:4` identity were verified before
   the host Agent selected `ADS Inclusive`. No persistent "always use"
   preference was enabled, and the candidate then reached `workspace-ready`.
10. An independent `dialog-watch` client detected a synthetic Qt modal while
    the work lane remained available. The snapshot exposed its title, label,
    enabled `OK` button, `AcceptRole`, low-risk floor, geometry, and targeted
    PNG.
11. Changing the dialog after observation caused the old fingerprint action
    to be rejected. A fresh low-risk action was accepted, the modal
    disappeared, and the blocked workflow callback completed with result 1024.
12. Native safe shutdown exited only the candidate processes. The previously
    running `:2` and `:4` ADS processes remained alive, and the server command
    still reported published version `0.1.0a21`.
13. A final review-fix candidate (`SHA256
    830CBF15C1BAA27DDEA4D1D4D95F82207E8E902262EFBE06E39642F1D7BE3EDF`)
    created a real unsaved schematic through `db_uu.create_schematic()` and an
    unsaved component edit. Native shutdown exposed `Save Modified Designs`.
    `Cancel` actuated at low/automatic policy, returned shutdown to `cancelled`,
    and kept ADS alive. A second prompt accepted `Yes` only at
    medium/workflow-policy, saved `%Unsaved%Shutdown%Gate3/schematic/sch.oa`,
    and exited only candidate PID 1664291. Protected PIDs 1199478 and 1246829
    remained alive, and the canonical server environment remained 0.1.0a21.

The disposable candidate environment was removed after the gate. The server's
canonical environment and add-on registration were restored to the latest
published release, `0.1.0a21`.

## Windows live gate

Environment:

- ADS 2026 Update 2 on Windows;
- disposable package state, workspace, and slot;
- a pre-existing user ADS process and workspace were explicitly excluded from
  reuse and shutdown.

Observed evidence:

1. Clean-state quickstart passed all six gates and produced a 31-row minimal
   AC dataset.
2. `launch` used `bin/ads.exe`, passed the workspace as the positional
   argument, set `cwd` to the same path, and returned `workspace-ready` in
   35.08 seconds.
3. The bridge reported the exact workspace, matching ownership identity,
   `is_pde_app=true`, and no active modal dialog.
4. `disconnect` left the managed ADS process alive and reachable.
5. Native safe shutdown exited only the managed process and removed its
   ownership record. The pre-existing user ADS process remained alive.
6. Candidate add-on registration was uninstalled after the test; the ADS
   registry HOME and the pre-test registration state were unchanged.
7. The final candidate wheel repeated the independent watcher, structured Qt
   snapshot, targeted PNG, stale-fingerprint rejection, fresh low-risk action,
   dialog disappearance, and blocked-callback completion gates against ADS
   2026 Update 2.
8. The candidate was PID 552; native safe shutdown removed that process and
   its slot while the pre-existing user ADS PIDs 49640/56928 remained alive.
9. Both `eesof_addons.xml` and `dds_addons.xml` were restored byte-for-byte to
   their pre-test SHA-256 values after temporarily disabling the legacy local
   loader for candidate isolation.
10. A final native unsaved-design gate used candidate PID 17948 and slot
    `review_fix_unsaved_windows`. It created
    `AgentBridgeExamples_lib:UnsavedShutdownWindowsGate:schematic` with an
    unsaved component edit and received the native `Save Modified Designs`
    dialog.
11. `Cancel` actuated under low/automatic policy, changed shutdown state to
    `cancelled`, and kept candidate ADS alive. A second shutdown accepted
    `Yes` only under medium/workflow-policy, saved
    `%Unsaved%Shutdown%Windows%Gate/schematic/sch.oa`, and exited candidate PID
    17948.
12. Protected user PIDs 49640 and 56928 remained alive. After the gate,
    `eesof_addons.xml` and `dds_addons.xml` were again verified at their exact
    pre-test hashes: `D6A2F6CD69DB57EB155A97F2422D80914463BC74625EE3FFB4BD4C694F26AC05`
    and `3B5D89BE2B7690E455A3FF26BB33E821685E96B7E7E6F56076AC5BB46BCC3CA8`.

## Defects found by the live gate

### SSH launch inherited standard streams

The first Linux launch reached `workspace-ready`, but ADS inherited the SSH
channel's stdout/stderr descriptors, so the client command did not return.
The launcher now uses `stdin=DEVNULL`, writes stdout/stderr to a per-session
local log, and starts a new POSIX process session.

### Native exit left stale bridge JSON

ADS native exit did not consistently invoke every add-on shutdown hook, so
dead DE/DDS session files could remain. Session discovery already hid dead
PIDs; the manager now additionally removes only dead records from its verified
owned slot after all live profiles have exited. Identity-mismatched and live
records are retained.

### Informational OK was initially over-classified

The first risk-floor implementation treated every Qt `AcceptRole` button as
medium risk. Real informational message boxes use that role for the standard
`OK` button, so automatic acknowledgement would have been rejected. The floor
now classifies standard `OK` as low risk while preserving medium floors for
save/open/apply/yes operations and high floors for discard or destructive
roles. Unit and Windows/Linux live gates verified the corrected behavior.

### Pre-bridge dialogs require a host-side lane

The Linux product-selection dialog proved that an embedded Qt bridge cannot
observe every startup blocker: this window was owned by a separate child
process before the add-on started. The product contract therefore keeps host
accessibility/vision as a required client-Agent capability, with exact process
and target-window identity checks before any action. Once the embedded bridge
is reachable, dialog actions use Qt semantics and never rely on coordinates.

### Native ADS dialogs can rebuild PySide button wrappers

The real `Save Modified Designs` dialog invalidated every button wrapper after
standard-button and role inspection, even though a fresh `findChildren()` call
returned the same indexed controls. Returning the observed wrapper into a later
callback therefore failed with `Internal C++ object ... already deleted`. The
actuation path now rechecks the full dialog fingerprint, reacquires the button
by its fingerprinted index, rechecks class/object name/text/visibility/enabled
state without another role query, and retains the fresh dialog and button list
through `click()`. The final Linux cancel/save gate verified both low- and
medium-risk actions against this native dialog.

## Release completion requirements

- The final source commit must pass the maintained Windows/Linux CI matrix.
- The tagged source must produce one wheel/sdist pair that passes package
  metadata checks and clean-install smoke tests.
- GitHub and PyPI must receive the same workflow artifact, and the publish
  workflow must verify PyPI hashes before the release is considered complete.

At the close of this validation record, the strongest claim was
**live-validated release candidate**. Publication status is established by the
signed tag, GitHub prerelease, PyPI project page, and publish-workflow evidence,
not by this pre-publication test record alone.

The final local suite contains 64 tests. It also verifies exclusive dialog PNG
creation, so the command's no-overwrite promise remains true if another process
creates the output after path validation but before storage.

The pre-tag `0.1.0a22` packaging gate produced a wheel with SHA-256
`F96990B750D64F4CA7453793F1D8F92A1D162CC2FF8A0336BBD01F0651EDF7E9` and an
sdist with SHA-256
`E821F68CD77078C6E6CEE1A145FEFBDB50BE5605ED28D79172373EE06996ABD7`.
Both passed `twine check`; a clean virtual environment installed the wheel and
reported `ads-agent 0.1.0a22` with no broken requirements.
