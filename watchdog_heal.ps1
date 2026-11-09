<#
.SYNOPSIS
  Plant Monitor -- Autonomous Auto-Healing Watchdog
.DESCRIPTION
  Memantau kesehatan Nginx, PostgreSQL, Active Slot Waitress (/api/v1/health),
  dan ke-6 background workers secara berkala.
  Melakukan pemulihan otomatis (Self-Healing) seketika jika ada komponen yang padam.
#>

[CmdletBinding()]
param(
    [int]$IntervalSeconds = 30,
    [switch]$RunOnce
)

$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"
$NginxExe = "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2\nginx.exe"
$PythonExe = "$ProjectRoot\venv\Scripts\python.exe"
$LogFile = "$ProjectRoot\logs\auto_heal.log"

Set-Location -Path $ProjectRoot

# Pastikan folder logs ada
if (!(Test-Path "$ProjectRoot\logs")) {
    New-Item -ItemType Directory -Path "$ProjectRoot\logs" -Force | Out-Null
}

function Write-HealLog {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[$timestamp] [$Level] $Message"
    Write-Host $logLine
    try {
        Add-Content -Path $LogFile -Value $logLine -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch {}
}

function Check-And-Heal {
    # 1. Cek PostgreSQL
    try {
        $pg = Get-Service -Name "postgresql-x64-17" -ErrorAction SilentlyContinue
        if ($pg -and $pg.Status -ne "Running") {
            Write-HealLog "PostgreSQL terdeteksi MATI. Menyalakan kembali..." "WARN"
            Start-Service -Name "postgresql-x64-17"
            Start-Sleep -Seconds 3
        }
    } catch {
        Write-HealLog "Gagal memeriksa status PostgreSQL: $_" "ERROR"
    }

    # 2. Cek Nginx
    $nginxProc = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
    if (!$nginxProc) {
        Write-HealLog "Nginx terdeteksi MATI. Menyalakan Nginx..." "WARN"
        Start-Process -FilePath $NginxExe -WorkingDirectory "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2" -WindowStyle Hidden
        Start-Sleep -Seconds 2
    }

    # 3. Cek Health Slot Web Server via Nginx (Port 8000)
    $webHealthy = $false
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 4 -ErrorAction Stop
        if ($res.status -eq "healthy") {
            $webHealthy = $true
        }
    } catch {
        $webHealthy = $false
    }

    if (!$webHealthy) {
        Write-HealLog "Endpoint Web /api/v1/health GAGAL merespons! Memeriksa proses backend Waitress..." "WARN"
        
        $activeSlotFile = "$ProjectRoot\.active_slot.txt"
        $activeSlot = "blue"
        if (Test-Path $activeSlotFile) {
            $activeSlot = (Get-Content $activeSlotFile -Raw).Trim()
        }
        $targetPort = if ($activeSlot -eq "green") { 8082 } else { 8081 }
        
        $conn = Get-NetTCPConnection -LocalPort $targetPort -State Listen -ErrorAction SilentlyContinue
        if (!$conn) {
            Write-HealLog "Proses Waitress di slot $activeSlot (Port $targetPort) MATI! Menyalakan kembali..." "WARN"
            Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
                CommandLine = "$PythonExe $ProjectRoot\run_server.py --port=$targetPort --slot=$activeSlot"
                CurrentDirectory = $ProjectRoot
            } | Out-Null
            Start-Sleep -Seconds 4
        } else {
            Write-HealLog "Port $targetPort aktif tetapi healthcheck gagal. Memulai tindakan perbaikan..." "WARN"
            & $NginxExe -p "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2" -s reload
        }
    }

    # 4. Cek Ke-6 Background Workers (JUMO Sensor, History, Telegram, Anomali)
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\start_background_workers.ps1" | Out-Null
    } catch {
        Write-HealLog "Gagal menjalankan supervisor background workers: $_" "ERROR"
    }
}

Write-HealLog "Plant Monitor Watchdog & Auto-Healer Dimulai (Interval: $IntervalSeconds detik)..." "INFO"

if ($RunOnce) {
    Check-And-Heal
    Write-HealLog "Pemeriksaan Watchdog selesai (RunOnce)." "INFO"
} else {
    while ($true) {
        Check-And-Heal
        Start-Sleep -Seconds $IntervalSeconds
    }
}
