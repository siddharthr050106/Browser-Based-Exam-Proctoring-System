<# 
.SYNOPSIS
    Start the BEZP API Server (FastAPI).
.DESCRIPTION
    Runs the main FastAPI application on port 8000.
    
    WHAT THIS SERVICE DOES:
    - REST API endpoints for sessions, events, clips, users, exams
    - WebSocket endpoint for real-time proctor event streaming (NO video)
    - Redis subscriber: listens for detection events, persists to PostgreSQL
    - Automatic table creation in dev mode
    - JWT authentication + role-based access control
    
    REQUIRES: PostgreSQL, Redis (run start_infra.ps1 first)
#>
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BEZP — API Server (port 8000)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Endpoints:"
Write-Host "  POST /api/users/register     — Register user"
Write-Host "  POST /api/users/login        — Login (JWT)"
Write-Host "  POST /api/sessions/start     — Start exam session"
Write-Host "  POST /api/events/            — Record detection event"
Write-Host "  POST /api/clips/{s}/{e}      — Upload 30s clip (FLAG only)"
Write-Host "  GET  /api/exams/             — List exams"
Write-Host "  WS   /ws/proctor/{session}   — Proctor live event feed"
Write-Host "  GET  /health                 — Health check"
Write-Host "  GET  /docs                   — OpenAPI documentation"
Write-Host ""

Set-Location (Split-Path $PSScriptRoot -Parent)

# Copy .env if not exists
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example" -ForegroundColor Yellow
}

uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
