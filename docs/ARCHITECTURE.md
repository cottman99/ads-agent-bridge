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
  -> matching certified workflow, when one exists
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

Generic native execution owns the controlled invocation of documented ADS
Python or AEL. It must declare Context, effect scope, timeout, artifacts, and
validation; it is not an unrestricted shell.

Certified workflows such as schematic construction, circuit simulation, DDS
creation, and generated-input Momentum solving remain useful, maintained
shortcuts. They do not define the outer boundary of ADS functionality and must
not grow into a second ADS API one component or plot type at a time.

GUI automation is a bounded fallback for genuinely API-inaccessible UI, not the
primary expansion route.
