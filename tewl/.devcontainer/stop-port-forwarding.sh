#!/bin/bash

# Stop port forwarding for localhost:1317
echo "Stopping port forwarding for localhost:1317"

# Find and kill socat processes listening on port 1317
PIDS=$(pgrep -f "socat.*TCP-LISTEN:1317")

if [ -z "$PIDS" ]; then
    echo "No port forwarding process found"
    exit 0
fi

echo "Stopping processes: $PIDS"
kill $PIDS

# Wait a moment and check if processes were killed
sleep 1

REMAINING=$(pgrep -f "socat.*TCP-LISTEN:1317")
if [ -z "$REMAINING" ]; then
    echo "✅ Port forwarding stopped successfully"
else
    echo "⚠️  Some processes may still be running: $REMAINING"
    echo "Use 'kill -9 $REMAINING' if needed"
fi