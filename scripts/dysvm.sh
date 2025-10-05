#!/bin/bash

# Enable verbose mode and exit on error
set -e

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Go version
check_go_version() {
    if ! command_exists go; then
        echo "Error: Go is not installed"
        return 1
    fi
    
    local go_version=$(go version | sed 's/go version go\([0-9.]*\).*/\1/')
    local required_version="1.24"
    
    # Simple version comparison (assumes format x.y)
    local go_major=$(echo "$go_version" | cut -d. -f1)
    local go_minor=$(echo "$go_version" | cut -d. -f2)
    local req_major=$(echo "$required_version" | cut -d. -f1)
    local req_minor=$(echo "$required_version" | cut -d. -f2)
    
    if [ "$go_major" -gt "$req_major" ] || { [ "$go_major" -eq "$req_major" ] && [ "$go_minor" -ge "$req_minor" ]; }; then
        echo "✓ Go version $go_version (>= $required_version required)"
        return 0
    else
        echo "Error: Go version $go_version is too old. Version >= $required_version required"
        return 1
    fi
}

# Function to check Python version and venv
check_python() {
    local python_cmd=""
    
    # Try different Python command variations
    for cmd in python3.12 python3; do
        if command_exists "$cmd"; then
            local version=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            local major=$(echo "$version" | cut -d. -f1)
            local minor=$(echo "$version" | cut -d. -f2)
            
            if [[ $(echo "$version" | cut -d'.' -f1-2) == "3.12" ]] || [[ $(echo "$version" | cut -d'.' -f1-2) > "3.12" ]]; then
                python_cmd="$cmd"
                echo "✓ Python version $version (>= 3.12 required) found at $cmd"
                break
            fi
        fi
    done
    
    if [ -z "$python_cmd" ]; then
        echo "Error: Python 3.12+ not found"
        return 1
    fi
    
    # Check if venv module is available
    if ! "$python_cmd" -m venv --help >/dev/null 2>&1; then
        echo "Error: Python venv module not available. Install python3.12-venv or equivalent package"
        return 1
    fi
    
    echo "✓ Python venv module available"
    return 0
}

# Function to verify git submodules (auto-init if missing)
check_git_submodules() {
    local script_dir
    local repo_root
    script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    repo_root="$(cd "$script_dir/.." && pwd)"

    # If not a git checkout, skip (e.g., archive download)
    if ! git -C "$repo_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "⚠️  Not a git checkout; skipping submodule verification"
        return 0
    fi

    # No submodules defined
    if [ ! -f "$repo_root/.gitmodules" ]; then
        echo "✓ No git submodules defined"
        return 0
    fi

    echo "Verifying git submodules..."

    local need_init=0
    local has_conflict=0
    local status
    status=$(git -C "$repo_root" submodule status --recursive 2>/dev/null || true)
    if echo "$status" | grep -q '^-'; then
        need_init=1
    fi

    # Detect conflicts: directory exists, non-empty, but not a git checkout
    for d in "$repo_root/dysvm/cpython" "$repo_root/dysvm/go-embed-python" "$repo_root/dysvm/python-build-standalone"; do
        if [ -d "$d" ] && [ -n "$(ls -A "$d" 2>/dev/null)" ]; then
            if ! git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
                echo "⚠️  Submodule directory exists but is not a git checkout: $d"
                has_conflict=1
            fi
        fi
    done

    if [ "$has_conflict" -eq 1 ]; then
        echo "Refusing to modify conflicting directories automatically."
        echo "Please remove or move the conflicting directories above, then run:"
        echo "  git submodule update --init --recursive"
        return 1
    fi

    # Ensure required DYSVM submodules exist
    for d in "$repo_root/dysvm/cpython" "$repo_root/dysvm/go-embed-python" "$repo_root/dysvm/python-build-standalone"; do
        if [ ! -d "$d" ] || [ -z "$(ls -A "$d" 2>/dev/null)" ]; then
            echo "• Missing or empty submodule directory: $d"
            need_init=1
        fi
    done

    if [ "$need_init" -eq 1 ]; then
        echo "Submodules are not initialized. This requires network access to clone/fetch."
        # Consent gates
        if [ "${DYSVM_YES:-}" = "1" ]; then
            echo "Consent provided via environment. Initializing submodules..."
        elif [ -t 0 ]; then
            read -r -p "Allow running 'git submodule update --init --recursive'? [y/N]: " _ans
            case "$_ans" in
                y|Y|yes|YES)
                    echo "Initializing submodules..." ;;
                *)
                    echo "Declined. No network requests were made."
                    echo "Run 'git submodule update --init --recursive' manually, or set DYSVM_YES=1 to auto-run."
                    return 1 ;;
            esac
        else
            echo "Non-interactive shell detected. Refusing to make network requests."
            echo "Run 'git submodule update --init --recursive' manually, or set DYSVM_YES=1 to auto-run."
            return 1
        fi

        if ! git -C "$repo_root" submodule update --init --recursive; then
            echo "Error: Failed to initialize git submodules."
            echo "Hint: Run 'git submodule update --init --recursive' in $repo_root"
            return 1
        fi
    fi

    echo "✓ Git submodules verified"
    return 0
}

# Function to verify all requirements
verify_requirements() {
    echo "Verifying system requirements..."
    
    # Check Go
    check_go_version || return 1
    
    # Check Git
    if ! command_exists git; then
        echo "Error: Git is not installed"
        return 1
    else
        echo "✓ Git found"
        # Verify and initialize submodules if needed (fail fast on error)
        check_git_submodules || return 1
    fi
    
    # Check Make
    if ! command_exists make; then
        echo "Error: Make is not installed"
        return 1
    else
        echo "✓ Make found"
    fi
    
    # Check Python
    check_python || return 1
    
    echo "✅ All requirements verified successfully"
    echo ""
}

# Main script for DYSVM operations
# This script runs all the DYSVM operations in sequence: patch -> build -> embed

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Verify requirements before proceeding
verify_requirements

# Call the scripts in sequence
echo "Running DYSVM operations..."
"$SCRIPT_DIR/dysvm-patch.sh" && "$SCRIPT_DIR/dysvm-build.sh" && "$SCRIPT_DIR/dysvm-embed.sh" && echo "DYSVM operations completed successfully" 