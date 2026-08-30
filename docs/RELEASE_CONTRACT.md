# v0.1 Release Contract

## Product promise

A new user can install one package, select the intended local ADS installation,
install mutually routing public Bridge and Docs Skills, query that installation's private local
documentation, and progress through five explicit examples without learning
the internal adapter or plugin architecture.

For live GUI work, the same package owns a conservative session lifecycle:
launch ADS with an explicit workspace context, verify the bridge and active
workspace, distinguish agent-owned from externally owned sessions, disconnect
without closing ADS, and request native safe exit only for a verified
agent-owned session.

The operation catalog is not a second ADS API. Stable typed operations are
certified workflows and shortcuts. Broader capability must come from governed
official Python/AEL execution in an exact Context, using the common transaction
and validation mechanisms defined in `docs/ARCHITECTURE.md`.

## User path

```text
pipx install ads-agent-bridge
ads-agent setup
ads-agent quickstart
```

`setup` must discover installed ADS instances, select one without silently
preferring the newest version, probe capabilities, install recoverable user
integration, install both public Skills without replacing ambiguous unmanaged
content or overwriting a complete Kit-provided Docs Skill, make
documentation lookup immediately useful, and start resumable private
enrichment without blocking the first query.

`quickstart` must report these gates independently:

1. documentation index;
2. documentation query;
3. add-on registration when the selected ADS supports Python add-ons;
4. disposable workspace creation;
5. circuit simulation;
6. dataset readback.

It passes only when all required gates pass.

The live session lifecycle is a separate acceptance path:

1. select an explicit configured ADS instance;
2. preserve the platform's real ADS user profile while isolating Bridge state
   with `ADS_AGENT_HOME`, unless the test explicitly targets first-user setup;
3. validate an existing workspace without modifying it;
4. launch with both the workspace argument and `cwd=workspace`;
5. bind slot, display, and a one-time ownership identity before process start;
6. reserve the managed identity immediately after process creation and retain
   actionable `starting` state when bridge startup is delayed;
7. serialize launch and shutdown mutations for each slot across local clients;
8. wait for a token-authenticated DE bridge and verify its ownership nonce;
9. verify that a reused session's bridge-reported ADS installation root matches
   the selected instance, then verify the exact active workspace through ADS;
10. report UI readiness, visible windows, modal blocking, structured dialog
   controls, and ownership;
11. let a client Agent independently watch long operations, request a targeted
    dialog image when needed, and perform a fingerprint-bound action, with an
    actuation-time identity recheck, under an explicit risk policy;
12. use an identity-checked host desktop route for native or separate-process
    dialogs that appear before the embedded bridge is reachable;
13. disconnect without closing ADS;
14. asynchronously prompt for modified files, expose the shutdown state, and
    exit only a matching agent-owned session.

No default path may force-switch workspaces, discard modified content, close an
externally owned ADS process, or escalate to process termination.

## Support tiers

- ADS 2025 and later: stable target.
- ADS 2024 Update 2: preview target.
- ADS 2023 Update 2 through ADS 2024 Update 1: experimental target.
- Older versions: documentation-only when local docs can be discovered; no
  live Python bridge promise.

Version is a starting hint. Runtime capability probes decide whether DE, DDS,
addons, AEL interoperability, headless automation, or EM routes are available.

## v0.1 release blockers

- clean wheel and offline wheelhouse installation;
- automatic dependency installation;
- multi-instance discovery and explicit selection;
- Windows and Linux setup/docs/bridge gates;
- resumable private documentation indexing;
- private HTML-to-Markdown enrichment separated by ADS instance;
- recoverable, conflict-safe Bridge and Docs Skill installation with explicit
  ownership and Kit coexistence behavior;
- recoverable addon install, upgrade, and uninstall;
- localhost token-authenticated live bridge;
- profile-specific DE/DDS context menus with bounded, copyable context handles,
  explicit freshness, symmetric callback shutdown, and no implicit mutation;
- cross-platform workspace-bound ADS session launch, ownership, status,
  recoverable startup, per-slot mutation locking, disconnect, UI-blockage
  diagnosis, supervised dialog intervention, and native safe-exit gates;
- Windows and Linux connected-Qt observation/action gates, plus a Linux
  host-observation gate for one startup dialog that could not be reached through
  the embedded Qt bridge;
- disposable-workspace headless circuit simulation and dataset readback;
- five cataloged examples with explicit prerequisites, state changes, evidence,
  and nonzero failure behavior;
- no vendor docs, private paths, or monorepo runtime imports.

## Non-blocking extensions

Blank-layout Momentum setup authoring, the full plugin platform, RFPro/FEM
completeness, SIPro/PIPro, broad PDK automation, AEL debugging, built-in SSH
orchestration, and large example catalogs do not block the first public beta.
The bounded generated-input Momentum runner is an additive capability and does
not broaden that setup-authoring promise.

Generic non-modal business-window lifecycle automation, forced termination,
multi-client leases beyond per-slot mutation serialization, and remote
client/server ADS session transport remain non-blocking extensions. Dialog
automation is intentionally Agent-supervised: opaque dialogs may use targeted
vision, but high-risk or unverifiable outcomes stop for user confirmation.

## Evidence language

Use `discovered`, `indexed`, `installed`, `connected`, `created`, `saved`,
`reopened`, `simulated`, and `read_back` only when the corresponding observable
gate passed. Filesystem presence alone is not live ADS or solver evidence.
