# Validation record — 2026-08-05

## Outcome

`ads-agent-bridge 0.1.0a17` passes the minimum public core on Windows and
Linux. The alpha package is suitable for a limited public release that claims
installation discovery, private local documentation indexing, recoverable
DE/DDS add-on registration, authenticated localhost bridge connectivity, and
the minimal headless AC workflow.

The full v0.1 contract is not yet complete because the real two-port Momentum
golden path has not passed. No EM or RFPro solver-completion claim is made by
this record.

## 0.1.0a19 remote candidate

The unreleased a19 candidate adds a genuinely read-only `ads-agent doctor`,
enforces the external-automation context in the headless quickstart, and
changes release automation to build once and publish the same distributions
to GitHub and PyPI. It remains a draft candidate until the required Windows
ADS acceptance is complete.

Remote target: `eda-server`, ADS 2026 Update 2.1, bundled Python 3.13.11,
isolated `DISPLAY=:2`, state, workspace, config, and bridge slot `a19`.

- GitHub CI: Windows and Linux, Python 3.10 and 3.13 passed with 23 tests.
- `doctor --no-ping`: discovered ADS, Python, ADS/Python/AEL/DDS documentation,
  and support tier without creating the requested `ADS_AGENT_HOME` directory.
- First setup indexed all 9,422 discovered HTML pages and registered DE/DDS
  only in an isolated config directory.
- Documentation query: `create_workspace` returned a bootstrap-index result.
- Headless quickstart: all gates passed; `running_automation=True`,
  `is_pde_app=False`, 31 dataset rows, and 1.033-second simulator runtime.
- Live DE and DDS: separate authenticated sessions used slot `a19`, localhost
  ports, random tokens, and `DISPLAY=:2`; ping, status, and capability probes
  passed for both profiles.
- AEL interoperability: `de_save_all_designs` completed through the guarded
  AEL channel after status proved that no workspace was open.
- Linux GUI startup required ADS `tools/python/lib` in `LD_LIBRARY_PATH`; the
  first launch exited before opening a window and left no process or session.
- Cleanup: only the two session-owned PIDs were terminated. User ADS/DE and
  DDS processes on `DISPLAY=:4` were preserved.
- The real DE/DDS XML files were restored to their pre-test SHA256 value
  `8e988072d890dd22b8030aa5f34fb401c33217ec8f42aee0f29b9a70afcf903c`.

## Release artifact

- Wheel: `ads_agent_bridge-0.1.0a17-py3-none-any.whl`
- Source distribution: `ads_agent_bridge-0.1.0a17.tar.gz`
- Clean Python 3.10 installation: passed, including declared dependencies.
- `pip check`: no broken requirements.
- Unit tests: 18 passed.
- Wheel inspection: contains only the public package, metadata, and MIT
  license; no documentation corpus, generated index, private path, host, or
  monorepo runtime dependency was found.

## Linux acceptance

Target: ADS 2026 Update 2.1 with its bundled Python 3.13, using an isolated X
display, state directory, user profile, workspace, slot, and ports.

- Automatic installation discovery: passed.
- Local documentation roots: ADS, Python, AEL, and DDS discovered.
- Fast private index: 9,422 HTML pages indexed; repeat run reused the index.
- `setup`: passed, including isolated DE and DDS registration.
- Final a16 `quickstart`: passed all six reported gates.
- Circuit evidence: 30-line generated netlist; 31 dataset rows; columns
  `freq`, `R1_v`, and `SRC1.i`; frequency range 1 Hz to 1 MHz.
- Live DE and DDS sessions: authenticated ping/status passed.
- Safe/unsafe boundary: arbitrary Python rejected by default and worked only
  after explicit process and client opt-in.
- Project management: copied workspace open/readback passed.
- AEL interoperability: bounded function discovery and workspace refresh
  passed.
- DDS: equation readback was valid with 31 complex samples.
- Headless route: separate workspace simulation and dataset readback passed.
- Cleanup: test ADS processes were terminated; pre-existing add-on XML files
  were restored to their exact pre-test SHA-256 values.

## Windows acceptance

Stable-version headless matrix:

| ADS version | Support | Indexed pages | Quickstart | Dataset rows |
|---|---:|---:|---:|---:|
| 2026 Update 2 | stable | 9,422 | passed | 31 |
| 2026 Update 1 | stable | 8,825 | passed | 31 |
| 2025 Update 2 | stable | 7,649 | passed | 31 |

Additional Windows gates:

- Clean wheel installation under Python 3.10: passed.
- Multi-installation discovery found the three stable installations plus an
  older ADS 2023 Update 1 installation without silently changing the default.
- ADS user configuration discovery followed Keysight's per-version
  `eeenv/HOME` registry value instead of assuming `%USERPROFILE%`.
- Real isolated ADS 2026 Update 2 DE and DDS add-on startup: passed.
- New DE and DDS sessions used localhost, random tokens, separate profiles,
  and the expected disposable workspace; ping/status passed.
- Public session listing redacted the token and reported only `has_token`;
  authenticated requests continued to use the private session record.
- Add-on XML recovery: byte-identical SHA-256 values before and after the live
  test.
- Test processes were terminated by exact new PID; the pre-existing user ADS
  process set remained unchanged.
- The final quickstart did not write ADS `.cfg` files into the caller's
  current directory.

## Older-version boundary

ADS 2023 Update 1 was discovered and `setup` degraded cleanly: missing local
HTML documentation was reported as `not_available`, and unsupported Python
add-on registration was skipped. Its bundled Python lacks `keysight.ads.de`,
so the circuit quickstart correctly failed. This is evidence for the current
unsupported boundary, not a failure of the stable ADS 2025+ claim.

## Remaining gates

1. Build and accept a distributable two-port Momentum fixture with solver-side
   port, terminal status, result-artifact, and numeric S-parameter evidence.
2. Make the maintained RFPro/Momentum acceptance harness cross-platform; the
   current external harness assumes the Windows `tools/python/python.exe`
   layout and cannot validate a Linux solver run.
3. Run the ADS 2024 Update 2 preview and ADS 2023 Update 2 experimental lanes
   on real installations before strengthening their support language.
4. Run the a19 Windows ADS acceptance matrix before merging or publishing the
   candidate. The single-build GitHub/PyPI hash gate can only be accepted by
   the a19 release workflow itself.
