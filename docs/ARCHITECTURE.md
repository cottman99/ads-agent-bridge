# Architecture and capability growth

ADS Agent Bridge connects an Agent to one exact ADS installation and Context.
It discovers the installation, retrieves version-matched documentation, selects
the correct official Python/AEL runtime, manages workspace and session
lifecycle, and returns checked evidence.

It is not a replacement schematic, layout, DDS, or solver API. The official ADS
APIs remain the functional surface. The Bridge supplies a governed execution
and verification envelope around them.

## Capability route

```text
natural-language task
  -> exact ADS Context and version-matched docs
  -> matching bootstrap experience and anti-pattern assets
  -> matching asset-bound compiled shortcut, when eligible
     OR governed official Python/AEL batch
  -> workspace staging and lifecycle
  -> readback, artifact validation, and evidence
```

The shared coverage definitions and promotion rules are maintained in the
[EDA Runtime capability model](https://github.com/cottman99/eda-bridge-runtime/blob/main/docs/CAPABILITY_MODEL.md).

## Product boundary

Bridge infrastructure owns installation, profile, slot, display, workspace,
selection Context, session ownership, dialog safety, transport, runtime
selection, staging, fingerprints, retries, and evidence normalization.

For multi-turn governed work, a successful native batch returns an opaque
content-bound continuation Context. Its private ADS-host record binds the exact
target identity and source fingerprint; the next batch may reuse those facts
but not prior authority, effect, write scope, program, idempotency, or
validation. See [Content-bound continuation Context](CONTINUATION_CONTEXT.md).

Generic native execution owns the controlled invocation of documented ADS
Python or AEL. It must declare Context, effect scope, timeout, artifacts, and
validation; it is not an unrestricted shell.

Certified workflows such as schematic construction, circuit simulation, DDS
creation, and generated-input Momentum solving remain useful, maintained
shortcuts. Their experience asset is semantic truth; implementation code is a
compiled command-group cache for lower token cost and fewer transcription
errors. A shortcut is preferred only while asset id/version/hash,
applicability, runtime probe, parameters, and validation match. They do not
define the outer boundary of ADS functionality and must
not grow into a second ADS API one component or plot type at a time.

The wheel carries the independent Bootstrap Experience Library. The read-only
`experience.list/get` gateway makes it reachable across local or SSH
deployments. Missing or corrupt assets lower Agent guidance quality but never
block docs, Context, sessions, or governed native execution. The Bridge records
the caller's purpose and execution facts; it does not infer engineering intent,
learn from receipts, or rewrite experience.

GUI automation is a bounded fallback for genuinely API-inaccessible UI, not the
primary expansion route.
