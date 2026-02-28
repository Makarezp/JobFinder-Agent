#!/bin/bash
# Opens the state snapshot log file in the default editor or tails it live.
# Usage:
#   ./scripts/open_state_log.sh        # tail live
#   ./scripts/open_state_log.sh open   # open in $EDITOR (default: nano)

LOG_FILE="$(python3 -c 'import tempfile; print(tempfile.gettempdir())')/cvviewer_state_debug.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "Log file not found: $LOG_FILE"
    echo "Start the app first to create it."
    exit 1
fi

if [ "$1" = "open" ]; then
    ${EDITOR:-nano} "$LOG_FILE"
else
    echo "Tailing $LOG_FILE (Ctrl+C to stop)..."
    tail -f "$LOG_FILE"
fi
