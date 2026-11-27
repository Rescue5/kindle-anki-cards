# Build the Windows installer (NSIS .exe) with the bundled Python bridge.
#
# Run from any directory inside the activated project environment:
#   conda activate kindle_app
#   ./scripts/build-installer.ps1 -RankingModel C:\models\rp-v2-expanded.sqlite
#   ./scripts/build-installer.ps1 -SkipBridge  # reuse a verified private 1.0 bridge
#
# Output: src-tauri/target/release/bundle/nsis/*.exe

param([switch]$SkipBridge, [string]$RankingModel)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $SkipBridge) {
    if (-not $RankingModel) { $RankingModel = '.app-data/models/rp-v2-expanded.sqlite' }
    if (-not (Test-Path -LiteralPath $RankingModel -PathType Leaf)) {
        throw "Private 1.0 installer requires the local expanded ranking model. Supply -RankingModel <path>."
    }
    python packaging/build_bridge.py --expanded-model $RankingModel --model-notice packaging/ranking-model-notices.txt
    if ($LASTEXITCODE -ne 0) { throw "Bridge build failed" }
}
if (-not (Test-Path "build/bridge/kindle-bridge/kindle-bridge.exe")) {
    throw "build/bridge/kindle-bridge is missing; run without -SkipBridge"
}
$model = 'build/bridge/kindle-bridge/models/rp-v2-expanded.sqlite'
$notice = 'build/bridge/kindle-bridge/ranking-model-notices.txt'
if ((Get-FileHash -LiteralPath $model).Hash -ne 'A24E16FA43A22AB3CDB871B2BC16971997FE97AB1A35CE18EE53119090D96F75') {
    throw "Bundled ranking model does not match the tested 1.0 resource."
}
if ((Get-FileHash -LiteralPath $notice).Hash -ne (Get-FileHash -LiteralPath 'packaging/ranking-model-notices.txt').Hash) {
    throw "Bundled ranking model notice does not match the source notice."
}

npm run tauri -- build --config src-tauri/tauri.bundle.conf.json
if ($LASTEXITCODE -ne 0) { throw "Tauri build failed" }

Get-ChildItem "src-tauri/target/release/bundle/nsis/*.exe" | ForEach-Object {
    "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB)
}
