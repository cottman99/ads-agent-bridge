---
name: ads-agent-bridge
description: "Operate and inspect local Keysight ADS through the installed ads-agent Bridge. Use for Bridge setup and diagnosis, explicit ADS instance selection, disposable quickstarts, workspace-bound launch and status, live DE/DDS runtime snapshots, ADS_CONTEXT handles, bounded dialog handling, headless examples, disconnect, and safe shutdown. Route documentation-only API, Python, AEL, DDS, and version questions to ads-kb-docs."
---

# ADS Agent Bridge

Use the local `ads-agent` CLI as the stable public interface. Keep ADS, session
tokens, workspaces, and private documentation on the ADS host. When operating
remotely, run the CLI on that host through SSH; do not expose or forward the
embedded loopback endpoint.

The Agent-facing Skill and generic Runtime MCP server belong on the Agent host.
This Bridge and `ads-agent runtime serve` belong on the ADS host. A host that
runs both roles should use a local Runtime connection, not bypass the common
request and Run contracts.

## Route the request

- For a documentation-only question, use `$ads-kb-docs`. Do not launch ADS to
  answer a question that local documentation can answer.
- For installation, runtime inspection, a disposable proof, or a live ADS/DDS
  target, continue with this skill.
- For a combined task, use `$ads-kb-docs` to establish a version-matched API or
  AEL route, then use this skill for a separate runtime acceptance gate.

## Establish identity before acting

Start with read-only discovery:

```text
ads-agent doctor --no-ping
ads-agent instances list
```

Run `ads-agent setup` only when setup or repair is within the request. When
several installations exist, require an explicit instance; never select the
newest implicitly.

For every live operation preserve these identities:

```text
ADS instance + workspace + slot + profile (de|dds)
```

DE and DDS are independent runtimes. DE evidence is not DDS evidence. Refuse a
workspace or ADS-root mismatch instead of switching an existing session.
Launching a DE workspace neither launches nor proves a DDS runtime. If a task
uses DDS, observe the exact DDS profile independently and stop if it is absent;
do not invent a DDS launch or infer it from DE readiness.

## Choose one public lane

### Disposable no-GUI proof

Before relying on automation for a real project, prefer the maintained
disposable gate:

```text
ads-agent quickstart --ads <instance-id>
```

Use `ads-agent examples list` and `ads-agent examples show <name>` before an
example. Run only the named example and honor its prerequisites, state changes,
evidence, and stop rule.

### Workspace-bound live ADS

Launch only an existing, explicit workspace:

```text
ads-agent --pretty launch --ads <instance-id> --workspace <path> --slot <slot>
ads-agent --pretty bridge runtime-snapshot --slot <slot> --profile de
```

On Linux, add the intended `--display`. Use `--reuse-existing` only when the
Bridge confirms the same ADS installation and either no workspace or the same
workspace. Prefer one compact runtime snapshot over several broad probes. Use
`--detail full` only when bounded window or DDS-file inventories are needed.

### Explicit ADS or DDS context

Use a user-copied `EDA_CONTEXT:v1:...` handle instead of guessing the foreground
window or selection:

```text
ads-agent bridge context-get <handle> --slot <slot> --profile <de|dds>
ads-agent bridge context-refresh <handle> --slot <slot> --profile <de|dds>
```

A context identifies a target; it does not authorize opening, editing,
simulating, closing, or replaying selected objects. Stop when the handle is
stale, belongs to another slot/profile, or cannot establish the exact target.
Do not launch a replacement session merely to make a copied handle resolve;
first establish the handle's intended existing slot and profile.

For repeated remote operations, use the generic Runtime's persistent SSH stdio
transport with `ads-agent runtime serve` on the ADS host. Do not open a new SSH
process for each Bridge command. Every agent-originated Runtime request must
carry a concise `purpose`; the Runtime supplies available actor and host metadata
and records observed timings automatically. Legacy `ADS_CONTEXT:v1` handles
remain accepted for compatibility, but the Add-on copies `EDA_CONTEXT:v1`.

### Blocking dialogs

Inspect before acting. Use the embedded dialog lane after the Bridge is ready,
or the Host UI lane only for one nonce-bound pre-bridge window. Require a fresh
fingerprint, bounded risk, explicit authorization class, and an expected
outcome. Never use a title-only rule, blind coordinate, stale screenshot, or
opaque high-risk action.

## Preserve safety boundaries

- Treat `declared`, `compatible`, `available`, `healthy`, and `authorized` as
  separate capability states.
- Do not enable arbitrary embedded Python or dynamic AEL unless the user
  explicitly requests that unsafe route and both process and client opt in.
- Do not infer permission from documentation, a context handle, session
  ownership, or capability availability.
- Never force-kill ADS, discard modified work, or close a user-owned or
  unverified session.
- Stop on ambiguous instance/workspace identity, stale context, unresolved
  modal state, unavailable capability, missing authorization, or unverifiable
  outcome.

## Finish with evidence and the right lifetime action

Read back the exact runtime state or artifact required by the task. A runtime
snapshot proves bounded live state at its capture time; it does not prove a
later mutation succeeded. A readable dataset is not interpreted engineering
evidence by itself.

Use the requested lifetime action:

```text
ads-agent disconnect --slot <slot>  # leave ADS running
ads-agent shutdown --slot <slot>    # native safe exit, agent-owned only
```

Report the selected instance, workspace, slot, profile, observed evidence, and
any boundary that remains unverified.
