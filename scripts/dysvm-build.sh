#!/bin/bash

# Enable verbose mode and exit on error
set -e

# Script for building custom Python distributions

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DYSVM_DIR="$REPO_ROOT/dysvm"
CPYTHON_DIR="$DYSVM_DIR/cpython"
PYTHON_BUILD_STANDALONE_DIR="$DYSVM_DIR/python-build-standalone"

# Load shared version variables
source "$SCRIPT_DIR/dysvm.env"

echo "Building custom Python distributions..."

# --- FP Mitigation: Set custom CFLAGS for consistency ---
# These will be passed to CPython's configure/make.
# Common flags: Disable fast-math and FMA for strict IEEE 754.
EXTRA_CFLAGS="-fno-fast-math -ffp-contract=off"

# Conditional on architecture (detected via uname -m)
ARCH="$(uname -m)"
if [ "$ARCH" = "x86_64" ]; then
    # x86-specific: Avoid x87 extended precision
    EXTRA_CFLAGS="$EXTRA_CFLAGS -mfpmath=sse -msse2"
elif [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
    # ARM: No x86 flags needed, but you could add -march=armv8-a if desired
    :
fi

# Export CFLAGS (append if already set, to avoid overriding other vars)
if [ -n "$CFLAGS" ]; then
    export CFLAGS="$CFLAGS $EXTRA_CFLAGS"
else
    export CFLAGS="$EXTRA_CFLAGS"
fi
# --- End FP Mitigation ---

# Build for current architecture (macOS or Linux)
if [ "$(uname -s)" = "Darwin" ]; then
    cd "$PYTHON_BUILD_STANDALONE_DIR" && \
    PYBUILD_PYTHON_VERSION="$PYTHON_VERSION" \
    python3 build-macos.py \
    --python "cpython-${PYTHON_VERSION_SHORT}" \
    --python-source "$CPYTHON_DIR" \
    --target-triple $([ "$(uname -m)" = "arm64" ] && echo "aarch64-apple-darwin" || echo "x86_64-apple-darwin") \
    --options noopt  # Use 'noopt' for FP consistency (avoids PGO/LTO variability)
else
    cd "$PYTHON_BUILD_STANDALONE_DIR"

    TARGET_TRIPLE=$([ "$(uname -m)" = "aarch64" ] && echo "aarch64-unknown-linux-gnu" || echo "x86_64-unknown-linux-gnu")

    # Run the linux build with required environment; fail fast on any error
    PYBUILD_PYTHON_VERSION="$PYTHON_VERSION" python3 build-linux.py \
        --python "cpython-${PYTHON_VERSION_SHORT}" \
        --python-source "$CPYTHON_DIR" \
        --target-triple "$TARGET_TRIPLE" \
        --options noopt
fi

echo "Python distributions built successfully"