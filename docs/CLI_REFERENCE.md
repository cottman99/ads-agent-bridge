# CLI and installation reference

This page keeps operational detail out of the product README while preserving
the complete public command surface and installation controls.

## Bootstrap installer

The bootstrap installer searches installed Python versions instead of assuming
the system default is usable. When pipx is missing, it creates an isolated
bootstrap environment and does not modify an externally managed system Python.

Select an explicit interpreter or install an offline/local wheel:

```console
sh install.sh --python /path/to/python3.11 --package /path/to/ads_agent_bridge.whl
.\install.ps1 -Python C:\Path\To\python.exe -Package C:\Path\To\ads_agent_bridge.whl
```

Use `--check` on Linux or `-Check` on Windows to verify interpreter selection
without installing or changing `PATH`.

## Setup controls

Select a specific ADS installation without an interactive prompt:

```console
ads-agent setup --ads-root /path/to/ADS2026_Update2 --non-interactive
```

Leave Codex skills unchanged or postpone full-text conversion:

```console
ads-agent setup --skip-skill --no-background-docs
```

Set `ADS_AGENT_HOME` to isolate Bridge configuration, data, caches, add-on
session files, and runtime records. On Linux, do not replace the user's real
`HOME` merely to isolate Bridge state: ADS uses it for per-user product and
license preferences. An alternate `HOME` is appropriate only for a deliberate
first-user/product-selection test.

On Windows, `setup` reads Keysight's per-version `eeenv/HOME` registry values
to locate the real `hpeesof/config` directory. Use `--config-dir` or
`ADS_AGENT_ADS_CONFIG_DIR` when maintaining a separate ADS profile.

On Linux, ADS Python can require an X display even for a no-GUI quickstart. Set
`DISPLAY` to the intended isolated display before running it.

## Documentation commands

The fast local index is immediately queryable. Full enrichment converts the
installed HTML into private per-version Markdown and updates the local SQLite
index:

```console
ads-agent docs ensure
ads-agent docs build --background
ads-agent docs status
ads-agent docs query "keysight.ads.de workspace" --limit 5
```

Use `--ads INSTANCE_ID` to bind a docs command to a non-default installation.

## Portable Docs Skill

`setup` installs the `ads-kb-docs` skill only when the target directory is
free. It can also be managed explicitly:

```console
ads-agent skill status docs
ads-agent skill install docs
ads-agent skill uninstall docs
```

## Managed sessions

```console
ads-agent launch --workspace PATH [--ads INSTANCE_ID] [--slot SLOT] [--display DISPLAY] [--reuse-existing]
ads-agent status [--slot SLOT]
ads-agent disconnect [--slot SLOT]
ads-agent shutdown [--slot SLOT]
```

`--reuse-existing` succeeds only when the selected ADS installation matches
and no workspace or the same workspace is already active. It does not close or
force-switch another workspace.

For pre-bridge native dialogs, use the PID- and fingerprint-bound Host UI lane:

```console
ads-agent host-ui snapshot --slot SLOT --image-out dialog.png
ads-agent host-ui action --slot SLOT --window-id ID --fingerprint SHA256 (--click X Y|--close) ...
```

For dialogs visible through the embedded Qt bridge:

```console
ads-agent bridge dialog-watch --slot SLOT --timeout 3600
ads-agent bridge dialog-snapshot --slot SLOT --image-out dialog.png
```

See [DIALOG_AUTOMATION.md](DIALOG_AUTOMATION.md) before automating a dialog.

## Complete public command surface

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
ads-agent launch --workspace PATH [--ads INSTANCE_ID] [--slot SLOT] [--display DISPLAY] [--reuse-existing]
ads-agent status [--slot SLOT]
ads-agent disconnect [--slot SLOT]
ads-agent shutdown [--slot SLOT]
ads-agent host-ui snapshot --slot SLOT [--window-id ID] [--image-out PATH]
ads-agent host-ui action --slot SLOT --window-id ID --fingerprint SHA256 (--click X Y|--close) ...
ads-agent examples list
ads-agent examples show NAME
ads-agent examples run NAME [--ads INSTANCE_ID] [--slot SLOT]
ads-agent skill status|install|uninstall docs
ads-agent addon status
ads-agent bridge sessions
ads-agent bridge runtime-snapshot --slot SLOT --profile de [--detail compact|full]
ads-agent bridge context-list --slot SLOT --profile de
ads-agent bridge context-get CONTEXT_OR_HANDLE --slot SLOT --profile de
```

Arbitrary embedded Python and dynamic AEL calls are disabled unless ADS is
launched with `ADS_AGENT_UNSAFE=1` and the client command also includes
`--unsafe`.

## Remove the integration

```console
ads-agent addon uninstall
```

The installer preserves unrelated add-ons and creates timestamped XML backups
before changing an existing ADS configuration.
