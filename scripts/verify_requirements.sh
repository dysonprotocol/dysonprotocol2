#!/bin/bash

# Enable verbose mode and exit on error
set -e

# Unified requirements verification for building/installing and DYSVM
# Usage:
#   scripts/verify_requirements.sh           # minimal checks for build/install
#   scripts/verify_requirements.sh dysvm     # extended checks incl. Python & DYSVM deps

MODE="${1:-common}"

# Helpers
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

check_go_version() {
    if ! command_exists go; then
        echo "Error: Go is not installed"
        return 1
    fi

    local go_version
    go_version=$(go version | sed 's/go version go\([0-9.]*\).*/\1/')
    local required_version="1.24"

    local go_major
    local go_minor
    local req_major
    local req_minor
    go_major=$(echo "$go_version" | cut -d. -f1)
    go_minor=$(echo "$go_version" | cut -d. -f2)
    req_major=$(echo "$required_version" | cut -d. -f1)
    req_minor=$(echo "$required_version" | cut -d. -f2)

    if [ "$go_major" -gt "$req_major" ] || { [ "$go_major" -eq "$req_major" ] && [ "$go_minor" -ge "$req_minor" ]; }; then
        echo "✓ Go version $go_version (>= $required_version required)"
        return 0
    else
        echo "Error: Go version $go_version is too old. Version >= $required_version required"
        return 1
    fi
}

check_python_min_for_dysvm() {
    # Only needed for DYSVM flow
    local python_cmd=""
    for cmd in python3.12 python3; do
        if command_exists "$cmd"; then
            local version
            version=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            if [[ $(echo "$version" | cut -d'.' -f1-2) == "3.12" ]] || [[ $(echo "$version" | cut -d'.' -f1-2) > "3.12" ]]; then
                python_cmd="$cmd"
                echo "✓ Python version $version (>= 3.12 required) found at $cmd"
                break
            fi
        fi
    done

    if [ -z "$python_cmd" ]; then
        echo "Error: Python 3.12+ not found (required for DYSVM)"
        return 1
    fi

    if ! "$python_cmd" -m venv --help >/dev/null 2>&1; then
        echo "Error: Python venv module not available. Install python3.12-venv or equivalent package"
        return 1
    fi

    echo "✓ Python venv module available"
    return 0
}

ensure_git_and_submodules() {
    local script_dir
    local repo_root
    script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    repo_root="$(cd "$script_dir/.." && pwd)"

    init_submodules_shallow() {
        # Try shallow first; if unsupported or fails, fall back to full history
        if git -C "$repo_root" submodule update --init --recursive --depth 1; then
            echo "✓ Git submodules initialized (shallow)"
            return 0
        fi
        echo "⚠️  Shallow submodule init not supported or failed; falling back to full history..."
        if ! git -C "$repo_root" submodule update --init --recursive; then
            return 1
        fi
        echo "✓ Git submodules initialized"
        return 0
    }

    if ! command_exists git; then
        echo "Error: Git is not installed"
        return 1
    fi
    echo "✓ Git found"

    # If not a git checkout, skip (e.g., archive download)
    if ! git -C "$repo_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "⚠️  Not a git checkout; skipping submodule verification"
        # Still perform sanity check for local replace paths
        if grep -q "replace\\s\+cosmossdk.io/collections" "$repo_root/go.mod" 2>/dev/null; then
            if [ ! -f "$repo_root/cosmos-sdk/collections/go.mod" ]; then
                echo "Error: Local Cosmos SDK replacement detected but submodule directory is missing."
                echo "Please clone the repository with git and initialize submodules:"
                echo "  git clone --recursive --depth 1 <repo>"
                echo "or inside the repo:"
                echo "  git submodule update --init --recursive --depth 1"
                return 1
            fi
        fi
        return 0
    fi

    echo "Ensuring git submodules are initialized..."

    local need_init=0
    local status
    status=$(git -C "$repo_root" submodule status --recursive 2>/dev/null || true)
    if echo "$status" | grep -q '^-'; then
        need_init=1
    fi

    # Fresh-clone sanity for local Cosmos SDK replacement
    if grep -q "replace\\s\+cosmossdk.io/collections" "$repo_root/go.mod" 2>/dev/null; then
        if [ ! -f "$repo_root/cosmos-sdk/collections/go.mod" ]; then
            need_init=1
        fi
    fi

    if [ "$MODE" = "dysvm" ]; then
        # DYSVM-related submodules exist check
        for d in "$repo_root/dysvm/cpython" "$repo_root/dysvm/go-embed-python" "$repo_root/dysvm/python-build-standalone"; do
            if [ ! -d "$d" ] || [ -z "$(ls -A "$d" 2>/dev/null)" ]; then
                need_init=1
            fi
        done
    fi

    if [ "$need_init" -eq 0 ]; then
        echo "✓ Git submodules already initialized"
        echo "✓ Git submodules verified"
        return 0
    fi

    echo "One or more required submodules are missing or uninitialized."
    echo "This repository uses git submodules for vendored dependencies (e.g., cosmos-sdk)."
    echo "To fix automatically, the following command must be run in $repo_root:"
    echo "  git submodule update --init --recursive --depth 1"

    # Consent gates: allow non-interactive auto-yes via env var
    if [ "${VERIFY_REQS_YES:-}" = "1" ] || [ "${DYSVM_YES:-}" = "1" ] || [ "${YES:-}" = "1" ]; then
        echo "Consent provided via environment. Initializing submodules (shallow)..."
        if ! init_submodules_shallow; then
            echo "Error: Failed to initialize git submodules."
            echo "Hint: Run 'git submodule update --init --recursive --depth 1' in $repo_root"
            return 1
        fi
        echo "✓ Git submodules verified"
        return 0
    fi

    # Interactive prompt only if stdin is a TTY
    if [ -t 0 ]; then
        echo -n "Proceed to initialize submodules now? [y/N]: "
        read -r _ans
        case "$_ans" in
            y|Y|yes|YES)
                echo "Initializing submodules (shallow)..."
                if ! init_submodules_shallow; then
                    echo "Error: Failed to initialize git submodules."
                    echo "Hint: Run 'git submodule update --init --recursive --depth 1' in $repo_root"
                    return 1
                fi
                echo "✓ Git submodules verified"
                return 0
                ;;
            *)
                echo "Declined. No changes were made."
                echo "You can initialize later with:"
                echo "  git submodule update --init --recursive --depth 1"
                echo "Or rerun with VERIFY_REQS_YES=1 to auto-approve."
                return 1
                ;;
        esac
    else
        echo "Non-interactive shell detected. Refusing to make changes automatically."
        echo "Run 'git submodule update --init --recursive --depth 1' manually, or set VERIFY_REQS_YES=1 to auto-approve."
        return 1
    fi
}

verify_common() {
    echo "Verifying system requirements (build/install)..."
    check_go_version
    ensure_git_and_submodules
    if ! command_exists make; then
        echo "Error: Make is not installed"
        return 1
    fi
    echo "✓ Make found"
    echo "✅ Common requirements verified successfully"
    echo ""
}

verify_dysvm() {
    verify_common
    echo "Verifying additional DYSVM requirements..."
    check_python_min_for_dysvm
    echo "✅ DYSVM requirements verified successfully"
    echo ""
}

case "$MODE" in
    dysvm)
        verify_dysvm ;;
    *)
        verify_common ;;
esac


