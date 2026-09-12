param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& python server.py --import-universe-csv "$CsvPath"
if ($LASTEXITCODE -ne 0) {
    throw "Universe CSV import failed, exit code: $LASTEXITCODE"
}

Write-Host "[import-universe] Completed."
