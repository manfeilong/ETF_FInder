param(
    [string]$TaskName = "ETF-Finder-DailyRefresh",
    [int]$WaitSeconds = 240,
    [int]$PollSeconds = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($WaitSeconds -lt 1) {
    throw "-WaitSeconds must be >= 1."
}
if ($PollSeconds -lt 1) {
    throw "-PollSeconds must be >= 1."
}

try {
    $before = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
    $beforeRunTime = $before.LastRunTime
    $beforeResult = [int]$before.LastTaskResult
} catch {
    throw "Scheduled task not found: $TaskName"
}

Start-ScheduledTask -TaskName $TaskName
Write-Host "[run-now] Started task: $TaskName"

$elapsed = 0
$updated = $false
$detectedRunBy = ""
while ($elapsed -lt $WaitSeconds) {
    Start-Sleep -Seconds $PollSeconds
    $elapsed += $PollSeconds
    $task = Get-ScheduledTask -TaskName $TaskName
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    $lastRunChanged = ($info.LastRunTime -ne $beforeRunTime)
    $resultChanged = ([int]$info.LastTaskResult -ne $beforeResult)

    # Best signal: a new run completed and task returned to Ready.
    if ($lastRunChanged -and $task.State -eq "Ready") {
        $updated = $true
        $detectedRunBy = "lastRunChanged_and_ready"
        break
    }

    # Fallback: scheduler can stay in Queued even after a successful run.
    if ($lastRunChanged -and [int]$info.LastTaskResult -eq 0) {
        $updated = $true
        $detectedRunBy = "lastRunChanged_result0"
        break
    }

    # Fallback: result changed to 0 during wait window.
    if ($resultChanged -and [int]$info.LastTaskResult -eq 0) {
        $updated = $true
        $detectedRunBy = "resultChanged_to_0"
        break
    }
}

$taskFinal = Get-ScheduledTask -TaskName $TaskName
$infoFinal = Get-ScheduledTaskInfo -TaskName $TaskName
$result = [ordered]@{
    taskName = $TaskName
    state = [string]$taskFinal.State
    completedWithinWait = $updated
    waitSeconds = $WaitSeconds
    beforeLastRunTime = $beforeRunTime.ToString("o")
    beforeLastTaskResult = $beforeResult
    lastRunTime = $infoFinal.LastRunTime.ToString("o")
    nextRunTime = $infoFinal.NextRunTime.ToString("o")
    lastTaskResult = [int]$infoFinal.LastTaskResult
    numberOfMissedRuns = [int]$infoFinal.NumberOfMissedRuns
    detectedRunBy = $detectedRunBy
}

$result | ConvertTo-Json -Depth 4

if (-not $updated) {
    exit 2
}
if ($infoFinal.LastTaskResult -ne 0) {
    exit 1
}
exit 0
