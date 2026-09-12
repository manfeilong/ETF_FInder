param(
    [string]$TaskName = "ETF-Finder-DailyRefresh",
    [int]$AlertLimit = 5,
    [int]$AccessLogLimit = 10,
    [string]$ApiBaseUrl = "http://127.0.0.1:4173",
    [switch]$SkipApi,
    [switch]$AsJson,
    [switch]$NoFailOnUnhealthy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-JsonlTail {
    param(
        [string]$Path,
        [int]$Limit
    )
    $bounded = [Math]::Max(1, [Math]::Min($Limit, 200))
    if (-not (Test-Path $Path)) {
        return @()
    }
    $rows = @()
    $lines = Get-Content -LiteralPath $Path -Encoding UTF8 -Tail $bounded
    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        try {
            $rows += ($line | ConvertFrom-Json)
        } catch {
            continue
        }
    }
    return @($rows | Sort-Object { $_.time } -Descending)
}

function Try-GetJson {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
        if (-not $response.Content) {
            return $null
        }
        return ($response.Content | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return (Get-Content -LiteralPath $Path -Encoding UTF8 -Raw | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Build-TaskSummary {
    param([string]$Name)
    try {
        $task = Get-ScheduledTask -TaskName $Name -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction Stop
    } catch {
        return [ordered]@{
            exists = $false
            taskName = $Name
            message = "Scheduled task not found."
        }
    }

    $nextRun = $null
    if ($info.NextRunTime -and $info.NextRunTime -gt [datetime]::MinValue) {
        $nextRun = $info.NextRunTime.ToString("o")
    }
    $lastRun = $null
    $hasRun = $true
    if ($info.LastRunTime -and $info.LastRunTime -gt [datetime]::MinValue) {
        $lastRun = $info.LastRunTime.ToString("o")
        if ($info.LastRunTime.Year -le 2000) {
            $hasRun = $false
        }
    } else {
        $hasRun = $false
    }

    $triggerRows = @()
    foreach ($trigger in $task.Triggers) {
        $triggerRows += [ordered]@{
            type = $trigger.CimClass.CimClassName
            startBoundary = $trigger.StartBoundary
            enabled = $trigger.Enabled
        }
    }

    if (-not $hasRun -and $info.LastTaskResult -eq 267011) {
        $isSuccess = $true
    } else {
        $isSuccess = ($info.LastTaskResult -eq 0)
    }
    return [ordered]@{
        exists = $true
        taskName = $Name
        state = [string]$task.State
        enabled = [bool]$task.Settings.Enabled
        hasRun = $hasRun
        lastRunTime = $lastRun
        nextRunTime = $nextRun
        lastTaskResult = [int]$info.LastTaskResult
        lastRunSucceeded = $isSuccess
        numberOfMissedRuns = [int]$info.NumberOfMissedRuns
        triggers = $triggerRows
    }
}

$scriptRoot = Split-Path -Parent $PSCommandPath
$workspaceRoot = Split-Path -Parent $scriptRoot
$dataDir = Join-Path $workspaceRoot "data"
$alertsPath = Join-Path $dataDir "refresh-alerts.jsonl"
$accessLogPath = Join-Path $dataDir "access-log.jsonl"
$latestDataPath = Join-Path $dataDir "latest-etf-holdings.json"
$historyQualityPath = Join-Path $dataDir "history-quality-latest.json"

$taskSummary = Build-TaskSummary -Name $TaskName
$alerts = @(Read-JsonlTail -Path $alertsPath -Limit $AlertLimit)
$accessLogs = @(Read-JsonlTail -Path $accessLogPath -Limit $AccessLogLimit)
$localLatestData = Read-JsonFile -Path $latestDataPath
$localHistoryQuality = Read-JsonFile -Path $historyQualityPath

$apiHealth = $null
$apiHistoryQuality = $null
$apiHistoryQualityLatest = $null
$apiPipelineStatus = $null
if (-not $SkipApi) {
    $healthUrl = "$($ApiBaseUrl.TrimEnd('/'))/api/health"
    $historyUrl = "$($ApiBaseUrl.TrimEnd('/'))/api/history/quality?quality=real_only&minSnapshots=2"
    $historyLatestUrl = "$($ApiBaseUrl.TrimEnd('/'))/api/history/quality/latest"
    $pipelineStatusUrl = "$($ApiBaseUrl.TrimEnd('/'))/api/pipeline/status"
    $apiHealth = Try-GetJson -Url $healthUrl
    $apiHistoryQuality = Try-GetJson -Url $historyUrl
    $apiHistoryQualityLatest = Try-GetJson -Url $historyLatestUrl
    $apiPipelineStatus = Try-GetJson -Url $pipelineStatusUrl
}

$latestAlertLevel = ""
if ($alerts.Count -gt 0) {
    $latestAlertLevel = [string]$alerts[0].level
}
$hasRecentError = $latestAlertLevel -eq "error"

$operationalHealthy = $true
if (-not $taskSummary.exists) { $operationalHealthy = $false }
if ($taskSummary.exists -and -not $taskSummary.enabled) { $operationalHealthy = $false }
if ($taskSummary.exists -and $taskSummary.hasRun -and $taskSummary.lastTaskResult -ne 0) { $operationalHealthy = $false }
if ($hasRecentError) { $operationalHealthy = $false }

$latestQuality = $null
$latestAsOf = ""
if ($null -ne $apiPipelineStatus) {
    $latestQuality = $apiPipelineStatus.liveFetch.latestQuality
    $latestAsOf = [string]$apiPipelineStatus.liveFetch.latest.asOf
} elseif ($null -ne $localLatestData) {
    $latestQuality = $localLatestData.dataQuality
    $latestAsOf = [string]$localLatestData.asOf
}

$historyQuality = $localHistoryQuality
if ($null -ne $apiHistoryQualityLatest -and $null -ne $apiHistoryQualityLatest.report) {
    $historyQuality = $apiHistoryQualityLatest.report
}

$dataReady = $true
$dataIssues = @()
if ($null -eq $latestQuality) {
    $dataReady = $false
    $dataIssues += "No latest holdings quality result is available."
} elseif ([string]$latestQuality.status -ne "full") {
    $dataReady = $false
    $partialCodes = @($latestQuality.partialCodes) -join ","
    $dataIssues += "Latest holdings quality is $($latestQuality.status); affected codes: $partialCodes"
}
if ($null -eq $historyQuality) {
    $dataReady = $false
    $dataIssues += "No history quality report is available."
} elseif (-not [bool]$historyQuality.ok) {
    $dataReady = $false
    $failedCodes = @($historyQuality.rows | Where-Object { -not $_.ok } | ForEach-Object { $_.code })
    $dataIssues += "History quality failed for $($failedCodes.Count) ETF codes: $($failedCodes -join ',')"
}

$recommendations = @()
if (-not $operationalHealthy) {
    $recommendations += "Inspect the scheduled task exit code and the latest error alert before the next run."
}
if (-not $dataReady) {
    $recommendations += "Review data/history-quality-latest.json and configure complete official holdings sources for failing ETF codes."
}
$status = if (-not $operationalHealthy) { "operational_failure" } elseif (-not $dataReady) { "data_not_ready" } else { "ready" }

$report = [ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    healthy = $operationalHealthy
    operationalHealthy = $operationalHealthy
    dataReady = $dataReady
    status = $status
    dataIssues = $dataIssues
    recommendations = $recommendations
    data = [ordered]@{
        latestAsOf = $latestAsOf
        latestQualityStatus = $(if ($null -eq $latestQuality) { "missing" } else { [string]$latestQuality.status })
        partialCodes = $(if ($null -eq $latestQuality) { @() } else { @($latestQuality.partialCodes) })
        historyReportGeneratedAt = $(if ($null -eq $historyQuality) { "" } else { [string]$historyQuality.generatedAt })
        historyPassCount = $(if ($null -eq $historyQuality) { 0 } else { [int]$historyQuality.passCount })
        historyFailCount = $(if ($null -eq $historyQuality) { 0 } else { [int]$historyQuality.failCount })
    }
    task = $taskSummary
    latestAlertLevel = $latestAlertLevel
    alerts = $alerts
    accessLogs = $accessLogs
    api = [ordered]@{
        baseUrl = $ApiBaseUrl
        checked = (-not $SkipApi)
        health = $apiHealth
        historyQuality = $apiHistoryQuality
        historyQualityLatest = $apiHistoryQualityLatest
        pipelineStatus = $apiPipelineStatus
    }
}

if ($AsJson) {
    $report | ConvertTo-Json -Depth 8
    if ((-not $operationalHealthy) -and (-not $NoFailOnUnhealthy)) {
        exit 1
    }
    exit 0
}

Write-Host "[check] Operational healthy: $operationalHealthy"
Write-Host "[check] Data ready: $dataReady"
Write-Host "[check] Overall status: $status"
Write-Host "[check] Latest holdings date: $latestAsOf"
if ($null -ne $latestQuality) {
    Write-Host "[check] Latest holdings quality: $($latestQuality.status)"
}
Write-Host "[check] Task exists: $($taskSummary.exists)"
if ($taskSummary.exists) {
    Write-Host "[check] Task enabled: $($taskSummary.enabled)"
    Write-Host "[check] Task has run: $($taskSummary.hasRun)"
    Write-Host "[check] Last run result: $($taskSummary.lastTaskResult)"
    Write-Host "[check] Last run time: $($taskSummary.lastRunTime)"
    Write-Host "[check] Next run time: $($taskSummary.nextRunTime)"
}
if ($alerts.Count -gt 0) {
    Write-Host "[check] Latest alert: [$($alerts[0].level)] $($alerts[0].message)"
}
if (-not $SkipApi) {
    if ($null -ne $apiHealth) {
        Write-Host "[check] API health reachable: true"
    } else {
        Write-Host "[check] API health reachable: false"
    }
}
foreach ($issue in $dataIssues) {
    Write-Host "[check] Data issue: $issue"
}
foreach ($recommendation in $recommendations) {
    Write-Host "[check] Next step: $recommendation"
}

if ((-not $operationalHealthy) -and (-not $NoFailOnUnhealthy)) {
    exit 1
}
