param(
    [switch]$ListedOnly,
    [switch]$CheckHistoryQuality,
    [int]$HistoryDays = 22,
    [ValidateSet("any", "full_only", "real_only")]
    [string]$HistoryQuality = "real_only",
    [int]$MinSnapshots = 2,
    [switch]$WriteHistoryQualityReport
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $PSCommandPath
$workspaceRoot = Split-Path -Parent $scriptRoot
$universePath = Join-Path $workspaceRoot "data\etf-universe.json"

if (-not (Test-Path -LiteralPath $universePath)) {
    throw "Universe file not found: $universePath"
}

$universeRows = Get-Content -LiteralPath $universePath -Raw | ConvertFrom-Json
if (-not $universeRows) {
    throw "Universe file is empty: $universePath"
}

$rows = @($universeRows)
if ($ListedOnly) {
    $rows = @($rows | Where-Object { [string]$_.status -eq "listed" })
}

$codes = @($rows | ForEach-Object { [string]$_.code } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($codes.Count -eq 0) {
    throw "No ETF codes selected from universe."
}

$codeArg = ($codes -join ",")
Write-Host "[refresh-universe] Target ETF count: $($codes.Count)"
Write-Host "[refresh-universe] Codes: $codeArg"

if ($codes.Count -gt 20) {
    Write-Host "[refresh-universe] Code count > 20, using --refresh-once default universe mode."
    & python server.py --refresh-once
} else {
    & python server.py --refresh-once --codes "$codeArg"
}
if ($LASTEXITCODE -ne 0) {
    throw "Refresh failed, exit code: $LASTEXITCODE"
}

if ($CheckHistoryQuality) {
    $gateArgs = @(
        "server.py",
        "--check-history-quality",
        "--codes", "$codeArg",
        "--history-days", "$HistoryDays",
        "--history-quality", $HistoryQuality,
        "--min-snapshots", "$MinSnapshots"
    )
    if ($WriteHistoryQualityReport) {
        $gateArgs += "--write-history-quality-report"
    }
    & python @gateArgs
    if ($LASTEXITCODE -ne 0) {
        throw "History quality check failed, exit code: $LASTEXITCODE"
    }
}

Write-Host "[refresh-universe] Completed successfully."
