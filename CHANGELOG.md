# Changelog

All notable public changes are documented here.

## Unreleased

- Preserve the real Linux ADS user profile during isolated Bridge acceptance,
  document `ADS_AGENT_HOME` as the isolation boundary, and add a non-blocking
  doctor warning when the usual ADS per-user preference file is not visible.
- Remove private development paths and infrastructure addresses from the
  maintained validation records.
- Pin every GitHub Actions dependency to an immutable commit and add regression
  checks for action pins, release references, and changelog version alignment.
- Accurately describe the accepted manual-publish release tag without claiming
  that lightweight tags are signed.

## 0.1.0a27 - 2026-08-10

- Fix the Windows bootstrap installer when the selected Python does not already
  provide pipx: treat the failed module probe as the expected signal to create
  the isolated pipx bootstrap environment instead of terminating under
  PowerShell's strict error policy.
- Prefer pipx's explicit `pip` backend when supported on Windows and Linux so an
  unrelated, incompatible `uv` executable on the user's PATH cannot break the
  one-package installation path; retain compatibility with older pipx versions
  that do not expose backend selection.
- Add a Windows integration gate that starts from a clean Python environment
  without pipx, installs the local package through the public installer, and
  verifies the resulting `ads-agent` CLI.

## 0.1.0a26 - 2026-08-10

- Reduce private documentation token cost by extracting the maintained page
  body, removing navigation/build chrome and private-use glyphs, preferring the
  visible H1 over browser-title branding, and eliminating duplicate headings.
- Rebuild version-scoped documentation indexes under schema 3 and expose live,
  committed enrichment progress while a background build is still running.
- Improve documentation retrieval by treating explicit ADS/Python/AEL/DDS
  terms as domain filters, ranking API reference and runnable examples ahead of
  generic pages, and centering bounded snippets on the best matching signature
  without destroying Python indentation.
- Return a structured nonzero Quickstart result when ADS automation exceeds its
  timeout, retaining bounded output and any partial-workspace path without
  accepting a late success record from the terminated process.
- Isolate runtime snapshot tests from a host's global ADS installation variable
  so the same wheel suite runs unchanged on developer machines and EDA servers.
- Validate the six-gate Quickstart with licensed ADS 2026 Update 2 on Windows,
  complete a 9,422-page private documentation rebuild with zero conversion
  errors, and pass clean package checks on Windows Python 3.10/3.12 and Linux
  Python 3.11/3.13.

## 0.1.0a25 - 2026-08-07

- Add the first `bridge-runtime-snapshot/v1` and
  `bridge-capability-descriptor/v1` contracts for compact Agent preflight.
- Expose a revision-aware `bridge runtime-snapshot` command that avoids copying
  the full context registry or returning full window inventories by default.
- Preserve the Kit/bridge boundary: the bridge reports live runtime facts while
  higher-level systems own task intent, authorization, routing, and evidence.
- Preserve nested descriptor and snapshot arrays across the authenticated wire
  serializer; live ADS validation caught and now covers the prior depth cutoff.
- Add a cross-platform pre-bridge Host UI contract with nonce/PID-bound window
  inventory, targeted PNG capture, fingerprint-bound client-relative clicks,
  native close, and explicit risk/authorization decisions.
- Package Pillow and Linux Xlib support so host-image handling works after the
  normal one-package install without a separate user dependency step.
- Keep product selection policy outside the package: no vendor title, license
  row, bundle id, or fixed-coordinate rules are embedded; ADS retains its own
  remembered selection after the verified first-run action.
- Keep Windows capture and actuation in physical client pixels by entering a
  per-monitor DPI-aware context before User32 geometry, Pillow capture, or
  client-relative input.

## 0.1.0a24 - 2026-08-07

- Add bounded `ADS_CONTEXT:v1` handles for exact DE design-window,
  Folder/Library tree, and live DDS window targets and selections.
- Validate each handle's encoded slot and profile before resolving its
  process-local id, and bound generic selection traversal as well as output.
- Keep live-object ownership inside a 64-entry process-local registry while
  exposing only bounded, token-free envelopes with freshness generations and
  explicit authorization requirements.
- Add safe bridge and CLI operations to list, inspect, refresh, and drop
  contexts without silently opening or mutating an ADS object.
- Split DE and DDS add-on entrypoints so DDS never exports the DE
  `generate_menu` hook, and unregister every callback through its documented
  profile-specific lifecycle.
- Add non-modal **Copy ADS Context** actions to supported right-click menus,
  DE's **Tools > ADS Context** menu, and a DDS-owned top-level menu, including
  empty-selection DDS pages and multi-item workspace context sets.

## 0.1.0a23 - 2026-08-06

- Adopt Linux `hpeesofde` and `hpeesofemx` processes only when both the exact
  managed-session nonce and slot match, so a short-lived `ads` wrapper cannot
  make a live ADS session appear orphaned or allow a duplicate launch.
- Report `waiting-for-host-ui` when a nonce-bound ADS process is alive but its
  embedded bridge is not reachable, with a bounded display, workspace, primary
  process, and observation-only candidate-process handoff.
- Include nonce-bound separate-process UI helpers in the host observation
  inventory without treating them as ADS ownership evidence.
- Add Linux and Windows bootstrap installers that find Python 3.10+, support an
  explicit interpreter or offline wheel, and provide a no-change preflight.
- Bootstrap missing `pipx` inside a dedicated virtual environment instead of
  modifying PEP 668 externally managed Python installations.
- Revalidate setup, six-gate quickstart, pre-bridge product selection,
  workspace readiness, bounded live examples, and native safe exit on Linux
  `DISPLAY=:4` without disturbing existing ADS sessions.

## 0.1.0a22 - 2026-08-06

- Add a cross-platform ADS Session Manager with workspace-bound launch,
  verified agent ownership, status, stateless disconnect, and native safe exit.
- Pass the workspace as both the ADS launch argument and process working
  directory, then verify the active workspace through the authenticated bridge.
- Refuse implicit slot reuse, different-workspace switching, user-owned
  shutdown, ownership mismatches, and shutdown while a modal dialog is active.
- Add bounded bridge commands for opening an empty workspace context and for
  prompting to save modified files before scheduling the native ADS exit.
- Prefer the supported `ads` launcher during installation discovery while
  retaining older executable-name fallbacks.
- Detach GUI ADS standard input from SSH and route stdout/stderr to a
  per-session local log so a successful remote launch returns promptly.
- Remove dead DE/DDS bridge records for a completed owned slot after native
  exit, while retaining live or identity-mismatched records.
- Refuse partially occupied slots and report exit only after every live bridge
  profile in the managed slot has stopped.
- Preserve a recoverable `starting` record and launch log when license,
  first-run, or add-on startup delays prevent the DE bridge from appearing.
- Serialize lifecycle mutations per slot across local client processes and fix
  identity-checked managed-record removal after a completed exit.
- Report bounded top-level window and modal state without title-specific rules
  or automatic clicks; surface launch as `blocked` when ADS needs user action.
- Make native modified-file prompting asynchronous and expose shutdown states,
  including `cancelled` and `awaiting-user-action`, instead of leaving a remote
  client request apparently hung.
- Add Agent-supervised dialog automation: independent watching, structured Qt
  labels/buttons/roles, optional targeted PNG capture for vision, and exact
  fingerprint-bound button actions with enforced risk and authorization floors.
- Revalidate the active modal fingerprint and target button inside the Qt
  actuation callback, expose its terminal state, and classify `No`, `NoToAll`,
  and `NoRole` at no lower than medium risk.
- Reacquire and raw-identity-check native ADS buttons after semantic inspection
  so dialogs that rebuild PySide wrappers remain safely actionable.
- Refuse existing-session reuse unless the bridge-reported ADS installation
  root matches the explicitly selected instance, before any workspace action.

## 0.1.0a21 - 2026-08-05

- Keep first-use documentation queries bounded: multi-term misses relax inside
  the local bootstrap index before a one-second, 200-file source fallback.
- Normalize client slot names exactly like the embedded bridge, so names such
  as `Windows-A21-Live` select the `windows_a21_live` session.
- Hide session records whose ADS process has exited, using a read-only Windows
  process probe instead of sending process signals.
- Return documentation enrichment state with every query so clients can
  distinguish bootstrap results from the completed private Markdown corpus.

## 0.1.0a20 - 2026-08-05

- Add a five-example public catalog with machine-readable prerequisites,
  state-change boundaries, acceptance evidence, and `examples list/show/run`.
- Add bounded live DE context, DDS dataset readback, and fixed read-only AEL
  workspace examples without enabling arbitrary embedded execution.
- Package a portable `ads-kb-docs` Codex skill with conflict-safe,
  recoverable install/status/uninstall commands.
- Keep fast documentation bootstrap immediately available while an optional
  background job converts installed HTML into private per-instance Markdown
  and enriches the local SQLite index.
- Keep version selection explicit and capability-driven across supported ADS
  installations; no example or skill is tied to the newest installed version.
- Include ADS's bundled Python libraries in the Linux headless runtime search
  path so the packaged quickstart does not depend on an interactive shell.

## 0.1.0a19 — 2026-08-05

- Add a read-only `ads-agent doctor` covering discovery, selected version,
  local docs, ADS Python, add-on registration, and live bridge sessions.
- Keep diagnostic reads from creating empty configuration, cache, data, or
  runtime directories.
- Record and enforce the external ADS automation context in the headless
  quickstart result.
- Build release distributions once, publish the exact artifacts to GitHub and
  PyPI, and verify their SHA256 values after upload.
- Update maintained GitHub Actions to Node 24-capable major versions.

## 0.1.0a18 — 2026-08-05

- Discover non-default Windows ADS installations from registered installer
  locations, including side-by-side versions on other drives.
- Publish through token-free PyPI Trusted Publishing with separate build and
  upload permission boundaries.
- Update the public installation path now that the package is available from
  PyPI.

## 0.1.0a17 — 2026-08-05

Initial limited public alpha.

- Discover and explicitly select local ADS installations on Windows and Linux.
- Classify stable, preview, experimental, and unsupported ADS generations.
- Build a private per-installation search index from locally installed HTML
  documentation without redistributing Keysight content.
- Install, inspect, upgrade, and uninstall the DE/DDS user add-on with backups.
- Connect to authenticated localhost-only DE and DDS bridge sessions.
- Keep arbitrary Python and AEL execution behind explicit two-sided unsafe
  opt-in.
- Run a disposable headless minimal-AC workspace and validate its ADS dataset.
- Locate Windows ADS user configuration through Keysight `eeenv/HOME` registry
  values, with an explicit config-directory override.
- Redact session bearer tokens from public CLI output.

Momentum, RFPro, FEM, SIPro, and PIPro are not part of this alpha's supported
workflow claim.
