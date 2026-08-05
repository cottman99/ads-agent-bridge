# ADS Agent Bridge

An unofficial, local-first documentation and automation bridge for Keysight
Advanced Design System (ADS).

> [!IMPORTANT]
> This is a limited public alpha. Use disposable ADS workspaces and review the
> reported capability gates before relying on automation results.
> Keysight and ADS are trademarks of Keysight Technologies. This project is
> not affiliated with or endorsed by Keysight.

The intended PyPI user path is four commands:

```text
pipx install ads-agent-bridge
ads-agent doctor
ads-agent setup
ads-agent quickstart
```

The current alpha slice implements cross-platform ADS installation discovery,
capability/support reporting, per-installation local documentation indexing,
DE/DDS add-on registration, and a headless minimal-AC quickstart with dataset
readback. Setup also installs the portable `ads-kb-docs` Codex skill when its
target directory is free and starts private full-text documentation enrichment
in the background.

It does **not** currently claim a completed Momentum, RFPro, FEM, SIPro, or
PIPro workflow. Those lanes require separate solver-side acceptance evidence.

Official ADS documentation is never distributed with this package. Indexes
and Markdown caches are built privately from documentation already installed
on the user's machine.

Set `ADS_AGENT_HOME` to place configuration, data, and caches under an explicit
directory. This is useful for isolated tests, remote servers, and systems where
the normal user cache location is not appropriate.

## Install and verify

Prerequisites:

- a locally licensed ADS installation;
- Python 3.10 or later for the `ads-agent` command;
- `pipx` (recommended) or an isolated virtual environment.

```console
pipx install ads-agent-bridge
ads-agent doctor
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

To leave Codex skills unchanged or postpone full-text conversion:

```console
ads-agent setup --skip-skill --no-background-docs
```

## Five public examples

List the supported examples and their prerequisites before running one:

```console
ads-agent --pretty examples list
```

The initial catalog is intentionally small:

1. ADS installation discovery and explicit version selection;
2. a headless minimal-AC workspace, simulation, and dataset readback;
3. read-only live DE workspace context;
4. bounded DDS dataset readback into a new native DDS file;
5. a fixed read-only AEL workspace call demonstrating the hybrid boundary.

Every runner emits JSON, names its required state, and returns nonzero when its
acceptance gate is not met. See [the example guide](docs/EXAMPLES.md) for exact
commands and stop rules.

## Portable Docs Skill

`setup` installs the `ads-kb-docs` skill without replacing an existing skill.
It can also be managed explicitly:

```console
ads-agent skill status docs
ads-agent skill install docs
ads-agent skill uninstall docs
```

The fast index is immediately queryable. Full enrichment converts installed
HTML into private per-version Markdown and updates the local SQLite index:

```console
ads-agent docs ensure
ads-agent docs build --background
ads-agent docs status
```

Use `--ads INSTANCE_ID` on any docs command to bind the result to a non-default
installation. No ADS version is hard-coded into the skill.

## Current commands

```text
ads-agent doctor [--ads-root PATH] [--search-root PATH] [--no-ping]
ads-agent instances scan [--ads-root PATH]
ads-agent instances list
ads-agent instances use INSTANCE_ID
ads-agent compatibility explain [--ads INSTANCE_ID]
ads-agent docs ensure [--ads INSTANCE_ID]
ads-agent docs build [--ads INSTANCE_ID] [--background]
ads-agent docs status [--ads INSTANCE_ID]
ads-agent docs query QUERY [--ads INSTANCE_ID]
ads-agent setup [--ads-root PATH] [--non-interactive] [--config-dir PATH]
ads-agent quickstart [--ads INSTANCE_ID] [--workspace PATH] [--config-dir PATH]
ads-agent examples list
ads-agent examples show NAME
ads-agent examples run NAME [--ads INSTANCE_ID] [--slot SLOT]
ads-agent skill status|install|uninstall docs
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
