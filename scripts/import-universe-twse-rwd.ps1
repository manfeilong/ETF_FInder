param(
    [string]$TwseLang = "zh"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$args = @("server.py", "--import-universe-twse-rwd", "--twse-lang", $TwseLang)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw "TWSE universe import failed, exit code: $LASTEXITCODE"
}

Write-Host "[import-universe-twse] Completed."
