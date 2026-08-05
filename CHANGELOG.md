# Changelog

All notable public changes are documented here.

## 0.1.0a19 — Unreleased

- Add a read-only `ads-agent doctor` covering discovery, selected version,
  local docs, ADS Python, add-on registration, and live bridge sessions.
- Keep diagnostic reads from creating empty configuration, cache, data, or
  runtime directories.
- Record and enforce the external ADS automation context in the headless
  quickstart result.
- Build release distributions once, publish the exact artifacts to GitHub and
  PyPI, and verify their SHA256 values after upload.
- Update maintained GitHub Actions to Node 24-capable major versions.

## 0.1.0a18 — 2026-08-05

- Discover non-default Windows ADS installations from registered installer
  locations, including side-by-side versions on other drives.
- Publish through token-free PyPI Trusted Publishing with separate build and
  upload permission boundaries.
- Update the public installation path now that the package is available from
  PyPI.

## 0.1.0a17 — 2026-08-05

Initial limited public alpha.

- Discover and explicitly select local ADS installations on Windows and Linux.
- Classify stable, preview, experimental, and unsupported ADS generations.
- Build a private per-installation search index from locally installed HTML
  documentation without redistributing Keysight content.
- Install, inspect, upgrade, and uninstall the DE/DDS user add-on with backups.
- Connect to authenticated localhost-only DE and DDS bridge sessions.
- Keep arbitrary Python and AEL execution behind explicit two-sided unsafe
  opt-in.
- Run a disposable headless minimal-AC workspace and validate its ADS dataset.
- Locate Windows ADS user configuration through Keysight `eeenv/HOME` registry
  values, with an explicit config-directory override.
- Redact session bearer tokens from public CLI output.

Momentum, RFPro, FEM, SIPro, and PIPro are not part of this alpha's supported
workflow claim.
