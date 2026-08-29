---
name: ads-kb-docs
description: "Retrieve private local Keysight ADS documentation by selecting a configured ADS installation. Use for documentation-only ADS API lookup, Python/AEL/DDS symbol searches, examples, local help source locations, execution-route research, and version-matched documentation questions. Route setup, quickstart, live DE/DDS inspection, ADS_CONTEXT, dialogs, session lifecycle, and runtime validation to ads-agent-bridge. Do not mutate ADS designs or claim that documentation lookup proves a live workflow."
---

# ADS KB Docs

Use Runtime typed operations `docs.status`, `docs.query`, and `docs.get` as the
normal documentation path. The selected ADS adapter keeps each installed
version's index separate and never uploads or redistributes Keysight
documentation. The local `ads-agent docs` commands remain setup and direct
diagnostic interfaces, not the normal Agent transport.

For setup, a disposable execution proof, live DE/DDS state, an `ADS_CONTEXT`
handle, dialog handling, or session lifetime, use `$ads-agent-bridge`. A pure
documentation request stays in this skill and must not launch ADS.

## Preflight

For a conceptual question about how to choose Python, AEL, or UI routes, use the Execution Route Policy below directly; do not call the CLI merely to restate that policy. If a structured answer requires a source reference, use the stable identifier `ads-policy:execution-route/v1`; never expose the installed skill path.

For setup or diagnosis, the equivalent read-only CLI check is:

```text
ads-agent doctor --no-ping
```

If no default ADS instance is configured, run `ads-agent setup`. When several versions are installed, require an explicit user selection; never silently prefer the newest version.

## Query

Query the configured installation through one Runtime submission. Select the
documentation domain explicitly for API work. The equivalent direct CLI is:

```text
ads-agent docs query "<technical query>" --domain python --limit 6
```

For a non-default installation, obtain its id from `ads-agent instances list`, then add `--ads <instance-id>`.

Treat `product_version`, `instance_id`, `source_ref`, `source_kind`, `validation_status`, and `search_mode` as evidence. Prefer `api_reference` and `official_example` results over `guide` results. A guide marked `docs_backed_unverified` is context, not authority for an executable symbol.

The query response already contains bounded snippets and per-term matched
sections. If they are insufficient, expand exactly one result through Runtime
`docs.get`. The equivalent direct CLI is:

```text
ads-agent docs get <source-ref> --ads <instance-id> --focus "<symbol-or-topic>" --max-chars 4000
```

For runnable code, treat every constructed or passed API object as a dependency.
Do not infer a constructor, factory, receiver, or argument order from a class
name, link label, or summary sentence. Expand an authoritative reference until
the full signature for each required dependency is visible. If the query budget
cannot establish that signature, return the boundary instead of guessing code.

One retrieval round is one `docs query` followed, when needed, by at most one
`docs get` for a result from that query. The follow-up `get` belongs to the same
round; it is not a second round. Do not open raw ADS HTML, cached Markdown,
package files, another skill tree, or scan the user's home directory. Do not
reconstruct a private file path from `relative_path`. Use at most three such
focused rounds; if the evidence is still insufficient, report the exact
boundary and next verification step.

For a capability-boundary question that explicitly asks for a fallback, reserve one of those three rounds for the next execution route. After at most two focused Python rounds, query the exact capability or known function name in `--domain ads` for a documented AEL route before proposing UI automation. A missing Python result is not runtime proof.

## Execution Route Policy

For an ADS automation capability, prefer these routes in order:

1. Public Python API, when the selected ADS version's API reference or official example supplies a credible symbol and signature.
2. AEL bridge, only when the Python route is absent or inadequate and the exact AEL function and calling contract are documented or otherwise verified.
3. Observable UI automation, only when neither API route can perform the task and the target window, context, action risk, and expected outcome are bounded.

Do not fall back merely because the first attempt failed. First distinguish a wrong symbol/signature, version mismatch, unavailable runtime, missing authorization, and an unsupported capability. Stop instead of acting when target context, callable identity, authorization, or outcome evidence cannot be established.

## Index Lifecycle

Run the fast idempotent bootstrap when the selected installation or docs changed:

```text
ads-agent docs ensure --ads <instance-id>
```

Build searchable Markdown and enrich the local SQLite index in the background when full-text retrieval is useful:

```text
ads-agent docs build --ads <instance-id> --background
ads-agent docs status --ads <instance-id>
```

The first query can still use the fast index and a local source fallback while enrichment is incomplete.

## Optional Agent Kit Enhancement

If `ADS_DOC_REPO` points to a full `keysight-ads-agent-kit` checkout, prefer its profile-aware query tool for curated support boundaries, migration mappings, pitfalls, and topic packs. Use the public `ads-agent` CLI for installation discovery and version selection; do not assume a fixed `u1`, `u2`, or latest-version path.

## Evidence Boundary

- Documentation results prove only that a local installed source matched the query.
- A readable dataset is not interpreted simulation evidence.
- A documented API is not proof that the selected ADS runtime exposes or successfully executes it.
- For live DE/DDS, headless simulation, or AEL execution, route to `$ads-agent-bridge` and require a separate runtime acceptance gate.
