# Host UI validation — 2026-08-07

## Scope

This gate validated the unreleased pre-bridge Host UI contract against isolated
ADS 2026 Update 2 launches on Linux and Windows. The Linux launch used a
dedicated X display; neither platform modified or restarted separately running
ADS sessions.

The validated package was installed into a scratch virtual environment. The
machine's normal `ads-agent` installation remained on the latest published
release throughout the gate.

## Result

The Linux targeted-image/action lane passed.

1. The Session Manager returned `waiting-for-host-ui` with an exact slot,
   managed-session nonce, display, workspace, ADS process inventory, and
   `aglmpsel_exe` candidate PID.
2. `host-ui snapshot` accepted only a visible window owned by a candidate PID
   and captured a 598 x 320 PNG of that one window.
3. The returned fingerprint bound the slot, nonce, display, window id, PID,
   title, class, and client geometry.
4. Three separate medium-risk, workflow-authorized actions selected the
   explicitly approved product, enabled the vendor's persistent-selection
   checkbox, and confirmed the dialog. A fresh target image verified each
   meaningful transition.
5. ADS reached an authenticated, nonce-matching embedded bridge. Its ordinary
   first-run dialogs were observable through the existing Qt dialog lane.
6. The vendor selector wrote the isolated preference as:

   ```text
   ADS_PRODSEL_AUTOSTART = true
   ADS_PRODSEL_PREVIOUS = b_ads_inclusive
   ```

7. After native safe exit, the same isolated HOME relaunched to an
   authenticated bridge in four seconds without `aglmpsel_exe` and without a
   `waiting-for-host-ui` state.
8. The second agent-owned session also exited through native safe shutdown.

A final-candidate recheck then launched a fresh isolated HOME. The managed
contract retained the launch-time X authority path; `host-ui snapshot` still
succeeded after `XAUTHORITY` was removed from the later client environment.
The final code captured the selector, selected the approved row after an
actuation-time identity recheck, closed that exact selector through
`WM_DELETE_WINDOW`, rebound to the new PID/fingerprint of the expected license
error, and closed that window independently. No process from the final test slot
remained afterward.

The package contains no product title, license row, bundle id, or fixed click
coordinate. Coordinates came from the current targeted image and every action
re-read the session/window fingerprint before actuation.

## Accessibility finding

The product selector inherited `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`, but the
vendor Qt 6 runtime did not register an AT-SPI application tree on this host.
The target-image lane is therefore a required fallback, not merely a unit-test
convenience. Operating-system accessibility remains the preferred first source
when a particular ADS/runtime combination exposes it.

## Windows live gate

The same contract passed a first-run Product Selection gate on Windows with
ADS 2026 Update 2 and an isolated HOME, package state, workspace, and slot.
A pre-existing user ADS workspace and its PIDs were treated as protected.

1. Clearing only the two saved product-selection values caused `launch` to
   return `waiting-for-host-ui` with the exact managed nonce and the descendant
   `aglmpsel.exe` PID.
2. The first targeted image exposed a real mixed-DPI defect: User32 geometry
   was virtualized while Pillow captured physical desktop pixels. The image
   included part of another window and clipped the target, so no click was
   attempted from it.
3. The Windows lane now enters a per-monitor-v2 thread DPI context before
   enumerating, capturing, or acting. Its records explicitly declare
   `coordinate_space=physical-client-pixels`; that field participates in both
   the window fingerprint and the actuation-time identity recheck.
4. The corrected 663 x 319 image contained only the Product Selection client.
   Fresh fingerprint-bound actions selected the explicitly approved
   `ADS Inclusive` row, enabled the persistent-selection checkbox, and
   confirmed the dialog. A targeted image verified every transition.
5. ADS reached the authenticated, nonce-matching bridge three seconds after
   confirmation, with the exact isolated workspace and no modal blocker.
6. Windows persisted the choice in its native user preference store as
   `ADS_PRODSEL_AUTOSTART=true` and
   `ADS_PRODSEL_PREVIOUS=b_ads_inclusive`, matching the pre-test values.
7. Native safe shutdown exited only the candidate. A second launch using the
   same isolated HOME reached `workspace-ready` in 4.86 seconds without a
   Product Selection process or `waiting-for-host-ui`, then exited through the
   same native safe-shutdown route.
8. The ADS 6.40 HOME registry value was restored to its exact pre-test path,
   and the protected user ADS PIDs remained alive throughout the gate.

With this result, the maintained Host UI contract has live first-run evidence
on both Linux and Windows. Publication still requires the ordinary final source,
artifact, CI, GitHub, and PyPI gates.
