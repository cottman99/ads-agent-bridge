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
