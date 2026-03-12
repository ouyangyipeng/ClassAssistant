#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup_processes() {
    echo "Cleaning up old processes..."
    pkill -f "uvicorn.*main:app" 2>/dev/null || true
    pkill -f "tauri.*dev" 2>/dev/null || true
    if pids="$(lsof -ti:8765 2>/dev/null)"; then
        if [[ -n "$pids" ]]; then
            echo "$pids" | xargs kill -9 2>/dev/null || true
        fi
    fi
}

cleanup_on_exit() {
    echo "Shutting down..."
    if [[ -n "$BACKEND_PID" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [[ -n "$FRONTEND_PID" ]]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    cleanup_processes
    exit 0
}

start_backend() {
    local python_bin="$ROOT_DIR/api-service/.venv/bin/python"

    if [[ ! -x "$python_bin" ]]; then
        echo "Missing Python virtualenv at $python_bin"
        echo "Run: cd api-service && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi

    echo "Starting FastAPI backend..."
    cd "$ROOT_DIR/api-service"
    "$python_bin" -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload &
    BACKEND_PID=$!
    cd "$ROOT_DIR"
    echo "Backend started on http://127.0.0.1:8765 (PID: $BACKEND_PID)"
}

start_frontend() {
    echo "Starting Tauri frontend..."
    cd "$ROOT_DIR/app-ui"
    npm run tauri dev &
    FRONTEND_PID=$!
    cd "$ROOT_DIR"
    echo "Frontend started (PID: $FRONTEND_PID)"
}

trap cleanup_on_exit INT TERM

echo "Starting ClassFox development environment..."
cleanup_processes
start_backend

echo "Waiting for backend to be ready..."
sleep 3

start_frontend

echo "Backend: http://127.0.0.1:8765"
echo "Press Ctrl+C to stop all services"

wait
