#!/bin/bash

# Enable verbose mode and exit on error
set -e

# Script for applying patches to submodules

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DYSVM_DIR="$REPO_ROOT/dysvm"
CPYTHON_DIR="$DYSVM_DIR/cpython"
CPYTHON_PATCH_FILE="$DYSVM_DIR/patch"
PBS_DIR="$DYSVM_DIR/python-build-standalone"
PBS_PATCH_FILE="$DYSVM_DIR/pbs-patch"

echo "Applying patch to CPython..."
# Reset only when inside a real git repo (skipped in Docker builder where
# submodules are COPY'd in fresh and have no .git metadata)
if git -C "$CPYTHON_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$CPYTHON_DIR" checkout -- .
fi
cd "$CPYTHON_DIR" && patch -p1 < "$CPYTHON_PATCH_FILE"
echo "Patch applied successfully"

if [ -f "$PBS_PATCH_FILE" ]; then
    echo "Applying patch to python-build-standalone..."
    if git -C "$PBS_DIR" rev-parse --git-dir >/dev/null 2>&1; then
        git -C "$PBS_DIR" checkout -- .
    fi
    cd "$PBS_DIR" && patch -p1 < "$PBS_PATCH_FILE"
    echo "Patch applied successfully"
fi 