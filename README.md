# ADS Agent Bridge

An unofficial, local-first documentation and automation bridge for Keysight
Advanced Design System (ADS).

> [!IMPORTANT]
> This is a limited public alpha. Use disposable ADS workspaces and review the
> reported capability gates before relying on automation results.
> Keysight and ADS are trademarks of Keysight Technologies. This project is
> not affiliated with or endorsed by Keysight.

The intended PyPI user path is three commands:

```text
pipx install ads-agent-bridge
ads-agent setup
ads-agent quickstart
```

PyPI publication is pending trusted-publisher authorization. Until then,
install the signed GitHub prerelease artifact directly:

```console
pipx install https://github.com/cottman99/ads-agent-bridge/releases/download/v0.1.0a17/ads_agent_bridge-0.1.0a17-py3-none-any.whl
ads-agent setup
ads-agent quickstart
```

The current alpha slice implements cross-platform ADS installation discovery,
capability/support reporting, per-installation local documentation indexing,
DE/DDS add-on registration, and a headless minimal-AC quickstart with dataset
readback.

It does **not** currently claim a completed Momentum, RFPro, FEM, SIPro, or
PIPro workflow. Those lanes require separate solver-side acceptance evidence.

Official ADS documentation is never distributed with this package. Indexes
are built privately from documentation already installed on the user's
machine.

Set `ADS_AGENT_HOME` to place configuration, data, and caches under an explicit
directory. This is useful for isolated tests, remote servers, and systems where
the normal user cache location is not appropriate.

## Install and verify

Prerequisites:

- a locally licensed ADS installation;
- Python 3.10 or later for the `ads-agent` command;
- `pipx` (recommended) or an isolated virtual environment.

```console
pipx install ads-agent-bridge  # after the PyPI publisher is authorized
ads-agent setup
ads-agent quickstart
```

When several ADS versions are found, interactive setup asks which one to use.
For an unattended or version-specific setup:

```console
ads-agent setup --ads-root /path/to/ADS2026_Update2 --non-interactive
```

A successful quickstart independently reports documentation, add-on,
workspace, circuit simulation, and dataset readback gates. It creates a new
disposable workspace and refuses to overwrite an existing path.

## Current commands

```text
ads-agent instances scan [--ads-root PATH]
ads-agent instances list
ads-agent instances use INSTANCE_ID
ads-agent compatibility explain [--ads INSTANCE_ID]
ads-agent docs ensure [--ads INSTANCE_ID]
ads-agent docs status [--ads INSTANCE_ID]
ads-agent docs query QUERY [--ads INSTANCE_ID]
ads-agent setup [--ads-root PATH] [--non-interactive] [--config-dir PATH]
ads-agent quickstart [--ads INSTANCE_ID] [--workspace PATH] [--config-dir PATH]
ads-agent addon status
ads-agent bridge sessions
```

Documentation queries stay on the local machine:

```console
ads-agent docs query "keysight.ads.de workspace" --limit 5
```

The bridge listens only on localhost and uses a random token per session.
Arbitrary embedded Python and dynamic AEL calls are disabled unless ADS is
launched with `ADS_AGENT_UNSAFE=1` and the client command also includes
`--unsafe`.

On Windows, `setup` reads Keysight's per-version `eeenv/HOME` registry values
to locate the real `hpeesof/config` directory. Use `--config-dir` (or
`ADS_AGENT_ADS_CONFIG_DIR`) when maintaining separate ADS profiles.

On Linux, ADS Python may still require an available X display even though the
quickstart opens no ADS window. Set `DISPLAY` to the intended isolated display
before running it. `setup` edits only the current user's ADS add-on XML files,
creates timestamped backups, and preserves unrelated add-ons.

Stable support is targeted at ADS 2025 and later. ADS 2024 Update 2 is a
preview target; ADS 2023 Update 2 through ADS 2024 Update 1 are experimental.
Runtime capability probes, rather than version numbers alone, decide which
features are actually available.

## Remove the integration

```console
ads-agent addon uninstall
```

The installer preserves unrelated ADS add-ons and creates timestamped XML
backups before changing an existing configuration.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) and the evidence-backed
[validation record](docs/VALIDATION_2026-08-05.md).
