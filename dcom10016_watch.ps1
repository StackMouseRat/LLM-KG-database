$ErrorActionPreference = "SilentlyContinue"

function Test-IsAdmin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = [Security.Principal.WindowsPrincipal]::new($id)
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
  Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$PSCommandPath`""
  )
  exit
}

$desktop = [Environment]::GetFolderPath("Desktop")
$log = Join-Path $desktop ("dcom10016_watch_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

"START $(Get-Date)" | Out-File -FilePath $log -Encoding utf8
"Watching System log for Event ID 10016..." | Add-Content $log
"Log file: $log" | Add-Content $log

Write-Host "Watching 10016 events..." -ForegroundColor Cyan
Write-Host "Log: $log" -ForegroundColor Yellow
Write-Host "Keep this window open. Press Ctrl+C to stop." -ForegroundColor Green

$lastCheck = (Get-Date).AddSeconds(-2)
$lastRecordId = -1L

while ($true) {
  $now = Get-Date
  $evts = Get-WinEvent -FilterHashtable @{
    LogName = "System"
    Id = 10016
    StartTime = $lastCheck
    EndTime = $now
  } | Sort-Object TimeCreated

  foreach ($ev in $evts) {
    if ($ev.RecordId -le $lastRecordId) { continue }
    $lastRecordId = $ev.RecordId

    $msg = $ev.Message
    $ids = [regex]::Matches($msg, '\{[0-9A-Fa-f\-]{36}\}') | ForEach-Object { $_.Value }
    $clsid = if ($ids.Count -ge 1) { $ids[0] } else { "" }
    $appid = if ($ids.Count -ge 2) { $ids[1] } else { "" }

    $header = "[{0}] EVT10016 CLSID={1} APPID={2}" -f $ev.TimeCreated.ToString("HH:mm:ss.fff"), $clsid, $appid
    $header | Tee-Object -FilePath $log -Append | Out-Host

    $watchNames = 'msedge|msedgewebview2|SearchHost|StartMenuExperienceHost|ShellExperienceHost|Widgets|RuntimeBroker|TextInputHost|dwm'
    $procs = Get-Process | Where-Object { $_.ProcessName -match $watchNames } |
      Sort-Object ProcessName |
      Select-Object ProcessName, Id, CPU, StartTime

    if ($procs) {
      ($procs | Format-Table -AutoSize | Out-String) | Tee-Object -FilePath $log -Append | Out-Host
    } else {
      "No watched processes found at this moment." | Tee-Object -FilePath $log -Append | Out-Host
    }
    "----" | Add-Content $log
  }

  $lastCheck = $now
  Start-Sleep -Milliseconds 700
}
