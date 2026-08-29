# ADS Context interaction contract

The context subsystem gives a client Agent an explicit, copyable reference to
the ADS object or selection the user meant. It does not grant permission to
edit, simulate, open, close, or otherwise mutate that target.

## User interaction

After `ads-agent setup` installs the add-on and ADS is restarted:

- a schematic, layout, or symbol window provides **Copy ADS Context** in its
  right-click menu and under **Tools > ADS Context**;
- the Folder/Library workspace tree provides **Copy ADS Context** when at least
  one supported item is selected;
- a DDS window provides **Copy ADS Context** in its right-click menu, including
  when no trace or annotation is selected, and in its top-level **ADS Context**
  menu.

The action copies a bounded `EDA_CONTEXT:v2:...` snapshot to the system
clipboard. It includes origin, session/Display, target, bounded selection,
capability digest, and freshness so an Agent can submit a known operation
without rediscovering them. Legacy `ADS_CONTEXT:v1` remains accepted. The
action is non-modal: success and failure are written to the ADS Python console
instead of opening another dialog.

## Meaning of the handle

The bridge retains a bounded in-process registry of at most 64 contexts. Each
public envelope contains:

- source profile and surface (`de`/`dds`, design window, workspace tree, or DDS
  window);
- stable target identity where ADS exposes one;
- a bounded selection summary of at most 50 items;
- slot, process, profile, and freshness generation;
- capability states and an explicit `authorization_required` marker.

The snapshot contains neither the bridge token nor its localhost port. It is a
durable reference to a captured context, not proof that the live ADS object is
still open. `context-refresh` rechecks the retained live object; it never opens
another design, workspace, or DDS file to make a stale reference appear live.
The bridge validates the slot and profile encoded in a handle before resolving
its context id, so a coincidentally identical process-local id in another ADS
session cannot be addressed through the wrong handle.

For sized ADS collections, `selection.count` is exact and
`selection.count_is_exact` is `true`. For a generic iterator, the bridge reads
at most 51 values: it emits at most 50 item summaries and, if another value was
observed, reports the count as a lower bound with `count_is_exact: false` and
`truncated: true`. This makes the serialization bound an execution bound too.

## DE and DDS boundaries

DE and DDS use separate add-on entrypoints and callback lifecycles. DDS does
not export DE's `generate_menu` hook. Shutdown unregisters DE popup callbacks
and DDS window/popup callback handles before the bridge releases its registry.
DDS owns a top-level menu rather than modifying ADS's dynamically rebuilt
**Tools** menu; this keeps the action inside the documented DDS window-callback
lifecycle.

A `.dds` item selected in the DE workspace tree is a `dds-file-ref`. Only an
action inside an open DDS window produces a live `dds-file` or `dds-page`
context. Multiple workspace-tree items form a `context-set` rather than being
silently reduced to one target.

## Client commands

These commands are safe, authenticated bridge reads or local registry
maintenance operations; none enables arbitrary embedded Python:

```console
ads-agent bridge context-capabilities --slot SLOT --profile de
ads-agent bridge context-list --slot SLOT --profile de
ads-agent bridge context-get CONTEXT_OR_HANDLE --slot SLOT --profile de
ads-agent bridge context-refresh CONTEXT_OR_HANDLE --slot SLOT --profile de
ads-agent bridge context-drop CONTEXT_OR_HANDLE --slot SLOT --profile de
```

Use `--profile dds` for a context captured in DDS. Contexts are process-local
and disappear when that ADS profile exits or its add-on is shut down.

## First-release limits

The initial contract intentionally does not infer an action from a selection,
does not click menus on behalf of the user, and does not persist live Python
objects across ADS restarts. Future open/edit/simulate workflows must resolve
the envelope, check freshness, and obtain the authorization stated by the
workflow before acting.
