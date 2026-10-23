# Security

Do not report security vulnerabilities through a public issue. Use GitHub's
private vulnerability reporting for this repository.

The product security boundary is localhost-only transport with a random token
per ADS session. Official Python, including official AEL interoperability,
runs through `native.execute` with an exact target, Runtime admission and an
explicit validation contract. Python uses normal imports and builtins; this
execution path is intended for trusted agents and is not a hostile-code sandbox.

Session JSON files contain bearer tokens. They are written to the local runtime
directory with restrictive permissions where supported. The public
`bridge sessions` command redacts tokens.

This alpha is intended for local ADS installations and disposable workspaces.
Do not expose bridge ports through a proxy, port forward, or public interface.
