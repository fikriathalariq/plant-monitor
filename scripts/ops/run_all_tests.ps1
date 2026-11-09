<#
.SYNOPSIS
  Plant Monitor — Unified Enterprise Test Runner (Backend & Frontend QA)
.DESCRIPTION
  Runs the complete 6-layer automated test pyramid:
  1. Backend Django Unit Tests (PINN, Modbus, WAF/RBAC, Thermodynamics, OpenAPI Ninja)
  2. Code Coverage Analysis (coverage.py)
  3. Frontend JavaScript Unit Tests (Node.js test runner)
  4. Frontend Production Build Check (Vite)
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"
$PythonExe = "$ProjectRoot\venv\Scripts\python.exe"

Set-Location -Path $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  PLANT MONITOR -- AUTOMATED TESTING AND QA SUITE" -ForegroundColor Cyan
Write-Host "==========================================================`n" -ForegroundColor Cyan

# 1. Backend Django Unit Tests + Coverage
Write-Host "[1/3] Running Backend Django Unit Tests with Coverage..." -ForegroundColor Yellow
& $PythonExe -m coverage run --rcfile=.coveragerc manage.py test --noinput `
    monitoring.tests.test_pinn_engine `
    monitoring.tests.test_electricity_metrics `
    monitoring.tests.test_admin_and_routes `
    monitoring.tests.test_root_entrypoints `
    monitoring.tests.test_batch_analyzer `
    monitoring.tests.test_modbus_and_telemetry `
    monitoring.tests.test_steam_and_shift_calc `
    monitoring.tests.test_production_reports `
    monitoring.tests.test_security_and_rbac `
    monitoring.tests.test_ninja_api

if ($LASTEXITCODE -ne 0) {
    Write-Host "[-] Backend tests FAILED!" -ForegroundColor Red
    exit 1
}
Write-Host "[+] All Backend unit tests PASSED!`n" -ForegroundColor Green

# Coverage Report
Write-Host "[Coverage Report]" -ForegroundColor Cyan
& $PythonExe -m coverage report --rcfile=.coveragerc
Write-Host ""

# 2. Frontend JavaScript Unit Tests
Write-Host "[2/3] Running Frontend JavaScript Unit Tests (Node.js Test Runner)..." -ForegroundColor Yellow
Set-Location -Path "$ProjectRoot\frontend"
& npm.cmd test

if ($LASTEXITCODE -ne 0) {
    Write-Host "[-] Frontend unit tests FAILED!" -ForegroundColor Red
    exit 1
}
Write-Host "[+] All Frontend unit tests PASSED!`n" -ForegroundColor Green

# 3. Frontend Production Build Check
Write-Host "[3/3] Verifying Frontend Production Build..." -ForegroundColor Yellow
& npm.cmd run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "[-] Frontend build FAILED!" -ForegroundColor Red
    exit 1
}
Write-Host "[+] Frontend production bundle built successfully!`n" -ForegroundColor Green

Set-Location -Path $ProjectRoot
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  ALL TESTS PASSED -- 100% GREEN (ZERO REGRESSIONS)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
