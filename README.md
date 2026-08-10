<p align="center">
  <strong>English</strong> · <a href="README.zh-CN.md">简体中文</a>
</p>

# ADS Agent Bridge

<p align="center">
  <strong>Give AI agents a safe, local, and version-aware way to understand and operate Keysight ADS.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/ads-agent-bridge/"><img alt="PyPI" src="https://img.shields.io/pypi/v/ads-agent-bridge"></a>
  <a href="https://pypi.org/project/ads-agent-bridge/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/ads-agent-bridge"></a>
  <a href="https://github.com/cottman99/ads-agent-bridge/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/cottman99/ads-agent-bridge/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/cottman99/ads-agent-bridge"></a>
</p>

![ADS Agent Bridge connects a general-purpose Agent to a bounded local EDA environment](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/ads-agent-bridge-hero.png)

ADS Agent Bridge is an unofficial, local-first documentation and automation
bridge for Keysight Advanced Design System (ADS). It turns the ADS installation
already on your machine into a version-aware documentation source, a bounded
runtime context, and a safely managed automation target for general-purpose
Agents such as Codex or OpenCode.

The Agent may run on the ADS host or execute `ads-agent` there over SSH. Live
bridge endpoints remain bound to loopback on the ADS host; the package does not
open ADS directly to the network.

> [!IMPORTANT]
> This project is a public alpha. Use disposable workspaces for first trials
> and review the reported capability gates before relying on automation
> results. Keysight and ADS are trademarks of Keysight Technologies. This
> project is not affiliated with or endorsed by Keysight.

## What it does

| Capability | What the Agent gets |
| --- | --- |
| ADS discovery | Finds installed ADS versions, selects one explicitly, and probes runtime capabilities instead of assuming the newest version. |
| Private local docs | Builds a version-scoped index and Markdown cache from documentation already installed on the user's machine. Vendor documentation is never redistributed. |
| Verified quickstart | Creates a disposable workspace, runs a minimal AC simulation, and reads the resulting dataset through explicit acceptance gates. |
| Managed GUI sessions | Launches an exact workspace, tracks process and display identity, reports UI state, and distinguishes agent-owned from user-owned ADS sessions. |
| Exact DE/DDS context | Adds **Copy ADS Context** to supported menus so an Agent can work from the selected workspace, design, cell, cellview, or DDS target without guessing the foreground window. |
| Bounded UI lifecycle | Observes blocking dialogs, supports identity-checked intervention, disconnects without closing ADS, and requests native safe exit only for a verified agent-owned session. |

The initial release is deliberately small, but it is not a dummy wrapper: docs,
no-GUI automation, live DE/DDS context, dialog supervision, and session
lifecycle are separate, observable capability lanes.

## Quick start

Prerequisites:

- a locally licensed ADS installation;
- Python 3.10 or later for the `ads-agent` command;
- Windows or Linux.

Install and prove the local setup:

```console
pipx install ads-agent-bridge
ads-agent doctor
ads-agent setup
ads-agent quickstart
```

`setup` discovers installed ADS versions instead of hard-coding one release.
`quickstart` passes only after documentation indexing and query, add-on
registration, disposable workspace creation, circuit simulation, and dataset
readback all pass.

Launch a real workspace only after that gate succeeds:

```console
ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk
ads-agent --pretty status
ads-agent disconnect                 # ADS keeps running
ads-agent shutdown                   # native exit for an agent-owned session
```

On Linux, bind GUI work to the intended display:

```console
ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk --display :4
```

<details>
<summary><strong>Bootstrap installation when pipx or a suitable Python is missing</strong></summary>

### Linux

```console
curl -fsSLO https://github.com/cottman99/ads-agent-bridge/releases/download/v0.1.0a28/install.sh
sh install.sh
```

### Windows PowerShell

```powershell
Invoke-WebRequest https://github.com/cottman99/ads-agent-bridge/releases/download/v0.1.0a28/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The bootstrap searches installed Python versions, can create an isolated pipx
environment, and does not modify an externally managed system Python. See the
[CLI and installation reference](docs/CLI_REFERENCE.md) for interpreter,
offline-wheel, and check-only options.

</details>

## Remote use over SSH

SSH is the recommended current remote boundary. Run the public CLI on the ADS
host instead of exposing the embedded Bridge port:

```console
ssh ads-host 'ads-agent doctor'
ssh ads-host 'ads-agent --pretty status'
ssh ads-host 'ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk --display :4'
```

This keeps session files, random tokens, process ownership, workspaces, and ADS
itself on the same host. A direct local-client-to-remote-Bridge protocol and
multi-client lease model are not yet part of the public contract.

## How it works

![ADS Agent Bridge architecture showing bidirectional local documentation retrieval, the packaged ADS plug-in, bounded live DE/DDS control, and a separate no-GUI ADS Python lane](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/how-it-works-image2.png)

The package has three main execution lanes:

1. **Knowledge:** the portable Docs Skill routes questions through the CLI to the
   selected installation's private, version-scoped local index, which returns
   matched content and source evidence.
2. **Live ADS:** the Session Manager coordinates the packaged ADS Agent Bridge
   plug-in installed inside DE or DDS. Its loopback, token-authenticated endpoint
   verifies the exact workspace, process, display, slot, profile, and ownership
   identity.
3. **No-GUI automation:** the selected ADS Python runtime creates a disposable
   example, simulates it, and reads the dataset without opening an ADS window.

On Linux, ADS Python can still require an available X display for runtime
initialization. For isolation, keep the real user `HOME` so ADS can see its
per-user state, and isolate Bridge state with `ADS_AGENT_HOME`.

## Safety and privacy

- Documentation, indexes, workspaces, session tokens, and automation results
  remain local unless the user deliberately moves them.
- Bridge endpoints listen on loopback and use a random token per session.
- Reusing a session requires the selected ADS instance and exact workspace to
  match; the Bridge does not silently switch workspaces.
- Context handles identify a target but do not authorize editing or simulation.
- Dialog actions are bound to a fresh process/window fingerprint instead of a
  product title or fixed screen coordinate.
- `shutdown` refuses unverified or user-owned sessions and never force-kills ADS
  or silently discards modified work.
- Arbitrary embedded Python and dynamic AEL calls stay disabled unless both the
  ADS process and the client explicitly opt into unsafe mode.

See the [dialog automation contract](docs/DIALOG_AUTOMATION.md),
[context interaction contract](docs/CONTEXT_INTERACTION.md), and
[execution context contract](docs/EXECUTION_CONTEXT_CONTRACT.md) for the exact
boundaries.

## Version support

| ADS generation | Public support level |
| --- | --- |
| ADS 2025 and later | Stable target, decided by runtime capability probes |
| ADS 2024 Update 2 | Preview |
| ADS 2023 Update 2 through ADS 2024 Update 1 | Experimental |
| Older installations | Documentation-only when local docs can be discovered |

No version is fixed into the portable Docs Skill. Multiple installed versions
can be discovered and selected explicitly.

## Five public examples

```console
ads-agent --pretty examples list
```

The current catalog covers:

1. ADS discovery and explicit version selection;
2. no-GUI minimal-AC simulation and dataset readback;
3. read-only live DE workspace context;
4. bounded DDS dataset readback into a new native DDS file;
5. a fixed read-only AEL workspace call showing the hybrid boundary.

Every runner names its prerequisites, state changes, evidence, and stop rule.
See [EXAMPLES.md](docs/EXAMPLES.md) for exact commands.

## Current boundaries

The project does **not** yet claim a completed Momentum, RFPro, FEM, SIPro, or
PIPro workflow. It also does not provide a public remote Bridge protocol: SSH
execution is supported, while raw port forwarding is not the documented user
path. These areas require their own runtime and solver-side acceptance evidence
before they are promoted as supported capabilities.

## Documentation

- [CLI and installation reference](docs/CLI_REFERENCE.md)
- [Examples and acceptance gates](docs/EXAMPLES.md)
- [Release contract](docs/RELEASE_CONTRACT.md)
- [Session and dialog automation](docs/DIALOG_AUTOMATION.md)
- [DE/DDS context interaction](docs/CONTEXT_INTERACTION.md)
- [Execution context contract](docs/EXECUTION_CONTEXT_CONTRACT.md)
- [Changelog](CHANGELOG.md)

To remove the ADS integration while preserving unrelated add-ons:

```console
ads-agent addon uninstall
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). Public claims are accepted only when the
corresponding test, runtime observation, or validation gate has passed.
