param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$UsePyLauncher = $null -ne (Get-Command py -ErrorAction SilentlyContinue)
$UsePython = $null -ne (Get-Command python -ErrorAction SilentlyContinue)

if (-not $UsePyLauncher -and -not $UsePython) {
    throw "Python 3 is required but was not found in PATH."
}

function Invoke-Python {
    param([string[]]$Arguments)

    if ($script:UsePyLauncher) {
        & py -3 @Arguments
    }
    else {
        & python @Arguments
    }
}

if ($UsePyLauncher) {
    & py -3 "scripts/wenyoo_launcher.py" @RemainingArgs
}
else {
    & python "scripts/wenyoo_launcher.py" @RemainingArgs
}
exit $LASTEXITCODE
