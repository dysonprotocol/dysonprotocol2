#!/bin/bash

# Enable verbose mode and exit on error
set -ex

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

# Function to verify all requirements
verify_requirements() {
    echo "Verifying system requirements..."
    
    local errors=0
    
    # Check Go
    if ! check_go_version; then
        errors=$((errors + 1))
    fi
    
    # Check Git
    if ! command_exists git; then
        echo "Error: Git is not installed"
        errors=$((errors + 1))
    else
        echo "✓ Git found"
    fi
    
    # Check Make
    if ! command_exists make; then
        echo "Error: Make is not installed"
        errors=$((errors + 1))
    else
        echo "✓ Make found"
    fi
    
    # Check Python
    if ! check_python; then
        errors=$((errors + 1))
    fi
    
    if [ $errors -gt 0 ]; then
        echo ""
        echo "❌ $errors requirement(s) not met. Please install the missing dependencies:"
        echo "   - Go (>= 1.24): https://golang.org/doc/install"
        echo "   - Git: Package manager or https://git-scm.com/downloads"
        echo "   - Make: Package manager (build-essential on Ubuntu/Debian)"
        echo "   - Python 3.12+ with venv: python3.12-venv package or equivalent"
        exit 1
    fi
    
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