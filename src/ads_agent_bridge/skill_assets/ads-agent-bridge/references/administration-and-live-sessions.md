# Administration and live sessions

Use this reference only for setup, repair, diagnosis, explicit live launch,
modal dialogs, or session lifetime management.

Start read-only:

```text
ads-agent doctor --no-ping
ads-agent instances list
```

Run `ads-agent setup` only when setup or repair is in scope. With multiple
installations, require an explicit instance.

Launch only an existing explicit workspace:

```text
ads-agent --pretty launch --ads <instance-id> --workspace <path> --slot <slot>
ads-agent --pretty bridge runtime-snapshot --slot <slot> --profile de
```

On Linux, supply the intended display. Use `--reuse-existing` only after the
Bridge confirms the same ADS installation and the same workspace (or no bound
workspace). Prefer one compact runtime snapshot; request full detail only for a
bounded window or DDS-file inventory. Launching DE neither launches nor proves
DDS readiness.

For copied Context:

```text
ads-agent bridge context-get <handle> --slot <slot> --profile <de|dds>
ads-agent bridge context-refresh <handle> --slot <slot> --profile <de|dds>
```

Do not launch a replacement session merely to make a stale or mismatched handle
resolve. Establish the intended existing slot/profile or stop.

For a blocking dialog, inspect first. Use the embedded dialog lane after Bridge
readiness, or the Host UI lane only for one nonce-bound pre-bridge window.
Require a fresh fingerprint, bounded risk, explicit authorization class, and
expected outcome. Never act by title alone, blind coordinate, or stale image.

Finish with the requested lifetime action:

```text
ads-agent disconnect --slot <slot>  # leave ADS running
ads-agent shutdown --slot <slot>    # native safe exit, agent-owned only
```
