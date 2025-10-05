#!/bin/bash

# Enable verbose mode and exit on error
set -e

# Script for cleaning DYSVM build artifacts

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DYSVM_DIR="$REPO_ROOT/dysvm"
CPYTHON_DIR="$DYSVM_DIR/cpython"
PYTHON_BUILD_STANDALONE_DIR="$DYSVM_DIR/python-build-standalone"
GO_EMBED_PYTHON_DIR="$DYSVM_DIR/go-embed-python"
TEMP_DIR="$DYSVM_DIR/.tmp"

echo "Cleaning DYSVM build artifacts..."
rm -rf "$TEMP_DIR"

# Reset and clean cpython directory
echo "Cleaning cpython directory..."
cd "$CPYTHON_DIR" && git reset --hard && git clean -dxf

# Reset and clean python-build-standalone directory
echo "Cleaning python-build-standalone directory..."
cd "$PYTHON_BUILD_STANDALONE_DIR" && git reset --hard && git clean -dxf

# Reset and clean go-embed-python directory
echo "Cleaning go-embed-python directory..."
cd "$GO_EMBED_PYTHON_DIR" && git reset --hard && git clean -dxf

echo "DYSVM build artifacts cleaned" 