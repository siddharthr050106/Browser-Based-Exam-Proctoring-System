<#
.SYNOPSIS
    Start ALL BEZP services — Docker infrastructure + API + Detection + Frontend.
.DESCRIPTION
    Single script to boot the entire system.

    SERVICE MAP:
    ┌──────────────────────────────────────────────────────────────┐
    │  Service            Port    What It Does                    │
    │  ─────────────────  ──────  ─────────────────────────────── │
    │  PostgreSQL         5432    Database storage                │
    │  Redis              6379    Detection ↔ API pub/sub bridge  │
    │  MinIO              9000    30s video clip storage (S3)     │
    │  API Server         8000    REST + WebSocket + DB writes    │
    │  Detection Worker   8001    ML pipeline (face/YOLO/gaze)   │
    │  Frontend           5173    React UI (student/proctor/admin)│
    └──────────────────────────────────────────────────────────────┘

    DATA FLOW:
    Browser → Detection Worker (8001) → Redis → API (8000) → PostgreSQL
    Browser ← WebSocket ← API (8000) ← Redis ← Detection Worker
    Browser → API (8000) → local/MinIO  (only 30s clips on FLAG events)

.EXAMPLE
    .\scripts\start_all.ps1
    .\scripts\start_all.ps1 -SkipDocker   # Skip docker if already running
#>

param(
    [switch]$SkipDocker
)

$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   BEZP — Browser Exam Proctoring System  ║" -ForegroundColor Cyan
Write-Host "║         Starting All Services             ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ──────────────────────────────────────────
# Step 1: Docker Infrastructure
# ──────────────────────────────────────────
if (-not $SkipDocker) {
    Write-Host "[1/5] Starting Docker infrastructure..." -ForegroundColor Yellow

    # Check if Docker is running
    $dockerCheck = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
        exit 1
    }

    Set-Location $root
    docker-compose up -d 2>&1 | Out-Null

    # Wait for PostgreSQL to be ready
    Write-Host "  Waiting for PostgreSQL..." -ForegroundColor DarkGray
    $retries = 0
    while ($retries -lt 15) {
        $pgReady = docker exec bezp-postgres pg_isready -U bezp -d bezp_db 2>&1
        if ($pgReady -match "accepting connections") { break }
        Start-Sleep -Seconds 1
        $retries++
    }
    if ($retries -ge 15) {
        Write-Host "  WARNING: PostgreSQL may not be ready yet" -ForegroundColor DarkYellow
    } else {
        Write-Host "  PostgreSQL ready" -ForegroundColor Green
    }

    # Wait for Redis
    Write-Host "  Waiting for Redis..." -ForegroundColor DarkGray
    $retries = 0
    while ($retries -lt 10) {
        $redisReady = docker exec bezp-redis redis-cli ping 2>&1
        if ($redisReady -match "PONG") { break }
        Start-Sleep -Seconds 1
        $retries++
    }
    if ($retries -lt 10) {
        Write-Host "  Redis ready" -ForegroundColor Green
    }

    Write-Host "  Docker infrastructure OK" -ForegroundColor Green
} else {
    Write-Host "[1/5] Skipping Docker (--SkipDocker)" -ForegroundColor DarkGray
}

# ──────────────────────────────────────────
# Step 2: Environment file
# ──────────────────────────────────────────
Write-Host "[2/5] Checking environment..." -ForegroundColor Yellow
Set-Location $root
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  Created .env from .env.example" -ForegroundColor DarkGray
    }
}
Write-Host "  Environment OK" -ForegroundColor Green

# ──────────────────────────────────────────
# Step 3: API Server (port 8000)
# ──────────────────────────────────────────
Write-Host "[3/5] Starting API Server (port 8000)..." -ForegroundColor Yellow

# Kill any existing process on port 8000
$existing = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    Stop-Process -Id (Get-Process -Id $existing.OwningProcess).Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Start-Process powershell -ArgumentList @(
    "-NoProfile", "-NoExit", "-Command",
    "Set-Location '$root'; `$Host.UI.RawUI.WindowTitle = 'BEZP API (8000)'; Write-Host 'Starting API Server...' -ForegroundColor Cyan; uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"
)
Write-Host "  API Server starting..." -ForegroundColor Green

# ──────────────────────────────────────────
# Step 4: Detection Worker (port 8001)
# ──────────────────────────────────────────
Write-Host "[4/5] Starting Detection Worker (port 8001)..." -ForegroundColor Yellow

$existing = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    Stop-Process -Id (Get-Process -Id $existing.OwningProcess).Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Start-Process powershell -ArgumentList @(
    "-NoProfile", "-NoExit", "-Command",
    "Set-Location '$root'; `$Host.UI.RawUI.WindowTitle = 'BEZP Detection (8001)'; Write-Host 'Starting Detection Worker...' -ForegroundColor Cyan; uvicorn detection.worker:app --host 0.0.0.0 --port 8001"
)
Write-Host "  Detection Worker starting..." -ForegroundColor Green

# ──────────────────────────────────────────
# Step 5: Frontend (port 5173)
# ──────────────────────────────────────────
Write-Host "[5/5] Starting Frontend (port 5173)..." -ForegroundColor Yellow

Start-Process powershell -ArgumentList @(
    "-NoProfile", "-NoExit", "-Command",
    "Set-Location '$root\frontend'; `$Host.UI.RawUI.WindowTitle = 'BEZP Frontend (5173)'; Write-Host 'Starting Frontend...' -ForegroundColor Cyan; npm run dev"
)
Write-Host "  Frontend starting..." -ForegroundColor Green

# ──────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────
Write-Host ""
Write-Host "Waiting for services to initialize..." -ForegroundColor DarkGray
Start-Sleep -Seconds 5

# Check API
try {
    $apiHealth = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5 -ErrorAction SilentlyContinue
    if ($apiHealth.status -eq "healthy") {
        Write-Host "  API Server:      HEALTHY" -ForegroundColor Green
    }
} catch {
    Write-Host "  API Server:      STARTING (may take a few seconds)" -ForegroundColor Yellow
}

# Check Detection Worker
try {
    $detHealth = Invoke-RestMethod -Uri "http://localhost:8001/health" -TimeoutSec 5 -ErrorAction SilentlyContinue
    if ($detHealth.status -eq "healthy") {
        Write-Host "  Detection Worker: HEALTHY" -ForegroundColor Green
    }
} catch {
    Write-Host "  Detection Worker: STARTING (may take a few seconds)" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║         All Services Launched!            ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  URLS:" -ForegroundColor White
Write-Host "  ────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  Frontend:      http://localhost:5173" -ForegroundColor Cyan
Write-Host "  API Docs:      http://localhost:8000/docs" -ForegroundColor White
Write-Host "  API Health:    http://localhost:8000/health" -ForegroundColor White
Write-Host "  Detection:     http://localhost:8001/health" -ForegroundColor White
Write-Host "  MinIO Console: http://localhost:9001" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  TERMINAL WINDOWS:" -ForegroundColor White
Write-Host "  ────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  3 PowerShell windows opened:" -ForegroundColor DarkGray
Write-Host "    - 'BEZP API (8000)'" -ForegroundColor DarkGray
Write-Host "    - 'BEZP Detection (8001)'" -ForegroundColor DarkGray
Write-Host "    - 'BEZP Frontend (5173)'" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  To stop all: close the 3 terminal windows + run:" -ForegroundColor DarkGray
Write-Host "    docker-compose down" -ForegroundColor DarkYellow
Write-Host ""
