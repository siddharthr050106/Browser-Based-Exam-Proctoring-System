<#
.SYNOPSIS
    Start the BEZP Frontend (Vite dev server, port 5173).
.DESCRIPTION
    Runs the React + Vite development server.
    
    WHAT THIS SERVICE DOES:
    - Serves the React frontend application
    - Hot module replacement for development
    - Proxies /api/* requests to the API server (port 8000)
    - Proxies /ws/* WebSocket requests to the API server
    
    PAGES:
    - /login, /register          — Authentication
    - /student/*                 — Student portal (dashboard, exams, session)
    - /proctor/*                 — Proctor dashboard (live sessions, monitoring)
    - /admin/*                   — Admin panel (exams, users, reports)
#>
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BEZP — Frontend (port 5173)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pages:"
Write-Host "  /login              — Sign in"
Write-Host "  /student            — Student dashboard"
Write-Host "  /student/exams      — Available exams"
Write-Host "  /proctor            — Live session monitoring"
Write-Host "  /admin              — System administration"
Write-Host ""

Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "frontend")
npm run dev
