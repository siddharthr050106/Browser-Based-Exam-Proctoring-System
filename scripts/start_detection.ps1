<#
.SYNOPSIS
    Start the BEZP Detection Worker (port 8001).
.DESCRIPTION
    Runs the detection worker as a separate FastAPI service.
    
    WHAT THIS SERVICE DOES:
    - Receives video frames from the client browser (base64 JPEG)
    - Runs the full detection pipeline on each frame:
        1. Face Gate    — MediaPipe face presence + identity check
        2. YOLO         — Phone detection + person count (YOLOv8-nano)
        3. Background   — SSIM drift detection (every 10 min)
        4. Gaze         — Head pose estimation (solvePnP stub → future MLP)
        5. Anomaly      — Threshold-based scoring (stub → future One-Class SVM)
        6. Rule Engine  — Escalation tier logic (INFO/WARNING/FLAG/CRITICAL)
    - Publishes detection events to Redis (pub/sub)
    - The API server subscribes to Redis and persists events to PostgreSQL
    
    REQUIRES: Redis (run start_infra.ps1 first)
    NOTE: This is a CPU-intensive service. Runs ML models (MediaPipe, YOLO).
#>
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BEZP — Detection Worker (port 8001)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Endpoints:"
Write-Host "  POST /detect/frame           — Process a video frame"
Write-Host "  POST /detect/browser-event   — Process tab switch/blur"
Write-Host "  POST /detect/end-session/{id} — Clean up session pipeline"
Write-Host "  GET  /health                 — Health check"
Write-Host ""
Write-Host "Pipeline: Face -> YOLO -> Background -> Gaze -> Anomaly -> Rules"
Write-Host ""

Set-Location (Split-Path $PSScriptRoot -Parent)
uvicorn detection.worker:app --reload --host 0.0.0.0 --port 8001
