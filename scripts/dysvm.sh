#!/bin/bash

# Enable verbose mode and exit on error
set -e

# Use the unified requirements verifier
command_exists() { command -v "$1" >/dev/null 2>&1; }

# Main script for DYSVM operations
# This script runs all the DYSVM operations in sequence: patch -> build -> embed

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Verify requirements before proceeding (extended for DYSVM)
bash "$SCRIPT_DIR/verify_requirements.sh" dysvm

# Call the scripts in sequence
echo "Running DYSVM operations..."
"$SCRIPT_DIR/dysvm-patch.sh" && "$SCRIPT_DIR/dysvm-build.sh" && "$SCRIPT_DIR/dysvm-embed.sh" && echo "DYSVM operations completed successfully" 