param(
    [string]$Codes = "",
    [string]$AsOf = "",
    [string]$Source = "official_twse_etffortune"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$args = @("server.py", "--import-metrics-etffortune", "--metrics-source", $Source)
if (-not [string]::IsNullOrWhiteSpace($Codes)) {
    $args += @("--metrics-codes", $Codes)
}
if (-not [string]::IsNullOrWhiteSpace($AsOf)) {
    $args += @("--metrics-as-of", $AsOf)
}

& python @args
if ($LASTEXITCODE -ne 0) {
    throw "ETFortune metrics import failed, exit code: $LASTEXITCODE"
}

Write-Host "[import-metrics-etffortune] Completed."
