<# 
.SYNOPSIS
    Start all BEZP infrastructure services (PostgreSQL, Redis, MinIO).
.DESCRIPTION
    Uses Docker Compose to start the database, cache, and object storage.
    These must be running before the API or detection worker can start.
#>
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BEZP — Starting Infrastructure" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Services:"
Write-Host "  PostgreSQL  :5432  — Database (users, exams, sessions, events)"
Write-Host "  Redis       :6379  — Pub/sub bridge (detection <-> API)"
Write-Host "  MinIO       :9000  — Object storage (30-second video clips)"
Write-Host ""

Set-Location (Split-Path $PSScriptRoot -Parent)
docker-compose up -d

Write-Host ""
Write-Host "Infrastructure is running." -ForegroundColor Green
Write-Host "MinIO Console: http://localhost:9001 (admin/minioadmin)" -ForegroundColor Yellow
