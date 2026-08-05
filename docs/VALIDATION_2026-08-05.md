# Validation record — 2026-08-05

## Outcome

`ads-agent-bridge 0.1.0a21` passes the minimum public core on Windows and
Linux. The candidate is suitable for a limited public release that claims
multi-installation discovery, private local documentation conversion and
indexing, recoverable DE/DDS add-on registration, authenticated localhost
bridge connectivity, five bounded public examples, and a portable Docs Skill.

No EM or RFPro solver-completion claim is made by this record. Those workflows
remain future extension lanes and are not part of the minimum v0.1 promise.

## 0.1.0a21 Windows onboarding hardening

The a21 candidate retains the a20 capability surface and closes three defects
found during a clean Windows PyPI acceptance run:

- A new ADS 2026 Update 2 state indexed 9,422 local HTML pages. Before full
  Markdown enrichment, the formerly unbounded query
  `de.open_workspace ADS Python` completed in 0.271 seconds and returned the
  exact version-matched API source from the bootstrap index.
- Client slot selection now accepts the same punctuation and case variants as
  the embedded server. Stale DE/DDS session files remain inert on disk but are
  no longer listed or selected after their owning ADS process exits.
- The packaged a21 wheel connected from an isolated Linux virtual environment
  to the existing `DISPLAY=:4` DE session when given the hyphenated slot
  `ads2026u2-d4`; ping and status resolved it to `ads2026u2_d4`. The candidate
  environment was then removed, leaving the server's canonical command on the
  latest actually published release.
- Windows process liveness uses `OpenProcess` and `GetExitCodeProcess`; it does
  not send a signal to ADS or another process.

The clean PyPI a20 baseline installed into an isolated virtual environment,
passed `pip check`, auto-discovered ADS 2026 Update 2, built the complete
9,422-page private Markdown corpus with zero errors, and passed headless AC
simulation with 31 dataset rows. An isolated Windows DE/DDS launch then passed
authenticated localhost ping, status, capability probes, and bounded DDS
readback with 31 rows while unsafe execution remained disabled. The Windows
launcher did not open the workspace supplied as its command-line argument, so
the two DE examples correctly stopped at their declared `open workspace`
prerequisite. The same five examples passed remotely on the dedicated ADS
session at `DISPLAY=:4`.

Only the exact test-owned Windows process tree was terminated. The existing
user DE process (PID 56928) remained alive, its workspace was not modified,
and the ADS 6.40 registry HOME was restored and verified as
`F:\pfli\Workspace\ADS`. All 32 unit tests passed after the a21 changes.

## 0.1.0a20 five-example and Docs Skill candidate

The public example catalog is exact and machine-readable:

1. `discover-installations`
2. `headless-minimal-ac`
3. `live-de-context`
4. `dds-dataset-readback`
5. `bounded-ael-workspace`

Remote acceptance used `eda-server`, ADS 2026 Update 2.1, bundled Python 3.13,
and only `DISPLAY=:2`. State, configuration, workspace, bridge sessions, Docs
Skill target, and logs were isolated under the a20 lab directory.

- Installation and support discovery passed; 9,422 local HTML pages were
  discovered without a hard-coded ADS version.
- Headless minimal AC passed workspace creation, simulation, and dataset
  readback with 31 rows and columns `freq`, `R1_v`, and `SRC1.i`.
- Live DE context passed against the disposable workspace.
- The fixed read-only AEL workspace command passed with
  `unsafe_python_enabled=false`.
- DDS readback created a bounded DDS file, validated `agent_readback=R1_v`,
  and returned 31 rows with `unsafe_enabled=false`.
- Arbitrary `exec` was rejected by the server after unsafe mode was removed,
  even when the client supplied `--unsafe`.
- The background Docs build converted all 9,422 inputs to private Markdown,
  enriched all 9,422 index rows, recorded zero conversion errors, and changed
  its durable status from `running` to `completed`.
- A post-build query returned the generated Markdown path and original local
  source path.
- Portable Docs Skill installation, exact-digest status, idempotence, conflict
  refusal, backup, and recoverable uninstall are covered by tests and clean
  installation smoke checks.
- Only the exact a20-owned DE/DDS process tree was terminated. Existing user
  DE/DDS processes on `DISPLAY=:4` remained alive.
- Real ADS add-on XML files were restored byte-identically; both SHA-256 values
  are `8e988072d890dd22b8030aa5f34fb401c33217ec8f42aee0f29b9a70afcf903c`.

Windows a20 acceptance used isolated state, add-on configuration, and a new
disposable workspace. Automatic discovery found ADS 2026 U2, ADS 2026 U1,
ADS 2025 U2, and ADS 2023 U1. ADS 2026 U2 headless minimal AC passed all gates
with 31 dataset rows. No new Windows GUI session was launched, so the user's
existing ADS windows were not touched.

Package gates for a20:

- 29 unit tests passed.
- A clean wheel installation pulled all declared dependencies and passed
  `pip check`.
- Wheel inspection confirmed the five-example catalog, Docs tooling, and
  packaged Skill assets.
- The canonical and packaged Docs Skill both passed the Skill validator.
- Agent Kit architecture, Docs KB, installed-skill zero-drift, and the three
  required edition dry runs passed.
- `scan_stale_references.py` still reports absolute paths inside historical
  generated `products/releases/*` payloads. This pre-existing repository
  hygiene debt must be cleared before publishing an Agent Kit edition; it does
  not affect the standalone bridge wheel.

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

Windows a19 acceptance used isolated state, add-on config, documentation
indexes, and disposable workspaces while preserving the user's open ADS 2026
Update 2 DE/DDS processes.

- Read-only doctor discovered ADS 2026 U2, ADS 2026 U1, ADS 2025 U2, and
  unsupported ADS 2023 U1 from Windows installer records without creating its
  requested state directory.
- ADS 2026 U2: 9,422 pages indexed; headless quickstart passed with 31 rows.
- ADS 2026 U1: 8,825 pages indexed; headless quickstart passed with 31 rows.
- ADS 2025 U2: 7,649 pages indexed; headless quickstart passed with 31 rows.
- All three runs reported `running_automation=True` and `is_pde_app=False`.
- User DE/DDS PIDs `56928` and `38020` remained unchanged, and the real user
  add-on XML hashes remained unchanged.
- A new Windows live session was not launched: strict virtual-desktop preflight
  found only the current desktop and no quiet move backend. The add-on server
  is unchanged from the a18 Windows live acceptance; a19 client/doctor live
  behavior is covered by the a19 Linux DE/DDS sessions. This inherited evidence
  is sufficient only for the existing limited-alpha claim.

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

1. Clear or exclude historical generated release payloads that fail the Agent
   Kit stale-reference scan before publishing an Agent Kit edition.
2. Run the ADS 2024 Update 2 preview and ADS 2023 Update 2 experimental lanes
   on real installations before strengthening their support language.
3. The single-build GitHub/PyPI hash gate can only be accepted by the a20
   release workflow itself.
