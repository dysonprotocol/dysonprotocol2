#!/bin/bash

# Enable verbose mode and exit on error
set -e

# Use the unified requirements verifier
command_exists() { command -v "$1" >/dev/null 2>&1; }

# Main script for DYSVM operations
# This script runs all the DYSVM operations in sequence: patch -> build -> embed

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Verify requirements before proceeding (extended for DYSVM)
bash "$SCRIPT_DIR/verify_requirements.sh" dysvm

check_submodule_sync() {
  # Skip if not a git checkout (e.g., tarball)
  if ! command_exists git || ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "⚠️  Not a git checkout; skipping submodule sync check"
    return 0
  fi

  echo "Checking git submodule sync..."
  local status
  status=$(git -C "$REPO_ROOT" submodule status --recursive 2>/dev/null || true)

  # Lines starting with a space are in-sync. Anything else ('-', '+', 'U') needs attention.
  local out_of_sync
  out_of_sync=$(echo "$status" | grep -E '^[^ ]' || true)

  if [ -z "$out_of_sync" ]; then
    echo "✓ Git submodules are in sync"
    return 0
  fi

  echo "⚠️  The following submodules are not at the recorded commits (or have conflicts/are uninitialized):"
  echo "$out_of_sync"
  echo "You likely need to sync submodules to the commits pinned by this repository."

  auto_sync() {
    # Try shallow first; if unsupported or fails, fall back to full history
    if git -C "$REPO_ROOT" submodule sync --recursive && \
       git -C "$REPO_ROOT" submodule update --init --recursive --depth 1; then
      echo "✓ Submodules synced (shallow)"
      return 0
    fi
    echo "⚠️  Shallow sync failed or unsupported; falling back to full sync..."
    git -C "$REPO_ROOT" submodule update --init --recursive
    echo "✓ Submodules synced"
    return 0
  }

  if [ -t 0 ]; then
    printf "Sync submodules to recorded commits now? [y/N]: "
    read ans
    case "$ans" in
      y|Y|yes|YES)
        auto_sync
        ;;
      *)
        echo "Declined. You can sync later with:"
        echo "  git submodule sync --recursive && git submodule update --init --recursive --depth 1"
        exit 1
        ;;
    esac
  else
    echo "Non-interactive shell."
    echo "Run the following and re-try:"
    echo "  git -C '$REPO_ROOT' submodule sync --recursive && git -C '$REPO_ROOT' submodule update --init --recursive --depth 1"
    exit 1
  fi
}

check_submodule_sync

# Call the scripts in sequence
echo "Running DYSVM operations..."
"$SCRIPT_DIR/dysvm-patch.sh" && "$SCRIPT_DIR/dysvm-build.sh" && "$SCRIPT_DIR/dysvm-embed.sh" && echo "DYSVM operations completed successfully" 