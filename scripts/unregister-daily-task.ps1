param(
    [string]$TaskName = "ETF-Finder-DailyRefresh"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
} catch {
    Write-Host "[task] Not found: $TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $existing.TaskName -Confirm:$false
Write-Host "[task] Removed: $TaskName"
