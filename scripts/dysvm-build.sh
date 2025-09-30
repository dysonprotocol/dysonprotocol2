#!/bin/bash

# Enable verbose mode and exit on error
set -ex

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
    PYBUILD_PYTHON_VERSION="$PYTHON_VERSION"

    TARGET_TRIPLE=$([ "$(uname -m)" = "aarch64" ] && echo "aarch64-unknown-linux-gnu" || echo "x86_64-unknown-linux-gnu")

    # Run the linux build; if it fails in the final compress/rename step, fall back to manual compression.
    set +e
    python3 build-linux.py \
        --python "cpython-${PYTHON_VERSION_SHORT}" \
        --python-source "$CPYTHON_DIR" \
        --target-triple "$TARGET_TRIPLE" \
        --options noopt
    BUILD_STATUS=$?
    set -e

    # If build failed, try to manually create the expected .tar.zst from the built .tar
    if [ $BUILD_STATUS -ne 0 ]; then
        echo "python-build-standalone build failed; attempting manual compression fallback..."

        BUILD_TAR="$PYTHON_BUILD_STANDALONE_DIR/build/cpython-${PYTHON_VERSION}-${TARGET_TRIPLE}-noopt.tar"
        DIST_DIR="$PYTHON_BUILD_STANDALONE_DIR/dist"
        mkdir -p "$DIST_DIR"

        if [ ! -f "$BUILD_TAR" ]; then
            echo "Error: Expected build archive not found: $BUILD_TAR"
            exit $BUILD_STATUS
        fi

        RELEASE_TAG=$(git log -n 1 --date=format:%Y%m%dT%H%M --pretty=format:%ad)
        DEST_FILE="$DIST_DIR/cpython-${PYTHON_VERSION}-${TARGET_TRIPLE}-noopt-${RELEASE_TAG}.tar.zst"
        TMP_FILE="$DEST_FILE.tmp.$$"

        if ! command -v zstd >/dev/null 2>&1; then
            echo "Error: zstd not found; cannot perform fallback compression"
            exit $BUILD_STATUS
        fi

        echo "Compressing $BUILD_TAR -> $DEST_FILE (fallback)"
        # Use strong compression and all cores; write to temp then atomically move
        zstd -T0 -22 -q -c "$BUILD_TAR" > "$TMP_FILE" && mv "$TMP_FILE" "$DEST_FILE"

        if [ ! -f "$DEST_FILE" ]; then
            echo "Fallback compression failed to produce $DEST_FILE"
            exit $BUILD_STATUS
        fi

        echo "Fallback compression succeeded: $DEST_FILE"
    fi
fi

echo "Python distributions built successfully"