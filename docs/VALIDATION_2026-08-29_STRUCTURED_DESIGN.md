# Structured ADS design transaction validation

Date: 2026-08-29

## Contract under test

The public `design.apply` Runtime operation accepted one
`ads.design-plan/v1` object. The plan named only registered `add_instance` and
`add_wire` operations, exact pre-state, and fresh-reopen assertions. It did not
contain Python, AEL, shell, GUI actions, simulation, or customer data.

The Bridge copied a closed disposable source workspace to staging, executed one
ADS database transaction on the copy, saved and closed it, freshly reopened the
design, checked the persisted result, verified the source Bundle fingerprint
was unchanged, and atomically promoted the output workspace.

## Real acceptance

- Product: ADS 2026 Update 2.1 on Linux
- Display: `:4.0`
- Path: local Agent -> EDA Bridge Runtime -> persistent SSH stdio -> ADS Agent Bridge
- Runtime calls: 3 of 3 passed (`capabilities`, `workspace.create`, `design.apply`)
- Persisted design: 3 exact instance names after fresh reopen
- Assertions: 7 of 7 passed across instance names, two parameter values, and
  required netlist text
- Source preservation: passed
- Output promotion: passed
- Solve: not run

The normalized evaluation measured 43.409 s end to end. Runtime transport,
including SSH and Bridge work, totalled 2.640 s (6.082%); 40.769 s remained on
the Agent/client side. These figures are one bounded acceptance sample, not a
latency guarantee.

## Failure and cleanup gates

Synthetic tests prove that unknown operations and raw-code-shaped plans are
rejected, an execution failure leaves no output, staging is removed, and the
source fingerprint is preserved. The two disposable real workspaces contained
no customer data and were removed after their resolved paths were verified
inside the dedicated evaluation root.
