param(
    [Parameter(Mandatory = $true)]
    [string]$Directory,
    [string]$Source = "official_snapshot_import",
    [switch]$CheckHistoryQuality,
    [string]$Codes = "",
    [int]$HistoryDays = 22,
    [ValidateSet("any", "full_only", "real_only")]
    [string]$HistoryQuality = "real_only",
    [int]$MinSnapshots = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& python server.py --import-history-snapshots "$Directory" --history-import-source "$Source"
if ($LASTEXITCODE -ne 0) {
    throw "History snapshot import failed, exit code: $LASTEXITCODE"
}

if ($CheckHistoryQuality) {
    $args = @(
        "server.py",
        "--check-history-quality",
        "--history-days", "$HistoryDays",
        "--history-quality", $HistoryQuality,
        "--min-snapshots", "$MinSnapshots",
        "--write-history-quality-report"
    )
    if (-not [string]::IsNullOrWhiteSpace($Codes)) {
        $args += @("--codes", "$Codes")
    }
    & python @args
    if ($LASTEXITCODE -ne 0) {
        throw "History quality gate failed, exit code: $LASTEXITCODE"
    }
}

Write-Host "[import-history] Completed."
