#!/bin/bash

# Start port forwarding from localhost:1317 to host.docker.internal:1317
echo "Starting port forwarding: localhost:1317 -> host.docker.internal:1317"

# Check if socat is already running on port 1317
if pgrep -f "socat.*TCP-LISTEN:1317" > /dev/null; then
    echo "Port forwarding already running"
    exit 0
fi

# Start port forwarding in background
socat TCP-LISTEN:1317,fork,reuseaddr TCP:host.docker.internal:1317 &
SOCAT_PID=$!

echo "Port forwarding started with PID: $SOCAT_PID"
echo "Testing connection..."

# Wait a moment for socat to start
sleep 1

# Test the connection
if curl -s --connect-timeout 3 http://localhost:1317/cosmos/base/tendermint/v1beta1/node_info >/dev/null; then
    echo "✅ Port forwarding working correctly"
else
    echo "⚠️  Port forwarding may not be working - check host service"
fi