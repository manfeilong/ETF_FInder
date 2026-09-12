param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath,
    [string]$AsOf = "",
    [string]$Source = "official_metrics_csv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$args = @("server.py", "--import-metrics-csv", "$CsvPath", "--metrics-source", "$Source")
if (-not [string]::IsNullOrWhiteSpace($AsOf)) {
    $args += @("--metrics-as-of", "$AsOf")
}

& python @args
if ($LASTEXITCODE -ne 0) {
    throw "Metrics CSV import failed, exit code: $LASTEXITCODE"
}

Write-Host "[import-metrics] Completed."
