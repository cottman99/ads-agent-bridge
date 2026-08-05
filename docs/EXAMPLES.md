# Five Public Examples

These examples form a capability ladder. Each one emits a JSON acceptance
record and stops instead of promoting a partial result to a broader claim.

## 1. Discover installations

Read-only. Use this before assuming which ADS version the user wants.

```console
ads-agent --pretty examples run discover-installations
```

Add one or more `--ads-root PATH` or `--search-root PATH` options when ADS is
installed outside the normal locations. Acceptance requires at least one
instance with a stable `instance_id`; discovery does not change the configured
default.

## 2. Headless minimal AC

Creates a new disposable workspace, a schematic, a netlist, a simulation
dataset, and an independent dataset readback record.

```console
ads-agent --pretty examples run headless-minimal-ac --ads INSTANCE_ID --workspace PATH
```

On Linux, set `DISPLAY` to the intended isolated display. The workspace path
must not already exist. Passing documentation lookup alone is not sufficient;
workspace creation, simulation, and dataset readback must all pass.

## 3. Live DE context

Read-only. Launch ADS DE after `ads-agent setup`, open a disposable workspace,
then run:

```console
ads-agent --pretty examples run live-de-context --slot INSTANCE_OR_SLOT
```

Acceptance requires a token-authenticated DE bridge and an open workspace. A
stale session file or a successful socket ping without workspace context does
not pass.

## 4. DDS dataset readback

Launch DDS with the bridge add-on. Point this example at the workspace and
dataset created by the headless example:

```console
ads-agent --pretty examples run dds-dataset-readback --slot INSTANCE_OR_SLOT --workspace WORKSPACE --dataset DATASET.ds
```

The bounded command creates `ads_agent_dds_readback.dds` inside the selected
workspace, adds a dataset alias, evaluates `R1_v`, saves the DDS file, and
reports the equation status and row count. It refuses to overwrite an existing
DDS file.

## 5. Bounded AEL workspace call

Read-only. With ADS DE and a disposable workspace open:

```console
ads-agent --pretty examples run bounded-ael-workspace --slot INSTANCE_OR_SLOT
```

This calls only the allowlisted `de_get_open_workspace_pathname()` function.
It demonstrates where retained AEL is useful without enabling arbitrary AEL or
embedded Python. Dynamic `ael-call`, `eval`, and `exec` remain behind the
two-sided `ADS_AGENT_UNSAFE=1` and `--unsafe` opt-in.

## Scope

These examples cover installation management, circuit simulation, live DE,
DDS, and a bounded AEL hybrid boundary. They do not claim Momentum, RFPro,
FEM, SIPro, PIPro, arbitrary PDK automation, or unattended GUI correctness.
