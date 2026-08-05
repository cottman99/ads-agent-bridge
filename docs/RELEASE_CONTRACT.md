# v0.1 Release Contract

## Product promise

A new user can install one package, select the intended local ADS installation,
query that installation's private local documentation, and run one verified
circuit workflow without learning the internal adapter or plugin architecture.

## User path

```text
pipx install ads-agent-bridge
ads-agent setup
ads-agent quickstart
```

`setup` must discover installed ADS instances, select one without silently
preferring the newest version, probe capabilities, install recoverable user
integration, and make documentation lookup immediately useful.

`quickstart` must report these gates independently:

1. documentation index;
2. documentation query;
3. add-on registration when the selected ADS supports Python add-ons;
4. disposable workspace creation;
5. circuit simulation;
6. dataset readback.

It passes only when all required gates pass.

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
- recoverable addon install, upgrade, and uninstall;
- localhost token-authenticated live bridge;
- disposable-workspace headless circuit simulation and dataset readback;
- one real two-port Momentum golden path;
- no vendor docs, private paths, or monorepo runtime imports.

## Non-blocking extensions

The full plugin platform, RFPro/FEM completeness, SIPro/PIPro, broad PDK
automation, AEL debugging, built-in SSH orchestration, and large example
catalogs do not block the first public beta.

## Evidence language

Use `discovered`, `indexed`, `installed`, `connected`, `created`, `saved`,
`reopened`, `simulated`, and `read_back` only when the corresponding observable
gate passed. Filesystem presence alone is not live ADS or solver evidence.
