# Contributing

Contributions should keep the three-command path reliable:

```console
pipx install ads-agent-bridge
ads-agent setup
ads-agent quickstart
```

## Local checks

Use Python 3.10 or later in an isolated environment:

```console
python -m pip install -e ".[test]"
python -m pytest
python -m build
python -m pip check
```

Do not commit Keysight documentation, generated indexes, ADS workspaces,
session files, license data, private paths, or customer material. Live ADS and
solver claims need observable evidence from a disposable or explicitly
authorized workspace.

Keep pull requests focused and explain the user-facing capability or failure
mode they change. Security reports belong in private vulnerability reporting,
not public issues.
