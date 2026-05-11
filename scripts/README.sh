#!/usr/bin/env bash
# ============================================================
# BEZP — Service Runner Scripts
# ============================================================
#
# SERVICE ARCHITECTURE:
#
#   ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
#   │   Frontend   │    │   API Server     │    │  Detection   │
#   │  (Vite dev)  │───▶│  (FastAPI)       │◀───│   Worker     │
#   │  port 5173   │    │  port 8000       │    │  port 8001   │
#   └──────────────┘    └───────┬──────────┘    └──────┬───────┘
#                               │                       │
#                        ┌──────▼──────────────────────▼──────┐
#                        │           Redis (pub/sub)           │
#                        │           port 6379                 │
#                        └──────────────────────────────────────┘
#                               │
#                        ┌──────▼──────┐    ┌─────────────┐
#                        │ PostgreSQL  │    │    MinIO     │
#                        │ port 5432   │    │  port 9000   │
#                        └─────────────┘    └─────────────┘
#
# WHAT EACH SERVICE DOES:
#
# 1. PostgreSQL  — Stores all data (users, exams, sessions, events, gaze)
# 2. Redis       — Pub/sub bridge between detection worker and API
# 3. MinIO       — S3-compatible storage for 30-second video clips
# 4. API Server  — REST + WebSocket endpoints, DB access, proctor feed
# 5. Detection   — Runs ML pipeline (face, YOLO, gaze), publishes to Redis
# 6. Frontend    — React app served by Vite dev server
# ============================================================

echo "This file is documentation only. Use the scripts below."
