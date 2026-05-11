<#
.SYNOPSIS
    Run database migrations using Alembic.
.DESCRIPTION
    Applies all pending migrations to PostgreSQL.
    REQUIRES: PostgreSQL running (run start_infra.ps1 first)
#>
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BEZP — Database Migration" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location (Split-Path $PSScriptRoot -Parent)
alembic upgrade head

Write-Host ""
Write-Host "Migration complete." -ForegroundColor Green
