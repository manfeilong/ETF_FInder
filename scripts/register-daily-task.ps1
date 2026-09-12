param(
    [string]$TaskName = "ETF-Finder-DailyRefresh",
    [string]$At = "18:30",
    [string]$Codes = "",
    [int]$HistoryDays = 22,
    [ValidateSet("any", "full_only", "real_only")]
    [string]$HistoryQuality = "real_only",
    [int]$MinSnapshots = 2,
    [switch]$StrictOfficialQuality,
    [int]$MinDeclaredHoldings = 30,
    [int]$MinParsedHoldings = 30,
    [switch]$SkipHistoryGate,
    [switch]$FailOnHistoryQuality
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Parse-TimeValue {
    param([string]$RawTime)
    try {
        return [datetime]::ParseExact($RawTime, "HH:mm", $null)
    } catch {
        throw "Invalid -At format: '$RawTime'. Use HH:mm, e.g. 18:30."
    }
}

$scriptRoot = Split-Path -Parent $PSCommandPath
$workspaceRoot = Split-Path -Parent $scriptRoot
$dailyScript = Join-Path $scriptRoot "daily-refresh.ps1"
if (-not (Test-Path $dailyScript)) {
    throw "Missing workflow script: $dailyScript"
}

$timeValue = Parse-TimeValue -RawTime $At
$selfUser = "$env:USERDOMAIN\$env:USERNAME"

$argParts = @(
    "-WindowStyle", "Hidden",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$dailyScript`"",
    "-HistoryDays", "$HistoryDays",
    "-HistoryQuality", $HistoryQuality,
    "-MinSnapshots", "$MinSnapshots",
    "-MinDeclaredHoldings", "$MinDeclaredHoldings",
    "-MinParsedHoldings", "$MinParsedHoldings"
)
if (-not [string]::IsNullOrWhiteSpace($Codes)) {
    $argParts += @("-Codes", "`"$Codes`"")
}
if ($StrictOfficialQuality) {
    $argParts += "-StrictOfficialQuality"
}
if ($SkipHistoryGate) {
    $argParts += "-SkipHistoryGate"
}
if ($FailOnHistoryQuality) {
    $argParts += "-FailOnHistoryQuality"
}
$arguments = $argParts -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $workspaceRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $timeValue
$principal = New-ScheduledTaskPrincipal -UserId $selfUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "[task] Registered: $TaskName"
Write-Host "[task] User: $selfUser"
Write-Host "[task] Time: $At"
Write-Host "[task] Command: powershell.exe $arguments"
