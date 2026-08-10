#!/bin/sh
set -eu

package=${ADS_AGENT_BRIDGE_PACKAGE:-ads-agent-bridge}
python_override=${ADS_AGENT_BRIDGE_PYTHON:-}
check_only=0

usage() {
    printf '%s\n' 'Usage: sh install.sh [--python PYTHON] [--package PACKAGE_OR_WHEEL] [--check]'
    printf '%s\n' 'Find Python 3.10+, bootstrap pipx when needed, and install ADS Agent Bridge.'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --python)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            python_override=$2
            shift 2
            ;;
        --package)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            package=$2
            shift 2
            ;;
        --check)
            check_only=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

python_command=
if [ -n "$python_override" ]; then
    if command -v "$python_override" >/dev/null 2>&1 &&
        "$python_override" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        python_command=$python_override
    fi
else
    candidates='python3.13 python3.12 python3.11 python3.10 python3 python'
    for candidate in $candidates; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
            python_command=$candidate
            break
        fi
    done
fi

if [ -z "$python_command" ]; then
    printf '%s\n' 'ADS Agent Bridge requires Python 3.10 or later.' >&2
    printf '%s\n' 'Install Python 3.10+, then rerun with: sh install.sh --python /path/to/python3.11' >&2
    exit 3
fi

python_executable=$("$python_command" -c 'import sys; print(sys.executable)')
python_version=$("$python_command" -c 'import platform; print(platform.python_version())')
printf 'Using Python %s: %s\n' "$python_version" "$python_executable"

if ! "$python_command" -c 'import venv' >/dev/null 2>&1; then
    printf '%s\n' "The selected Python has no venv module: $python_executable" >&2
    printf '%s\n' 'Install the venv component for that interpreter and rerun this installer.' >&2
    exit 4
fi

if [ "$check_only" -eq 1 ]; then
    printf '%s\n' 'Installer preflight passed; no packages were installed.'
    exit 0
fi

pipx_python=$python_command
if ! "$pipx_python" -m pipx --version >/dev/null 2>&1; then
    bootstrap_dir=${ADS_AGENT_BRIDGE_BOOTSTRAP_DIR:-$HOME/.local/share/ads-agent-bridge/pipx-bootstrap}
    printf '%s\n' "pipx was not found; creating an isolated bootstrap environment at $bootstrap_dir"
    "$python_command" -m venv "$bootstrap_dir"
    pipx_python=$bootstrap_dir/bin/python
    "$pipx_python" -m pip install --upgrade pip pipx
fi

"$pipx_python" -m pipx ensurepath
pipx_backend_args=
if "$pipx_python" -m pipx install --help 2>&1 | grep -q -- '--backend'; then
    pipx_backend_args='--backend pip'
fi
# Intentional word splitting: the optional value contains two pipx arguments.
# shellcheck disable=SC2086
"$pipx_python" -m pipx install $pipx_backend_args --force --python "$python_executable" "$package"

bin_dir=$("$pipx_python" -m pipx environment --value PIPX_BIN_DIR 2>/dev/null || printf '%s/.local/bin' "$HOME")
printf '%s\n' 'ADS Agent Bridge installation completed.'
printf 'Run now: %s/ads-agent doctor\n' "$bin_dir"
printf '%s\n' 'Open a new shell before using bare `ads-agent` if pipx changed PATH.'
