# Agent Execution Context Contract

Status: draft for the next alpha compatibility release.

## Boundary

The bridge owns live ADS runtime facts. It does not own Agent planning,
workflow policy, engineering memory, or operation evidence.

The bridge publishes two standard-library-only contracts:

- `bridge-runtime-snapshot/v1`: one bounded, revision-aware view of one
  `slot + profile` runtime;
- `bridge-capability-descriptor/v1`: machine-readable command meaning and
  current runtime state.

An Agent capability system such as `keysight-ads-agent-kit` may compose those
records with knowledge, routing, authorization, and evidence to form its own
execution context. The public bridge never imports or governs that system.

Schemas:

- `schemas/ads-continuation-state-v1.schema.json`
- `schemas/bridge-runtime-snapshot-v1.schema.json`
- `schemas/bridge-capability-descriptor-v1.schema.json`

The runtime snapshot describes bounded live state. Separately, governed
`native.batch` returns a private-host-backed continuation Context after a
successful content fingerprint has been observed. The opaque handle lets a
later batch materialize exact identity and content-state fields without making
the token an authority or exposing the bound workspace/fingerprint in it. See
[`CONTINUATION_CONTEXT.md`](CONTINUATION_CONTEXT.md).

## Fast path

The default preflight is one targeted request:

```console
ads-agent --pretty bridge runtime-snapshot --slot <slot> --profile de
```

The compact result includes runtime identity, workspace state, bounded UI
state, the newest context summary, per-command dynamic state, and safe next
actions. It does not include screenshots, full design exports, solver artifact
scans, or unbounded object traversal.

Callers retain `state_revision`. A later request can suppress unchanged state:

```console
ads-agent --pretty bridge runtime-snapshot \
  --slot <slot> --profile de --since-revision <revision>
```

When the relevant bounded state has not changed, the bridge returns
`changed=false` with identity and revision only. The revision is a state
fingerprint, not a global event counter and not durable evidence.

Use `--detail full` only when bounded top-level window and DDS file inventories
are needed. Full still does not mean arbitrary ADS database serialization.

## Capability state

Every descriptor separates five questions:

1. `declared`: the installed bridge defines the operation;
2. `compatible`: the current profile and probed ADS runtime expose its required
   primitives;
3. `available`: the immediate runtime preconditions are present;
4. `healthy`: the operation is not currently blocked by a known runtime state;
5. `authorized`: the bridge runtime opt-in required by its safety class is
   satisfied.

`authorized` reports only bridge-local policy. A caller may impose stronger
workflow authorization before sending the request.

Descriptors also publish `safety`, `mutates`, `latency_class`, `requirements`,
`reason`, and bounded `safe_next_actions`. Agents should inspect these fields
instead of learning support through failed arbitrary code execution.

## Profile rule

DE and DDS remain independent runtimes. A DE snapshot is not DDS evidence and
a DDS snapshot is not workspace or solver evidence. A higher-level execution
context must preserve the source profile of every live claim.

## Performance rules

- Select one exact `slot + profile`; do not ping every historical session.
- Prefer one compact snapshot over several status/context/dialog probes.
- Cache static descriptor meaning by schema/package version; refresh dynamic
  descriptor state with the runtime snapshot.
- Request expensive design export, images, and solver evidence only when a
  workflow gate requires them.
- Measure subprocess starts, socket round trips, main-thread dispatches,
  response bytes, and failed-route retries before claiming a speedup.

## Evidence boundary

A snapshot is live readback with a capture time and state fingerprint. It is
not proof that a later mutation succeeded. Workflow evidence, artifact hashes,
and gate outcomes belong to the caller's operation ledger.
