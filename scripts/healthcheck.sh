#!/usr/bin/env bash
#
# Weather-Dome service healthcheck and auto-restart script.
# Intended to run every 30 minutes via cron with flock to prevent overlap.
#

set -euo pipefail

PROJECT_DIR="/opt/weather-dome"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/healthcheck.log"
LOCKFILE="/tmp/weatherdome-healthcheck.lock"
VENV_DIR="${PROJECT_DIR}/.venv"

BACKEND_URL="http://localhost:8000/health"
FRONTEND_URL="http://localhost:5173"

RESTART_WAIT=5

mkdir -p "$LOG_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

# Acquire lock (non-blocking). Exit if another instance is running.
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    log "SKIP: another healthcheck instance is already running"
    exit 0
fi

log "INFO: healthcheck started"

backend_up=true
frontend_up=true

# --- Check backend ---
if curl -sf --max-time 10 "$BACKEND_URL" > /dev/null 2>&1; then
    log "INFO: backend is UP"
else
    backend_up=false
    log "WARN: backend is DOWN — attempting restart"

    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"

    cd "${PROJECT_DIR}/backend"
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 \
        >> "${LOG_DIR}/backend.log" 2>&1 &

    log "INFO: backend restart command issued (pid $!)"
fi

# --- Check frontend ---
if curl -sf --max-time 10 "$FRONTEND_URL" > /dev/null 2>&1; then
    log "INFO: frontend is UP"
else
    frontend_up=false
    log "WARN: frontend is DOWN — attempting restart"

    cd "${PROJECT_DIR}/frontend"
    nohup npm run dev -- --host 0.0.0.0 --port 5173 \
        >> "${LOG_DIR}/frontend.log" 2>&1 &

    log "INFO: frontend restart command issued (pid $!)"
fi

# --- Re-check restarted services ---
if ! $backend_up || ! $frontend_up; then
    log "INFO: waiting ${RESTART_WAIT}s for services to start"
    sleep "$RESTART_WAIT"

    if ! $backend_up; then
        if curl -sf --max-time 10 "$BACKEND_URL" > /dev/null 2>&1; then
            log "INFO: backend restarted successfully"
        else
            log "ERROR: backend failed to come up after restart"
        fi
    fi

    if ! $frontend_up; then
        if curl -sf --max-time 10 "$FRONTEND_URL" > /dev/null 2>&1; then
            log "INFO: frontend restarted successfully"
        else
            log "ERROR: frontend failed to come up after restart"
        fi
    fi
fi

log "INFO: healthcheck completed"
