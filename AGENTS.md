# ADS Agent Bridge Development Contract

This repository is the clean, public product repository. Keep research,
customer workspaces, vendor documentation, generated indexes, and private
paths out of Git.

The critical user path is:

```text
pipx install ads-agent-bridge
ads-agent setup
ads-agent quickstart
ads-agent launch --workspace <workspace>
ads-agent status
ads-agent shutdown
```

Work that does not improve or protect that path is not a v0.1 release blocker.
Read `docs/RELEASE_CONTRACT.md` before expanding scope.

Capability work must also follow `docs/ARCHITECTURE.md` and
`docs/OPERATION_CLASSIFICATION.md`. Do not recreate the ADS API as a growing set
of Bridge wrappers. Treat typed operations as certified workflows; expand broad
functionality through version-matched official docs plus governed native
execution and reusable transaction/validation infrastructure.

Rules:

- Windows and Linux are equal release gates.
- ADS 2025 and later are the stable support target. Earlier Python-capable
  generations remain preview or experimental until their real runtime gates
  pass.
- Bind docs, capabilities, sessions, and examples to an explicit ADS instance.
- Prefer runtime feature probes over version-only assumptions.
- Keep the ADS embedded addon standard-library-only when practical.
- Listen on localhost and require a random session token.
- Never distribute Keysight documentation or a generated copy of it.
- Run tests from a non-system-drive temporary directory when available.
- A partial quickstart must return a non-zero status and name every unpassed
  gate; never report docs lookup as a completed automation roundtrip.

## User-facing release communication

- Write README and GitHub Release content for engineers who want to complete
  ADS work, not primarily for maintainers or API developers.
- Lead with the user outcome, then native ADS evidence and exact observed
  results. Put architecture, PRs, commits, and implementation detail later.
- Keep validation runs clean. Do not add screenshots, camera work, plots, or
  promotional steps to a timed engineering acceptance.
- After a successful run is frozen, promotional material may be made by
  reopening or replaying that exact accepted result. Record this separately as
  release preparation, never as engineering-task time.
- Prefer real ADS application-window captures and native editable schematic,
  layout, dataset, or DDS results. Do not substitute mockups or external
  replots for native evidence.
- Describe supported outcomes positively and precisely. Put useful planned
  expansion in a compact Roadmap or Next section instead of leading with
  defensive language.
- Keep installation and natural-language task examples prominent. Put
  compatibility detail, changelogs, PRs, checksums, and developer notes last.
- Follow the shared
  [user-facing release communication guide](https://github.com/cottman99/eda-bridge-runtime/blob/main/docs/USER_FACING_RELEASES.md)
  when editing a README, release note, public example, or homepage visual.
