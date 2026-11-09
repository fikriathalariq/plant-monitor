<#
.SYNOPSIS
  Zero-Downtime Blue-Green Deployment Script for Plant-Monitor.
.DESCRIPTION
  Opsi A: 1 Codebase, Dual Isolated Slots (Blue: 8081, Green: 8082).
  Menjalankan migrasi database, build frontend, pengujian healthcheck di slot target,
  dan pengalihan trafik Nginx tanpa memutuskan koneksi pengguna (Zero Downtime).
#>

[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$SkipMigrate,
    [string]$ForceSlot = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"
$NginxConfDir = "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2\conf"
$NginxExe = "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2\nginx.exe"
$PythonExe = "$ProjectRoot\venv\Scripts\python.exe"

Set-Location -Path $ProjectRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " PLANT MONITOR -- ZERO-DOWNTIME BLUE-GREEN DEPLOYMENT    " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# ── 1. Deteksi Slot Aktif & Slot Target ──────────────────────────
$activeSlotFile = "$ProjectRoot\.active_slot.txt"
$activeSlot = "blue"
if (Test-Path $activeSlotFile) {
    $activeSlot = (Get-Content $activeSlotFile -Raw).Trim()
} elseif (Test-Path "$NginxConfDir\active_upstream.conf") {
    $upContent = Get-Content "$NginxConfDir\active_upstream.conf" -Raw
    if ($upContent -match "8082") { $activeSlot = "green" }
}

if ($ForceSlot -in @("blue", "green")) {
    $targetSlot = $ForceSlot
} else {
    $targetSlot = if ($activeSlot -eq "blue") { "green" } else { "blue" }
}

$targetPort = if ($targetSlot -eq "blue") { 8081 } else { 8082 }
$oldPort = if ($activeSlot -eq "blue") { 8081 } else { 8082 }
$targetDistDir = "$ProjectRoot\frontend\dist_$targetSlot"

Write-Host "[1/7] Slot Aktif   : $activeSlot (Port: $oldPort)" -ForegroundColor Yellow
Write-Host "      Target Rilis : $targetSlot (Port: $targetPort)" -ForegroundColor Green

# ── 2. Buat Snapshot Backup Kode Python (~5 MB) ──────────────────
Write-Host "`n[2/7] Mengarsipkan Snapshot Kode Backend..." -ForegroundColor Gray
$snapshotDir = "$ProjectRoot\.snapshots"
if (!(Test-Path $snapshotDir)) { New-Item -ItemType Directory -Path $snapshotDir -Force | Out-Null }
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$snapshotZip = "$snapshotDir\backend_prev_$timestamp.zip"
$lastWorkingZip = "$snapshotDir\backend_last_working.zip"

try {
    $filesToZip = Get-ChildItem -Path "monitoring", "plant_monitor" -Recurse -File | Where-Object { $_.FullName -notmatch "__pycache__" }
    Compress-Archive -Path $filesToZip.FullName -DestinationPath $snapshotZip -Force
    Copy-Item -Path $snapshotZip -Destination $lastWorkingZip -Force
    Write-Host "      OK - Snapshot tersimpan di: $snapshotZip" -ForegroundColor Green
} catch {
    Write-Warning "      Gagal membuat zip snapshot (abaikan): $_"
}

# ── 3. Jalankan System Check & Database Migration ────────────────
if (!$SkipMigrate) {
    Write-Host "`n[3/7] Menjalankan Database Check dan Migration..." -ForegroundColor Gray
    & $PythonExe manage.py check
    if ($LASTEXITCODE -ne 0) { throw "Django system check gagal! Deployment dibatalkan." }
    
    & $PythonExe manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "Migrasi database gagal! Deployment dibatalkan." }
    Write-Host "      OK - Database migrasi tuntas (Backward-Compatible)." -ForegroundColor Green
} else {
    Write-Host "`n[3/7] Melewati Database Migration (-SkipMigrate)" -ForegroundColor DarkGray
}

# ── 4. Build Frontend & Salin ke Target Dist Slot ────────────────
if (!$SkipBuild) {
    Write-Host "`n[4/7] Membangun Frontend Bundle (Vite)..." -ForegroundColor Gray
    Set-Location -Path "$ProjectRoot\frontend"
    cmd.exe /c "npm.cmd run build"
    if ($LASTEXITCODE -ne 0) {
        Set-Location -Path $ProjectRoot
        throw "Vite build gagal! Pengguna aktif di slot $activeSlot tetap aman. Deployment dibatalkan."
    }
    Set-Location -Path $ProjectRoot
    
    # Salin ke slot target (tetap menyertakan chunk lama)
    if (!(Test-Path $targetDistDir)) { New-Item -ItemType Directory -Path $targetDistDir -Force | Out-Null }
    Copy-Item -Path "$ProjectRoot\frontend\dist\*" -Destination $targetDistDir -Recurse -Force
    Write-Host "      OK - Frontend siap di: $targetDistDir" -ForegroundColor Green
} else {
    Write-Host "`n[4/7] Melewati Build Frontend (-SkipBuild)" -ForegroundColor DarkGray
}

# ── 5. Nyalakan Waitress di Slot Target ───────────────────────────
Write-Host "`n[5/7] Menyalakan Waitress di Slot $targetSlot (Port: $targetPort)..." -ForegroundColor Gray

# Bersihkan proses lama jika ada yang menduduki port target
$existingConn = Get-NetTCPConnection -LocalPort $targetPort -State Listen -ErrorAction SilentlyContinue
if ($existingConn) {
    Write-Host "      Membersihkan proses lama di port $targetPort..." -ForegroundColor DarkGray
    taskkill /F /T /PID $existingConn.OwningProcess 2>$null
    Start-Sleep -Seconds 1
}

# Spawn Waitress proses baru
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "$PythonExe $ProjectRoot\run_server.py --port=$targetPort --slot=$targetSlot"
    CurrentDirectory = $ProjectRoot
} | Out-Null

# ── 6. Pre-Flight Healthcheck Probe ──────────────────────────────
Write-Host "`n[6/7] Menguji Kesiapan Slot $targetSlot (/api/v1/health)..." -ForegroundColor Gray
$healthy = $false
$maxRetries = 30
for ($i = 1; $i -le $maxRetries; $i++) {
    Start-Sleep -Seconds 1
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:$targetPort/api/v1/health?flush_cache=1" -TimeoutSec 3 -ErrorAction Stop
        if ($res.status -eq "healthy") {
            $healthy = $true
            Write-Host "      OK - Slot $targetSlot SEHAT! (DB Latency: $($res.database_latency_ms)ms)" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "      Menunggu kesiapan slot $targetSlot (Percobaan $i/$maxRetries)..." -ForegroundColor DarkGray
    }
}

if (!$healthy) {
    # Emergency abort: matikan proses target yang gagal, slot aktif tetap utuh
    $failConn = Get-NetTCPConnection -LocalPort $targetPort -State Listen -ErrorAction SilentlyContinue
    if ($failConn) { taskkill /F /T /PID $failConn.OwningProcess 2>$null }
    throw "Gagal memverifikasi kesehatan slot $targetSlot! Slot $activeSlot tetap berjalan aman tanpa gangguan."
}

# ── 7. Pengalihan Trafik Nginx (The Flip ~0 ms) ───────────────────
Write-Host "`n[7/7] Mengalihkan Trafik Nginx ke Slot $targetSlot..." -ForegroundColor Gray
$upText = "upstream app_backend {`n    server 127.0.0.1:$targetPort;`n    keepalive 32;`n}"
$feText = "root C:/Users/HP/Documents/Plant-Monitor/plant-monitor/frontend/dist_$targetSlot;"

# Tulis UTF-8 NO-BOM (Nginx menolak BOM UTF-8)
[System.IO.File]::WriteAllText("$NginxConfDir\active_upstream.conf", $upText)
[System.IO.File]::WriteAllText("$NginxConfDir\active_frontend.conf", $feText)

& $NginxExe -p "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2" -s reload
Start-Sleep -Seconds 1

# Catat slot aktif
Set-Content -Path $activeSlotFile -Value $targetSlot -Encoding ASCII

# Draining: Beri waktu 5 detik agar request yang sedang diproses di slot lama selesai
Write-Host "      Koneksi Nginx berhasil dialihkan ke $targetSlot!" -ForegroundColor Green
Write-Host "      Menunggu 5 detik (connection draining) untuk slot lama..." -ForegroundColor DarkGray
Start-Sleep -Seconds 5

# Matikan proses Waitress di slot lama untuk menghemat RAM
$oldConn = Get-NetTCPConnection -LocalPort $oldPort -State Listen -ErrorAction SilentlyContinue
if ($oldConn -and $oldPort -ne $targetPort) {
    taskkill /F /T /PID $oldConn.OwningProcess 2>$null
    Write-Host "      Slot lama ($activeSlot : $oldPort) dimatikan dengan aman." -ForegroundColor DarkGray
}

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host " RILIS SELESAI (ZERO DOWNTIME)!                         " -ForegroundColor Green
Write-Host " Slot Aktif Sekarang : $($targetSlot.ToUpper()) (Port: $targetPort)" -ForegroundColor Green
Write-Host " Tampilan Frontend   : dist_$targetSlot" -ForegroundColor Green
Write-Host " Untuk rollback darurat, jalankan: ./rollback.ps1       " -ForegroundColor Yellow
Write-Host "========================================================`n" -ForegroundColor Cyan
