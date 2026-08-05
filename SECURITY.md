# Security

Do not report security vulnerabilities through a public issue. Use GitHub's
private vulnerability reporting for this repository.

The product security boundary is localhost-only transport with a random token
per ADS session. Arbitrary Python or AEL execution will require explicit unsafe
mode and is not part of the default quickstart path.

Session JSON files contain bearer tokens. They are written to the local runtime
directory with restrictive permissions where supported. The public
`bridge sessions` command redacts tokens.

This alpha is intended for local ADS installations and disposable workspaces.
Do not expose bridge ports through a proxy, port forward, or public interface.
