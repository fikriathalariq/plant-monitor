<#
.SYNOPSIS
  Singleton Process Supervisor for Plant-Monitor Background Workers.
.DESCRIPTION
  Memastikan ke-6 worker latar belakang (sensor JUMO, log history, telegram bot, anomali)
  berjalan dengan tepat 1 instance (mencegah duplikasi log atau bentrokan bot Telegram).
#>

$ProjectRoot = "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"
$PythonExe = "$ProjectRoot\venv\Scripts\python.exe"

Set-Location -Path $ProjectRoot

function Ensure-Worker {
    param(
        [string]$Name,
        [string]$FilterPattern,
        [scriptblock]$StartAction
    )

    $existing = Get-CimInstance Win32_Process -Filter "CommandLine like '%$FilterPattern%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -notmatch "powershell" -and $_.CommandLine -notmatch "wmic" }

    if ($existing) {
        $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ", "
        Write-Host "  [OK] $Name sudah berjalan (PID: $pids)." -ForegroundColor Green
    } else {
        & $StartAction
        Write-Host "  [+] $Name berhasil dinyalakan." -ForegroundColor Yellow
    }
}

Write-Host "Memeriksa status background workers..." -ForegroundColor Cyan

# 1. JUMO Realtime
Ensure-Worker -Name "JUMO Realtime (Sensor)" -FilterPattern "manage.py jumo_realtime" -StartAction {
    Start-Process -FilePath $PythonExe -ArgumentList "manage.py jumo_realtime" -WorkingDirectory $ProjectRoot -WindowStyle Minimized
}

# 2. Log Minute History
Ensure-Worker -Name "Log Minute History" -FilterPattern "manage.py log_minute_history" -StartAction {
    Start-Process -FilePath $PythonExe -ArgumentList "manage.py log_minute_history" -WorkingDirectory $ProjectRoot -WindowStyle Minimized
}

# 3. Anomaly Detection Loop
Ensure-Worker -Name "Kalkulasi Anomali" -FilterPattern "loop_anomalies.bat" -StartAction {
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$ProjectRoot\scripts\ops\loop_anomalies.bat`"" -WorkingDirectory $ProjectRoot -WindowStyle Minimized
}

# 4. Check Device Health (No Signal)
Ensure-Worker -Name "Device Health (No Signal)" -FilterPattern "manage.py check_device_health" -StartAction {
    Start-Process -FilePath $PythonExe -ArgumentList "manage.py check_device_health" -WorkingDirectory $ProjectRoot -WindowStyle Minimized
}

# 5. Telegram Status Changes
Ensure-Worker -Name "Telegram Status Notify" -FilterPattern "manage.py notify_status_changes" -StartAction {
    Start-Process -FilePath $PythonExe -ArgumentList "manage.py notify_status_changes" -WorkingDirectory $ProjectRoot -WindowStyle Minimized
}

# 6. Telegram Bot
Ensure-Worker -Name "Telegram Bot Listener" -FilterPattern "manage.py telegram_bot" -StartAction {
    Start-Process -FilePath $PythonExe -ArgumentList "manage.py telegram_bot" -WorkingDirectory $ProjectRoot -WindowStyle Minimized
}

Write-Host "Seluruh background workers siap.`n" -ForegroundColor Cyan
