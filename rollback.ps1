<#
.SYNOPSIS
  Instant 1-Second Emergency Rollback Script for Plant-Monitor.
.DESCRIPTION
  Memutar balik lalu lintas Nginx ke slot sebelumnya secara instan (1 detik).
#>

[CmdletBinding()]
param(
    [switch]$RestoreCode
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"
$NginxConfDir = "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2\conf"
$NginxExe = "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2\nginx.exe"
$PythonExe = "$ProjectRoot\venv\Scripts\python.exe"

Set-Location -Path $ProjectRoot

Write-Host "========================================================" -ForegroundColor Red
Write-Host " PLANT MONITOR -- EMERGENCY 1-SECOND ROLLBACK           " -ForegroundColor Red
Write-Host "========================================================" -ForegroundColor Red

# 1. Deteksi Slot yang Sedang Aktif
$activeSlotFile = "$ProjectRoot\.active_slot.txt"
$activeSlot = "green"
if (Test-Path $activeSlotFile) {
    $activeSlot = (Get-Content $activeSlotFile -Raw).Trim()
} elseif (Test-Path "$NginxConfDir\active_upstream.conf") {
    $upContent = Get-Content "$NginxConfDir\active_upstream.conf" -Raw
    if ($upContent -match "8081") { $activeSlot = "blue" }
}

$rollbackSlot = if ($activeSlot -eq "blue") { "green" } else { "blue" }
$rollbackPort = if ($rollbackSlot -eq "blue") { 8081 } else { 8082 }
$brokenPort = if ($activeSlot -eq "blue") { 8081 } else { 8082 }

Write-Host ("Rollback Slot Bermasalah : " + $activeSlot + " (Port: " + $brokenPort + ")") -ForegroundColor Yellow
Write-Host ("Rollback Kembali ke Slot : " + $rollbackSlot + " (Port: " + $rollbackPort + ")") -ForegroundColor Green

# 2. Opsional: Pulihkan file kode backend jika diminta (-RestoreCode)
if ($RestoreCode) {
    $lastWorkingZip = "$ProjectRoot\.snapshots\backend_last_working.zip"
    if (Test-Path $lastWorkingZip) {
        Write-Host "Memulihkan file kode dari snapshot: $lastWorkingZip..." -ForegroundColor Yellow
        Expand-Archive -Path $lastWorkingZip -DestinationPath $ProjectRoot -Force
        Write-Host "File kode backend berhasil dipulihkan." -ForegroundColor Green
    }
}

# 3. Pastikan slot rollback menyala
$conn = Get-NetTCPConnection -LocalPort $rollbackPort -State Listen -ErrorAction SilentlyContinue
if (!$conn) {
    Write-Host ("Menyalakan slot " + $rollbackSlot + " (Port: " + $rollbackPort + ")...") -ForegroundColor Gray
    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = "$PythonExe $ProjectRoot\run_server.py --port=$rollbackPort --slot=$rollbackSlot"
        CurrentDirectory = $ProjectRoot
    } | Out-Null
    
    # Tunggu healthcheck
    $healthy = $false
    for ($i = 1; $i -le 15; $i++) {
        Start-Sleep -Seconds 1
        try {
            $res = Invoke-RestMethod -Uri "http://127.0.0.1:$rollbackPort/api/v1/health?flush_cache=1" -TimeoutSec 2 -ErrorAction Stop
            if ($res.status -eq "healthy") { $healthy = $true; break }
        } catch {}
    }
    if (!$healthy) { throw "Gagal menyalakan slot rollback $rollbackSlot!" }
}

# 4. Swap Nginx seketika (The Flip ~0 ms)
Write-Host ("Memutar Nginx ke slot " + $rollbackSlot + "...") -ForegroundColor Gray
$upFile = "$NginxConfDir\active_upstream.conf"
$feFile = "$NginxConfDir\active_frontend.conf"

$upText = "upstream app_backend {`n    server 127.0.0.1:" + $rollbackPort + ";`n    keepalive 32;`n}"
$feText = "root C:/Users/HP/Documents/Plant-Monitor/plant-monitor/frontend/dist_" + $rollbackSlot + ";"

[System.IO.File]::WriteAllText($upFile, $upText)
[System.IO.File]::WriteAllText($feFile, $feText)

& $NginxExe -p "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2" -s reload
Start-Sleep -Seconds 1

Set-Content -Path $activeSlotFile -Value $rollbackSlot -Encoding ASCII

# 5. Matikan slot yang bermasalah
$brokenConn = Get-NetTCPConnection -LocalPort $brokenPort -State Listen -ErrorAction SilentlyContinue
if ($brokenConn -and ($brokenPort -ne $rollbackPort)) {
    taskkill /F /T /PID $brokenConn.OwningProcess 2>$null
    Write-Host ("Slot bermasalah (" + $activeSlot + " : " + $brokenPort + ") telah dimatikan.") -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host (" ROLLBACK BERHASIL! SISTEM KEMBALI STABIL DI " + $rollbackSlot.ToUpper()) -ForegroundColor Green
Write-Host (" Slot Aktif Sekarang: " + $rollbackSlot.ToUpper() + " (Port: " + $rollbackPort + ")") -ForegroundColor Green
Write-Host (" Tampilan Frontend  : dist_" + $rollbackSlot) -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
