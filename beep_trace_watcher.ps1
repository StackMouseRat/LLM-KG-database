$ErrorActionPreference = "SilentlyContinue"

# Relaunch as admin if needed.
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).
  IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$PSCommandPath`""
  )
  exit
}

$desktop = [Environment]::GetFolderPath("Desktop")
$log = Join-Path $desktop ("beep_trace_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

"=== START {0} ===" -f (Get-Date) | Out-File -FilePath $log -Encoding utf8
"Tips: Trigger the error sound, then press Ctrl+C to stop." | Add-Content $log
"Log file: $log" | Add-Content $log

Write-Host "Beep trace running..." -ForegroundColor Cyan
Write-Host "Log file: $log" -ForegroundColor Yellow
Write-Host "After the next error sound, press Ctrl+C and send me the last ~100 lines." -ForegroundColor Green

$seen = @{}
Get-Process | ForEach-Object { $seen[$_.Id] = $_.ProcessName }
$last = Get-Date

while ($true) {
  Start-Sleep -Milliseconds 800
  $now = Get-Date

  # Process start/exit tracking
  $current = @{}
  Get-Process | ForEach-Object { $current[$_.Id] = $_.ProcessName }

  foreach ($pid in $current.Keys) {
    if (-not $seen.ContainsKey($pid)) {
      Add-Content $log ("{0:HH:mm:ss.fff} PROC_START pid={1} name={2}" -f $now, $pid, $current[$pid])
    }
  }
  foreach ($pid in @($seen.Keys)) {
    if (-not $current.ContainsKey($pid)) {
      Add-Content $log ("{0:HH:mm:ss.fff} PROC_EXIT  pid={1} name={2}" -f $now, $pid, $seen[$pid])
    }
  }
  $seen = $current

  # Event windows between ticks (include info/warn/error)
  foreach ($ln in @("Application", "System", "Microsoft-Windows-TaskScheduler/Operational")) {
    Get-WinEvent -FilterHashtable @{ LogName = $ln; StartTime = $last; EndTime = $now } |
      Sort-Object TimeCreated |
      ForEach-Object {
        $msg = (($_.Message -split "`r?`n")[0] -replace "\s+", " ").Trim()
        Add-Content $log ("{0:HH:mm:ss.fff} EVT log={1} level={2} provider={3} id={4} msg={5}" -f $_.TimeCreated, $ln, $_.LevelDisplayName, $_.ProviderName, $_.Id, $msg)
      }
  }

  $last = $now
}
