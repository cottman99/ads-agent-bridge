# Background native workflows

Use this reference only after the task has selected the isolated background
lane. The normal Agent path is Runtime, not direct shell or CLI orchestration.

For a non-existing workspace, call `workspace.create`. It returns an
`eda_context`, a portable opaque continuation, and a short host-local
`continuation_ref`. Pass the short reference as
`payload.continuation_context` in the first `native.execute`; do not inspect or
recopy the long token. Declare a distinct output workspace and keep the source
unchanged.

The native plan must bound read/write paths, ADS runtime, program, artifacts,
limits, and validation. A mutation also needs a concrete `expected_effect` and
stable task-specific `idempotency_key`. Reuse the same key only for a retry of
the same intended effect.

Validate in a fresh process or by the workflow's explicit artifact assertions.
Retain source/output fingerprints, native-call evidence, dataset or generated
artifact identity, and validation result. A successful process exit without
the expected design or artifact is not success.

Direct CLI quickstart is an administrator acceptance gate, not the Agent route:

```text
ads-agent quickstart --ads <instance-id>
ads-agent examples list
ads-agent examples show <name>
```

Run only the named example and honor its prerequisites, state changes,
evidence, and stop rule.
