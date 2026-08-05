---
name: ads-kb-docs
description: "Retrieve private local Keysight ADS documentation by automatically selecting a configured ADS installation. Use for ADS API lookup, Python/AEL symbol searches, examples, local help source locations, and version-matched documentation questions. Do not mutate ADS designs or claim that documentation lookup proves a live automation workflow."
---

# ADS KB Docs

Use the local `ads-agent` command as the portable documentation backend. It discovers installed ADS versions, keeps each version's index separate, and never uploads or redistributes Keysight documentation.

## Preflight

Run the read-only check first:

```text
ads-agent doctor --no-ping
```

If no default ADS instance is configured, run `ads-agent setup`. When several versions are installed, require an explicit user selection; never silently prefer the newest version.

## Query

Query the configured default installation:

```text
ads-agent docs query "<technical query>" --limit 10
```

For a non-default installation, obtain its id from `ads-agent instances list`, then add `--ads <instance-id>`.

Treat `product_version`, `instance_id`, `source_path`, and `search_mode` in the JSON result as evidence. Open only the few returned local source files needed to answer the question.

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
- For live DE/DDS, headless simulation, or AEL execution, route to the corresponding control workflow and require its own acceptance gates.
