# ADS 2027 Linux HOME isolation validation — 2026-08-11

## Scope

This gate retested the published `0.1.0a27` package against ADS 2027 on a
private Linux EDA server. GUI activity was confined to a dedicated X display.
Bridge configuration, cache, runtime records, workspace, and slot were
isolated; the ordinary Linux user `HOME` was preserved so ADS could read its
existing per-user product and license state.

## Result

1. Setup selected ADS 2027 and found all 9,289 installed documentation files.
2. Quickstart passed documentation indexing and query, add-on registration,
   disposable workspace creation, circuit simulation, and dataset readback.
   The AC dataset contained 31 rows.
3. GUI launch reached `workspace-ready` in about ten seconds on the dedicated
   display. The authenticated DE bridge reported the exact workspace, ADS 2027
   installation, real user home, and one visible ADS main window with no modal
   blocker.
4. `disconnect` left both ADS and the Bridge reachable.
5. Native `shutdown` exited the exact agent-owned process and removed its
   managed and DE/DDS session records.
6. The disposable test root was removed. The existing add-on registrations and
   ADS per-user preference file retained their pre-test locations and timestamp.

## Finding

An earlier run replaced `HOME` as part of test isolation. ADS then entered its
product-selection path and could not reuse the working per-user configuration.
The successful rerun changed the isolation boundary: it preserved the real
ADS user profile and isolated only Bridge-owned state through
`ADS_AGENT_HOME`, together with a unique workspace, slot, and display.

This is an acceptance-harness correction, not evidence of a Bridge session
lifecycle defect or license-server capacity failure. A missing `.eesoflic`
remains advisory because valid installations may supply licensing through
other platform mechanisms.

## Maintained gate

Linux release acceptance must use:

```text
real HOME
+ isolated ADS_AGENT_HOME
+ unique workspace and slot
+ explicit DISPLAY
-> launch -> workspace-ready -> ping
-> disconnect (ADS remains reachable)
-> native shutdown (owned process exits)
```

An alternate `HOME` is reserved for an explicit first-user/product-selection
test and must not be used as the default package-isolation mechanism.
