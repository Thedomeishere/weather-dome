#!/bin/bash
# Weather Dome calibration cron job
# Runs 2x/day to compare predicted vs actual outages and update correction factors.
#
# Cron schedule: 0 6,18 * * * /opt/weather-dome/backend/scripts/run_calibration.sh
#   (runs at 6 AM and 6 PM UTC)

set -e

LOGFILE="/opt/weather-dome/logs/calibration.log"
VENV="/opt/weather-dome/.venv"
BACKEND="/opt/weather-dome/backend"

# Ensure log directory exists
mkdir -p /opt/weather-dome/logs

# Activate venv and run calibration
source "$VENV/bin/activate"
cd "$BACKEND"

echo "--- Calibration run: $(date -u) ---" >> "$LOGFILE"
python -m app.services.calibration >> "$LOGFILE" 2>&1
echo "" >> "$LOGFILE"

# Trim log to last 1000 lines
tail -1000 "$LOGFILE" > "$LOGFILE.tmp" && mv "$LOGFILE.tmp" "$LOGFILE"
