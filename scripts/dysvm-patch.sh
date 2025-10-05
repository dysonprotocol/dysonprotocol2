#!/bin/bash

# Enable verbose mode and exit on error
set -e

# Script for applying patch to CPython

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DYSVM_DIR="$REPO_ROOT/dysvm"
CPYTHON_DIR="$DYSVM_DIR/cpython"
PATCH_FILE="$DYSVM_DIR/patch"


echo "Applying patch to CPython..."
cd "$CPYTHON_DIR" && git checkout -- .
cd "$CPYTHON_DIR" && patch -p1 < "$PATCH_FILE"
echo "Patch applied successfully" 