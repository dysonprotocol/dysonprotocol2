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
                echo "  git clone --recursive <repo>"
                echo "or inside the repo:"
                echo "  git submodule update --init --recursive"
                return 1
            fi
        fi
        return 0
    fi

    # Initialize/update all submodules recursively (non-interactive, safe to re-run)
    echo "Ensuring git submodules are initialized..."
    if ! git -C "$repo_root" submodule update --init --recursive; then
        echo "Error: Failed to initialize git submodules."
        echo "Hint: Run 'git submodule update --init --recursive' in $repo_root"
        return 1
    fi

    # Sanity check for common fresh-clone failure: local Cosmos SDK replacement
    if grep -q "replace\\s\+cosmossdk.io/collections" "$repo_root/go.mod" 2>/dev/null; then
        if [ ! -f "$repo_root/cosmos-sdk/collections/go.mod" ]; then
            echo "Error: cosmos-sdk submodule appears uninitialized or incomplete (missing collections/go.mod)."
            echo "Run: git submodule update --init --recursive"
            return 1
        fi
    fi

    echo "✓ Git submodules verified"
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


