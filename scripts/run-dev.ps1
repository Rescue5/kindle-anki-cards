param(
    [string]$EnvName = 'kindle_app',
    [string]$Workspace,
    [switch]$EmptyProfile
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$conda = Get-Command conda -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $conda) {
    throw 'Conda is not in PATH. Run this command from a Miniconda or Anaconda terminal.'
}

$profileArgs = @()
if ($Workspace) {
    $profileArgs += @('--workspace', $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Workspace))
}
if ($EmptyProfile) {
    $profileArgs += '--empty-profile'
}

Push-Location -LiteralPath $root
try {
    & $conda.Source run --no-capture-output -n $EnvName python -X utf8 -m scripts.run_dev @profileArgs
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
