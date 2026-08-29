# Linux ADS Python and EM runtime validation

Date: 2026-08-30

This gate used the discovered ADS 2026 Update 2.1 bundled Python on Linux with the selected
virtual display. It validates runtime initialization only; it did not open a customer workspace,
create an EM setup, run a solver, or claim Momentum/RFPro completion.

## Failure reproduced

The existing generic Linux environment initialized `keysight.ads.de`, dataset, and DDS, but
`keysight.ads.emtools` failed because `libemViewsPlugin.so` was outside the shared loader paths.
The library was discovered under the selected ADS installation's own
`bin/plugins/pde_core` directory. No machine-specific absolute path was added to the product.

## Candidate acceptance

- one shared environment builder is used by quickstart, `workspace.create`, and `design.apply`;
- Windows and Linux resolver tests pass without pretending that Linux loader state exists on
  Windows;
- the candidate environment initialized `keysight.ads.de`, `keysight.ads.dds`, and
  `keysight.ads.emtools` together under the selected Linux display;
- the full public test suite passed;
- the temporary candidate module was removed from the EDA host after the probe.

The remaining two-port Momentum solver-completion gate is tracked separately. An import probe,
visible port, generated input file, or readable dataset is not accepted as that evidence.
