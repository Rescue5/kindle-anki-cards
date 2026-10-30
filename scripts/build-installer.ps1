# Build the Windows installer (NSIS .exe) with the bundled Python bridge.
#
# Run from any directory inside the activated project environment:
#   conda activate kindle_app
#   ./scripts/build-installer.ps1            # full build
#   ./scripts/build-installer.ps1 -SkipBridge  # reuse build/bridge from a previous run
#
# Output: src-tauri/target/release/bundle/nsis/*.exe

param([switch]$SkipBridge)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $SkipBridge) {
    python packaging/build_bridge.py
    if ($LASTEXITCODE -ne 0) { throw "Bridge build failed" }
}
if (-not (Test-Path "build/bridge/kindle-bridge/kindle-bridge.exe")) {
    throw "build/bridge/kindle-bridge is missing; run without -SkipBridge"
}

npm run tauri -- build --config src-tauri/tauri.bundle.conf.json
if ($LASTEXITCODE -ne 0) { throw "Tauri build failed" }

Get-ChildItem "src-tauri/target/release/bundle/nsis/*.exe" | ForEach-Object {
    "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB)
}
