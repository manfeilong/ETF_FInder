param(
    [string]$Codes = "",
    [int]$HistoryDays = 22,
    [ValidateSet("any", "full_only", "real_only")]
    [string]$HistoryQuality = "real_only",
    [int]$MinSnapshots = 2,
    [switch]$StrictOfficialQuality,
    [int]$MinDeclaredHoldings = 30,
    [int]$MinParsedHoldings = 30,
    [switch]$SkipHistoryGate,
    [switch]$FailOnHistoryQuality,
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Label,
        [string[]]$PythonArgs
    )
    Write-Host "[daily-refresh] $Label"
    & python @PythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($Label), exit code: $LASTEXITCODE"
    }
}

$scriptRoot = Split-Path -Parent $PSCommandPath
$workspaceRoot = Split-Path -Parent $scriptRoot
$serverScript = Join-Path $workspaceRoot "server.py"
if (-not (Test-Path -LiteralPath $serverScript)) {
    throw "Missing server entrypoint: $serverScript"
}

if ($ValidateOnly) {
    [ordered]@{
        ok = $true
        mode = "validate_only"
        workspaceRoot = $workspaceRoot
        codesMode = $(if ([string]::IsNullOrWhiteSpace($Codes)) { "listed_universe" } else { "explicit" })
        codes = $Codes
        strictOfficialQuality = [bool]$StrictOfficialQuality
        historyGateEnabled = (-not [bool]$SkipHistoryGate)
        historyQualityFailureIsFatal = [bool]$FailOnHistoryQuality
        steps = @("check_config", "refresh_latest_holdings", "prune_history") + $(if ($SkipHistoryGate) { @() } else { @("check_history_quality") })
    } | ConvertTo-Json -Depth 4
    exit 0
}

if ($StrictOfficialQuality) {
    $env:ETF_LIVE_REQUIRE_FULL_HOLDINGS = "1"
    $env:ETF_LIVE_MIN_DECLARED_HOLDINGS = "$MinDeclaredHoldings"
    $env:ETF_LIVE_MIN_PARSED_HOLDINGS = "$MinParsedHoldings"
    Write-Host "[daily-refresh] Strict official quality enabled (full + min declared $MinDeclaredHoldings / parsed $MinParsedHoldings)"
}

$checkConfigArgs = @($serverScript, "--check-config")
Invoke-Step -Label "Check config" -PythonArgs $checkConfigArgs

$refreshArgs = @($serverScript, "--refresh-once")
if (-not [string]::IsNullOrWhiteSpace($Codes)) {
    $refreshArgs += @("--codes", $Codes)
}
Invoke-Step -Label "Refresh latest holdings" -PythonArgs $refreshArgs

$pruneArgs = @($serverScript, "--prune-history")
Invoke-Step -Label "Prune history by retention policy" -PythonArgs $pruneArgs

$historyQualityPassed = $true
if (-not $SkipHistoryGate) {
    $gateArgs = @(
        $serverScript,
        "--check-history-quality",
        "--history-days", "$HistoryDays",
        "--history-quality", $HistoryQuality,
        "--min-snapshots", "$MinSnapshots",
        "--write-history-quality-report"
    )
    if (-not [string]::IsNullOrWhiteSpace($Codes)) {
        $gateArgs += @("--codes", $Codes)
    }
    Write-Host "[daily-refresh] Run history quality gate"
    & python @gateArgs
    $gateExitCode = $LASTEXITCODE
    if ($gateExitCode -ne 0) {
        $historyQualityPassed = $false
        if ($FailOnHistoryQuality -or $gateExitCode -ne 1) {
            throw "Step failed (Run history quality gate), exit code: $gateExitCode"
        }
        Write-Warning "History quality is not ready yet. Refresh completed successfully; see data/history-quality-latest.json for failing ETF codes."
    }
}

if ($historyQualityPassed) {
    Write-Host "[daily-refresh] Completed successfully; history quality gate passed."
} else {
    Write-Host "[daily-refresh] Completed successfully with a data-quality warning."
}
