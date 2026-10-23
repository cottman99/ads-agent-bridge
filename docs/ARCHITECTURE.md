# Architecture and capability growth

ADS Agent Bridge connects an Agent to one exact ADS installation and Context.
It discovers the installation, retrieves version-matched documentation, selects
the correct official Python/AEL runtime, manages workspace and session
lifecycle, and returns checked evidence.

It is not a replacement schematic, layout, DDS, or solver API. The official ADS
APIs remain the functional surface. The Bridge supplies a governed execution
and verification envelope around them.

## Shared semantic route

The common experience, documentation, implementation-discovery, and native
fallback order is defined once in the
[EDA Runtime capability model](https://github.com/cottman99/eda-bridge-runtime/blob/main/docs/CAPABILITY_MODEL.md).
This Bridge contributes only ADS-specific contracts: installation/profile,
DE/DDS session identity, workspace lifecycle, official Python/AEL execution,
and ADS readback. Its ordinary operation catalogue omits certified workflows;
an exact `experience.get` result supplies a compiled implementation binding when
that asset owns one.
When version, profile, and primary operation are exact, the same call resolves
one unique metadata match directly; zero or multiple matches fail explicitly.
This removes an index-listing turn without making the Bridge choose engineering
semantics.

## Product boundary

Bridge infrastructure owns installation, profile, slot, display, workspace,
selection Context, session ownership, dialog safety, transport, runtime
selection, staging, fingerprints, retries, and evidence normalization.

For multi-turn governed work, a successful native program returns an opaque
content-bound continuation Context. Its private ADS-host record binds the exact
target identity and source fingerprint; the next batch may reuse those facts
but not prior authority, effect, write scope, program, idempotency, or
validation. See [Content-bound continuation Context](CONTINUATION_CONTEXT.md).

Generic native execution owns the controlled invocation of documented ADS
Python or AEL. It must declare Context, effect scope, timeout, artifacts, and
validation; it is not an unrestricted shell.

Certified workflows such as schematic construction, circuit simulation, DDS
creation, and generated-input Momentum solving remain compatible shortcuts.
Their experience asset is semantic truth; implementation code is a compiled
command-group cache. A shortcut is selected only when the applicable experience
references it, its binding and validation match, and same-task evidence shows a
concrete latency, reliability, or token benefit. They do not define the outer
boundary of ADS functionality and must
not grow into a second ADS API one component or plot type at a time.

Operation descriptors are deterministic request and safety contracts. They are
not a catalogue of everything ADS can do. Official ADS Python/AEL reach plus the
governed execution envelope is the capability backbone.

## Live and background lanes

A Context copied from the ADS GUI defaults to the same open DE or DDS session.
The Agent controls it through official internal APIs and the user sees changes
immediately; no mouse automation is implied. An independent background
workspace is reserved for explicit non-interference, long-running or high-risk
work, or a proven live-API limitation. The lanes never write one workspace at
the same time and meet only at explicit save, reload, ownership-transfer, or
promotion boundaries.

The wheel carries the independent Bootstrap Experience Library. The read-only
`experience.list/get` gateway makes it reachable across local or SSH
deployments. Missing or corrupt assets lower Agent guidance quality but never
block docs, Context, sessions, or governed native execution. The Bridge records
the caller's purpose and execution facts; it does not infer engineering intent,
learn from receipts, or rewrite experience.

GUI automation is a bounded fallback for genuinely API-inaccessible UI, not the
primary expansion route.
