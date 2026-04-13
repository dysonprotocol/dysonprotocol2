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

# --- Pre-build cleanup: Remove stale /build and /tools directories ---
# This prevents permission errors when python-build-standalone tries to clean up
if [ -d "/build" ]; then
    echo "Cleaning up /build directory..."
    if ! rm -rf /build 2>/dev/null; then
        echo "⚠️  Could not remove /build; attempting chmod and retry..."
        chmod -R 755 /build 2>/dev/null || true
        rm -rf /build 2>/dev/null || {
            echo "⚠️  /build still locked; continuing with build (may fail)"
        }
    fi
fi

if [ -d "/tools" ]; then
    echo "Cleaning up /tools directory..."
    if ! rm -rf /tools 2>/dev/null; then
        echo "⚠️  Could not remove /tools; attempting chmod and retry..."
        chmod -R 755 /tools 2>/dev/null || true
        rm -rf /tools 2>/dev/null || {
            echo "⚠️  /tools still locked; continuing with build (may fail)"
        }
    fi
fi

# Recreate directories with proper permissions
mkdir -p /build /tools
chmod 755 /build /tools
# --- End pre-build cleanup ---

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

    # When PYBUILD_NO_DOCKER is set, build steps share a single /build and
    # /tools directory (instead of separate Docker containers). Parallel make
    # would cause race conditions, so force serial execution.
    SERIAL_FLAG=""
    if [ -n "$PYBUILD_NO_DOCKER" ]; then
        SERIAL_FLAG="--serial"
    fi

    # Setup cleanup trap: if build fails, clean up /build to prevent permission errors on retry
    cleanup() {
        local exit_code=$?
        if [ $exit_code -ne 0 ]; then
            echo "⚠️  Build failed; cleaning up /build and /tools for next attempt..."
            chmod -R 755 /build /tools 2>/dev/null || true
            rm -rf /build /tools 2>/dev/null || {
                echo "⚠️  Could not fully clean /build or /tools; next build may encounter permission issues"
            }
        fi
        return $exit_code
    }
    trap cleanup EXIT

    # Run the linux build with required environment; fail fast on any error
    PYBUILD_PYTHON_VERSION="$PYTHON_VERSION" python3 build-linux.py \
        --python "cpython-${PYTHON_VERSION_SHORT}" \
        --python-source "$CPYTHON_DIR" \
        --target-triple "$TARGET_TRIPLE" \
        --options noopt \
        $SERIAL_FLAG
fi

echo "Python distributions built successfully"