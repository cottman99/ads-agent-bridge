# Content-bound continuation Context

`native.batch` returns the existing `EDA_CONTEXT:v2` token after a successful
observe or staged mutation. It does not introduce another handle protocol. The
token contains routing identity, a random private-record id, and only a
non-sensitive content-bound summary. Exact instance, version, profile, optional
`slot + connection + design`, absolute workspace path, and the trusted source
fingerprint remain in a private record on the ADS worker host.

`workspace.create` returns two deliberately different Context roles. Its
`eda_context` remains the general workspace/lifecycle Context. Its
`continuation_context` is already content-bound and may bootstrap the first
`native.batch` without making the Agent rediscover the absolute workspace path,
ADS version, or source fingerprint. Subsequent successful batches return the
next content-bound continuation Context in the same field.

The same responses also return `continuation_ref`, a short unpredictable
host-local reference to that exact private record. Agents should pass this short
value as `payload.continuation_context`; the long `EDA_CONTEXT` remains the
portable handoff form. Both resolve to the same record and authorization,
content-state, identity, staging, and validation checks remain unchanged.

The next governed native batch may put that handle in
`target.continuation_context` or `target.context`. It may omit only identity and
content-state fields already bound by the Context:

- `scope.resource_kind`;
- `scope.selectors.instance/version/profile`;
- `scope.read_paths`;
- `transaction.source_fingerprints` for staged mutation.

The official program, effect, new write/artifact scope, transaction strategy,
fresh-reopen rule, promotion rule, validation program, limits, purpose, and
idempotency key remain explicit. This is continuation of an exact target, not
delegated authority or an operation recipe.

```json
{
  "purpose": "Continue the validated workspace update",
  "target": {
    "eda": "keysight-ads",
    "context": "EDA_CONTEXT:v2:..."
  },
  "operation": "native.batch",
  "payload": {
    "mutating": true,
    "plan": {
      "schema_version": "eda.native-batch/v1",
      "batch_id": "continue_update",
      "runtime": "ads.python.de",
      "effect": "staged_mutation",
      "program": {"language": "python", "source": "...", "sha256": "..."},
      "scope": {"write_paths": ["/new/sibling/output_wrk"], "artifacts": []},
      "transaction": {
        "strategy": "adapter_staging",
        "fresh_reopen": true,
        "promotion": "on_validation"
      },
      "validation": {
        "program": {"language": "python", "source": "...", "sha256": "..."},
        "required_artifacts": []
      },
      "limits": {"timeout_seconds": 180, "max_output_bytes": 65536}
    }
  },
  "idempotency_key": "continue-update-v2"
}
```

Before starting ADS Python, the Bridge resolves the private host record,
rejects every explicit target/selector/path/fingerprint conflict, recomputes
the current workspace fingerprint, and fails closed if content changed. A
successful mutation returns a new handle bound to the promoted output and its
new fingerprint. `continuation_state` reports only that a binding exists and
which non-sensitive identity dimensions were bound; it contains no path or
fingerprint.

Contexts resolve only through their origin/connection worker and do not carry
authorization, customer paths, fingerprints, programs, or validation claims.
The non-sensitive result summary follows
[`ads-continuation-state-v1.schema.json`](schemas/ads-continuation-state-v1.schema.json);
the token remains the common `eda-context/v2` contract.
