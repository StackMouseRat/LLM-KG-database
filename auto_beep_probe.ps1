$ErrorActionPreference = "SilentlyContinue"

$desktop = [Environment]::GetFolderPath("Desktop")
$log = Join-Path $desktop ("auto_beep_probe_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
"START $(Get-Date)" | Out-File -FilePath $log -Encoding utf8
"Collecting: System/Application/TaskScheduler events + process start/exit" | Add-Content $log
"Log file: $log" | Add-Content $log

$seen = @{}
Get-Process | ForEach-Object { $seen[$_.Id] = $_.ProcessName }
$last = Get-Date

while ($true) {
  Start-Sleep -Milliseconds 700
  $now = Get-Date

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

  foreach ($ln in @("System", "Application", "Microsoft-Windows-TaskScheduler/Operational")) {
    Get-WinEvent -FilterHashtable @{ LogName = $ln; StartTime = $last; EndTime = $now } |
      Sort-Object TimeCreated |
      ForEach-Object {
        $m = (($_.Message -split "`r?`n")[0] -replace "\s+", " ").Trim()
        Add-Content $log ("{0:HH:mm:ss.fff} EVT log={1} level={2} provider={3} id={4} msg={5}" -f $_.TimeCreated, $ln, $_.LevelDisplayName, $_.ProviderName, $_.Id, $m)
      }
  }

  $last = $now
}
