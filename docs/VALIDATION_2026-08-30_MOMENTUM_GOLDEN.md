# Momentum generated-input validation — 2026-08-30

## Claim under test

The Bridge can execute an already-generated Momentum input through the generic
EDA Runtime without raw Agent-authored commands, preserve its source, validate
the saved S-parameter result, and commit only a verified new output directory.
It does not claim to create an EM setup from a blank layout.

## Environment and fixture

- ADS 2026 Update 2.1 on Linux
- `DISPLAY=:4.0`
- installed ADS two-port low-pass-filter example archive
- official documented `adsMomWrapper -O -3D project project` execution route
- candidate Bridge source invoked through its real JSON-lines Runtime adapter

The installed example archive was read-only evidence. Its SHA-256 remained
unchanged. Extraction and execution occurred only in an owned disposable test
directory; no customer project or private documentation was included.

## Result

- Runtime status: `passed`
- source fingerprint preserved: yes
- atomic non-overwriting output: yes
- ports: 2
- frequency points: 17
- range: 0.1 GHz to 20 GHz
- finite complete matrix: S11, S12, S21, and S22 passed
- result artifacts: non-empty CITI, AFS, and STA, each hashed
- solver process after completion: none
- source and output were distinct siblings

The bounded CITI reader also accepted the fixture's floating-point
`NORMALIZATION` value, which the installed vendor Python parser rejected. The
returned samples were physically plausible for the fixture: near-unity S21 at
the low end, falling strongly by 20 GHz, with reciprocal S12/S21 samples.

## Warning boundary

The archived fixture retained a historical absolute dataset-export path. ADS
therefore reported two dataset-export errors after successfully completing the
S-parameter simulation. The Bridge preserved this as a structured warning
(`dataset_export_failed=true`) instead of either hiding it or misclassifying the
validated CITI/AFS/STA solver result as absent.

## Protected failure behavior

Unit tests additionally prove that invalid/non-finite CITI data, nonzero or
incomplete solver execution, stale source fingerprints, unsafe path topology,
and overwrite attempts do not commit output. A timeout terminates the owned
wrapper process group, including child solver processes, before staging is
removed.

The timeout boundary was also exercised against the real fixture with a
one-second limit. Runtime returned the explicit expected failure, committed no
output directory, and left no `MomEngine`, `adsMomWrapper`, or `momServer`
process. The installed example archive hash again remained unchanged.
