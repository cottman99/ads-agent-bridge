# Dialog automation contract

ADS workflows may block on native or Qt modal dialogs even when the preferred
Python or AEL API is used. A client Agent must therefore supervise long-running
GUI work instead of assuming that API calls are sufficient.

## Observation escalation

Use the strongest available observation channel in this order:

1. the embedded Qt object tree when the authenticated bridge is reachable;
2. the host operating system's accessibility tree for native or
   separate-process windows;
3. a target-window screenshot and Agent vision when semantic controls are
   incomplete;
4. user intervention only when identity, intent, or effect remains uncertain.

The connected bridge commands implement the first channel and targeted Qt
image capture. The Session Manager also implements a bounded host-image/action
channel for license, crash, or first-run dialogs that appear before the
embedded bridge starts. A capable client Agent supplies vision and semantic
judgment; operating-system accessibility remains the preferred extra source
when the vendor Qt build exposes it. The live gate exercised the connected Qt
route and the separate-process ADS product-selection route on both Windows and
Linux; unit tests alone are not accepted as proof of this coverage.

When a nonce-bound Linux ADS process outlives the short `ads` wrapper but no
authenticated bridge is reachable, `ads-agent status` reports
`waiting-for-host-ui`. Its `host_ui` object binds the handoff to the exact slot,
display, workspace, primary ADS processes, and nonce-bearing candidate host
processes. Separate-process UI helpers may appear in the candidate inventory,
but they are observation-only and never prove ADS ownership. This state is not an
orphan and must not be retried as a second launch. The host Agent may inspect
accessibility or a target-window image, but a license selection remains a
policy decision: act automatically only when an explicit workflow preference
identifies the exact product; otherwise request confirmation.

For the targeted host-image lane:

```console
ads-agent host-ui snapshot --slot SLOT --image-out host-window.png
ads-agent host-ui action --slot SLOT --window-id WINDOW --fingerprint FINGERPRINT \
  --click X Y --risk medium --authorization workflow-policy \
  --reason "Select the explicitly configured product"
```

The image contains only one nonce-bound candidate window. The click is
client-relative and is rejected when the session state, candidate PID, window
identity, geometry, coordinate space, fingerprint, visibility, bounds, risk,
or authorization no longer matches. On Windows the CLI enters a per-monitor
DPI-aware context before reading geometry, capturing, or posting input, so
User32, Pillow, and the target share physical client pixels even on a mixed-DPI
desktop. There are no product-name, title-to-button, row, or absolute-coordinate
rules in the package. The Agent must take a new snapshot after every meaningful
UI transition and verify the expected effect.

## Two independent lanes

Run the intended ADS operation on the work lane. Run `dialog-watch` on a
separate client lane so a modal event can still be observed while the work lane
is waiting:

```console
ads-agent bridge dialog-watch --slot SLOT --timeout 3600
ads-agent bridge dialog-snapshot --slot SLOT --image-out dialog.png
ads-agent bridge dialog-action --slot SLOT \
  --fingerprint FINGERPRINT --button-id BUTTON_ID \
  --risk low --authorization automatic \
  --reason "Acknowledge an informational completion message"
```

The embedded bridge remains standard-library-only apart from the Qt runtime ADS
already provides. The same in-process Qt observation path works on Windows and
Linux. A targeted Qt screenshot is optional and exists for Agent vision when
labels, accessibility names, standard buttons, and button roles are
insufficient.

## Decision loop

For every detected dialog, the client Agent must:

1. inspect structured title, label, button, role, enabled state, and geometry;
2. request a targeted screenshot only when structured semantics are ambiguous;
3. infer the dialog's effect in the context of the active workflow;
4. select a button and declare risk, authorization, and reason;
5. schedule an action against the exact dialog fingerprint and button ID; the
   Qt callback re-reads and revalidates that same identity immediately before
   clicking;
6. verify that the dialog disappeared or changed as expected;
7. verify that the original workflow resumed or returned a meaningful failure.

An action is rejected if the dialog changed either before scheduling or before
actual actuation, the target is not visible and enabled, the declared risk is
below Qt's semantic risk floor, or the authorization is insufficient. The last
actuation result is observable through bridge status. There are no
title-specific rules and no absolute-coordinate actions in the embedded bridge.
For native ADS dialogs that rebuild button wrappers during semantic inspection,
the callback reacquires the fingerprinted index and rechecks its raw identity
while retaining the fresh Qt ownership scope through `click()`.

## Default autonomy policy

The client Agent may act automatically when it can explain the effect and the
action is low-risk, such as acknowledging information, closing a completed
notification, or cancelling an operation before it mutates state.

Medium-risk actions require an explicit workflow policy or user confirmation.
Examples include saving an Agent-owned workspace, applying a recoverable
configuration change, answering No/No-to-all, or retrying a costly operation.
Qt `NoRole`, standard `No`, and standard `NoToAll` impose this floor even when
the visible label is ambiguous.

High-risk actions require user confirmation. This includes discard, overwrite,
delete, accepting legal or license terms, supplying credentials, changing
security boundaries, acting in a user-owned session, or any outcome the Agent
cannot bound and verify. Qt destructive roles and the standard Discard button
automatically impose a high-risk floor.

When the Agent cannot identify the dialog, cannot capture trustworthy context,
or cannot verify the expected postcondition, it must leave the dialog intact
and report the exact snapshot and stop reason.

## Product boundary

The bridge supplies cross-platform in-process observation, bounded host-window
inventory, targeted image capture, actuation-time fingerprint-bound clicking,
native close, and independent watching. The client Agent supplies optional
host accessibility, vision, workflow context, semantic judgment, and
authorization. This separation allows Codex Computer Use or another capable
Agent to interpret opaque and pre-bridge dialogs without embedding a model,
vendor-specific title list, or fragile click script inside the package.
