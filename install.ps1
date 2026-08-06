[CmdletBinding()]
param(
    [string] $Python,
    [string] $Package = "ads-agent-bridge",
    [switch] $Check
)

$ErrorActionPreference = "Stop"
if (-not $PSBoundParameters.ContainsKey("Package") -and $env:ADS_AGENT_BRIDGE_PACKAGE) {
    $Package = $env:ADS_AGENT_BRIDGE_PACKAGE
}
if (-not $PSBoundParameters.ContainsKey("Python") -and $env:ADS_AGENT_BRIDGE_PYTHON) {
    $Python = $env:ADS_AGENT_BRIDGE_PYTHON
}

function Test-PythonCandidate {
    param(
        [Parameter(Mandatory)] [string] $Command,
        [string[]] $PrefixArguments = @()
    )
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        return $false
    }
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Command @PrefixArguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        $candidateExitCode = $LASTEXITCODE
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return $candidateExitCode -eq 0
}

$candidates = @()
if ($Python) {
    $candidates += [pscustomobject]@{ Command = $Python; Prefix = @() }
} else {
    foreach ($version in @("-3.13", "-3.12", "-3.11", "-3.10")) {
        $candidates += [pscustomobject]@{ Command = "py"; Prefix = @($version) }
    }
    foreach ($command in @("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python")) {
        $candidates += [pscustomobject]@{ Command = $command; Prefix = @() }
    }
}

$selected = $null
foreach ($candidate in $candidates) {
    if (Test-PythonCandidate -Command $candidate.Command -PrefixArguments $candidate.Prefix) {
        $selected = $candidate
        break
    }
}
if (-not $selected) {
    throw "ADS Agent Bridge requires Python 3.10 or later. Install it and rerun: .\install.ps1 -Python C:\path\to\python.exe"
}

$pythonExecutable = (& $selected.Command @($selected.Prefix) -c "import sys; print(sys.executable)").Trim()
$pythonVersion = (& $selected.Command @($selected.Prefix) -c "import platform; print(platform.python_version())").Trim()
Write-Host "Using Python ${pythonVersion}: ${pythonExecutable}"

& $selected.Command @($selected.Prefix) -c "import venv" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python has no venv module: $pythonExecutable"
}

if ($Check) {
    Write-Host "Installer preflight passed; no packages were installed."
    exit 0
}

$pipxPython = $pythonExecutable
& $pipxPython -m pipx --version *> $null
if ($LASTEXITCODE -ne 0) {
    $bootstrapDir = if ($env:ADS_AGENT_BRIDGE_BOOTSTRAP_DIR) {
        $env:ADS_AGENT_BRIDGE_BOOTSTRAP_DIR
    } else {
        Join-Path $env:LOCALAPPDATA "ads-agent-bridge\pipx-bootstrap"
    }
    Write-Host "pipx was not found; creating an isolated bootstrap environment at $bootstrapDir"
    & $selected.Command @($selected.Prefix) -m venv $bootstrapDir
    if ($LASTEXITCODE -ne 0) { throw "Could not create the pipx bootstrap environment." }
    $pipxPython = Join-Path $bootstrapDir "Scripts\python.exe"
    & $pipxPython -m pip install --upgrade pip pipx
    if ($LASTEXITCODE -ne 0) { throw "Could not install pipx in the bootstrap environment." }
}

& $pipxPython -m pipx ensurepath
if ($LASTEXITCODE -ne 0) { throw "pipx could not configure the user PATH." }
& $pipxPython -m pipx install --force --python $pythonExecutable $Package
if ($LASTEXITCODE -ne 0) { throw "Could not install ADS Agent Bridge with pipx." }

$binDir = (& $pipxPython -m pipx environment --value PIPX_BIN_DIR).Trim()
Write-Host "ADS Agent Bridge installation completed."
Write-Host "Run now: $binDir\ads-agent.exe doctor"
Write-Host "Open a new PowerShell window before using bare 'ads-agent' if pipx changed PATH."
