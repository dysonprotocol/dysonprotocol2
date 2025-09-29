#!/bin/bash

# Enable verbose mode and exit on error
set -ex

# Script for preparing Python for go-embed-python

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DYSVM_DIR="$REPO_ROOT/dysvm"
PYTHON_BUILD_STANDALONE_DIR="$DYSVM_DIR/python-build-standalone"
GO_EMBED_PYTHON_DIR="$DYSVM_DIR/go-embed-python"
# Prefer TMPDIR when set (CI often sets this); fallback to /tmp
TEMP_BASE="${TMPDIR:-/tmp}"

# Python version for DYSVM
PYTHON_VERSION="3.12.11"
PYTHON_DIST_NAME="cpython-${PYTHON_VERSION}"
CUSTOM_VERSION="custom"

# Get current platform
if [ "$(uname -s)" = "Darwin" ]; then
    if [ "$(uname -m)" = "arm64" ]; then
        OS=darwin
        ARCH=arm64
        DIST_PATTERN="apple-darwin-noopt"
        DIST_FULL="apple-darwin-pgo+lto-full"
        ARCH_NAME="aarch64"
    else
        OS=darwin
        ARCH=amd64
        DIST_PATTERN="apple-darwin-noopt"
        DIST_FULL="apple-darwin-pgo+lto-full"
        ARCH_NAME="x86_64"
    fi
else
    if [ "$(uname -m)" = "aarch64" ]; then
        OS=linux
        ARCH=arm64
        DIST_PATTERN="unknown-linux-gnu-noopt"
        DIST_FULL="unknown-linux-gnu-lto-full"
        ARCH_NAME="aarch64"
    else
        OS=linux
        ARCH=amd64
        DIST_PATTERN="unknown-linux-gnu-noopt"
        DIST_FULL="unknown-linux-gnu-pgo+lto-full"
        ARCH_NAME="x86_64"
    fi
fi

echo "Preparing custom Python for go-embed-python..."
# Create a unique, writable working directory to avoid permission issues
PREPARE_DIR=$(mktemp -d "${TEMP_BASE%/}/python-download.XXXXXX")

# Prepare the filenames - pattern must match actual filename in dist directory
# The file pattern shown in your ls output is different from what you had in the script
DIST_FILE=$(ls -t "$PYTHON_BUILD_STANDALONE_DIR/dist/${PYTHON_DIST_NAME}-${ARCH_NAME}-${DIST_PATTERN}"*.tar.zst | head -1)

if [ -z "$DIST_FILE" ]; then
    echo "Error: No Python distribution file found in $PYTHON_BUILD_STANDALONE_DIR/dist"
    echo "Available files:"
    ls -la "$PYTHON_BUILD_STANDALONE_DIR/dist"
    exit 1
fi

TARGET_FILE="$PREPARE_DIR/cpython-${PYTHON_VERSION}+${CUSTOM_VERSION}-${ARCH_NAME}-${DIST_FULL}.tar.zst"
EXTRACT_DIR="$TARGET_FILE.extracted"

echo "Source file: $DIST_FILE"
echo "Target file: $TARGET_FILE"

# Copy the built distribution
cp "$DIST_FILE" "$TARGET_FILE"

# Extract it manually
mkdir -p "$EXTRACT_DIR"
zstd -d < "$TARGET_FILE" | tar -x -C "$EXTRACT_DIR"

# Clean up case-sensitive file conflicts in terminfo
echo "🧹 Removing terminfo directory to avoid case-sensitivity conflicts..."
PYTHON_INSTALL_DIR="$EXTRACT_DIR/python/install"
if [ -d "$PYTHON_INSTALL_DIR/share/terminfo" ]; then
    rm -rf "$PYTHON_INSTALL_DIR/share/terminfo"
    echo "✓ Removed terminfo directory"
else
    echo "ℹ️ No terminfo directory found"
fi

# Repackage the cleaned distribution
echo "📦 Repackaging cleaned Python distribution..."
cd "$EXTRACT_DIR"
tar -cf - python | zstd > "$TARGET_FILE"
echo "✓ Repackaged successfully"

# Run the packer script - only do the current platform
cd "$GO_EMBED_PYTHON_DIR" && \
go mod tidy && \
go run ./python/generate \
    --python-standalone-version=${CUSTOM_VERSION} \
    --python-version=${PYTHON_VERSION} \
    --prepare-path="$PREPARE_DIR" \
    --prepare=false

# Embed the Python interpreter into the go-embed-python package
cd "$REPO_ROOT" && go generate ./...
