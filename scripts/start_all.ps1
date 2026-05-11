<#
.SYNOPSIS
    Start ALL BEZP services at once.
.DESCRIPTION
    Starts infrastructure, runs migrations, then launches API, detection worker, 
    and frontend in separate terminal windows.
    
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
    Browser → API (8000) → MinIO  (only 30s clips on FLAG events)
#>

$root = Split-Path $PSScriptRoot -Parent

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BEZP — Starting All Services" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Infrastructure
Write-Host "`n[1/5] Starting infrastructure (Docker)..." -ForegroundColor Yellow
Set-Location $root
docker-compose up -d
Start-Sleep -Seconds 3

# 2. Migrations
Write-Host "[2/5] Running database migrations..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
alembic upgrade head 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Migration skipped (may need PostgreSQL ready)" -ForegroundColor DarkYellow
}

# 3. API Server
Write-Host "[3/5] Starting API Server (port 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; uvicorn api.main:app --reload --port 8000"

# 4. Detection Worker
Write-Host "[4/5] Starting Detection Worker (port 8001)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; uvicorn detection.worker:app --reload --port 8001"

# 5. Frontend
Write-Host "[5/5] Starting Frontend (port 5173)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"

Start-Sleep -Seconds 2
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  All services started!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend:    http://localhost:5173" -ForegroundColor White
Write-Host "  API Docs:    http://localhost:8000/docs" -ForegroundColor White
Write-Host "  API Health:  http://localhost:8000/health" -ForegroundColor White
Write-Host "  Detection:   http://localhost:8001/health" -ForegroundColor White
Write-Host "  MinIO:       http://localhost:9001" -ForegroundColor White
Write-Host ""
