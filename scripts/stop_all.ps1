<#
.SYNOPSIS
    Stop ALL BEZP services — kills API, Detection, Frontend processes and Docker containers.
.EXAMPLE
    .\scripts\stop_all.ps1
#>

$root = Split-Path $PSScriptRoot -Parent

Write-Host ""
Write-Host "Stopping all BEZP services..." -ForegroundColor Yellow

# Kill processes on service ports
$ports = @(8000, 8001, 5173)
foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        try {
            $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            if ($proc -and $proc.Name -ne "System") {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                Write-Host "  Stopped $($proc.Name) on port $port" -ForegroundColor DarkGray
            }
        } catch {}
    }
}

# Stop Docker containers
Write-Host "  Stopping Docker containers..." -ForegroundColor DarkGray
Set-Location $root
docker-compose down 2>&1 | Out-Null

Write-Host ""
Write-Host "All BEZP services stopped." -ForegroundColor Green
Write-Host ""
