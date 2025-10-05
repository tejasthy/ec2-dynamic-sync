#!/bin/bash
"""
Installation script for EC2 Dynamic Sync.

This script provides an easy way to install EC2 Dynamic Sync and its dependencies
on various Linux distributions and macOS.
"""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PYTHON_MIN_VERSION="3.8"
INSTALL_DIR="$HOME/.local/bin"
VENV_DIR="$HOME/.ec2-sync-venv"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_python_version() {
    log_info "Checking Python version..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        log_error "Python is not installed. Please install Python $PYTHON_MIN_VERSION or later."
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    
    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
        log_error "Python $PYTHON_VERSION is installed, but Python $PYTHON_MIN_VERSION or later is required."
        exit 1
    fi
    
    log_success "Python $PYTHON_VERSION is installed and compatible."
}

check_system_dependencies() {
    log_info "Checking system dependencies..."
    
    MISSING_DEPS=()
    
    # Check for required system commands
    if ! command -v ssh &> /dev/null; then
        MISSING_DEPS+=("openssh-client")
    fi
    
    if ! command -v rsync &> /dev/null; then
        MISSING_DEPS+=("rsync")
    fi
    
    if ! command -v git &> /dev/null; then
        MISSING_DEPS+=("git")
    fi
    
    if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
        log_warning "Missing system dependencies: ${MISSING_DEPS[*]}"
        
        # Detect package manager and suggest installation
        if command -v apt-get &> /dev/null; then
            log_info "To install missing dependencies, run:"
            echo "sudo apt-get update && sudo apt-get install ${MISSING_DEPS[*]}"
        elif command -v yum &> /dev/null; then
            log_info "To install missing dependencies, run:"
            echo "sudo yum install ${MISSING_DEPS[*]}"
        elif command -v brew &> /dev/null; then
            log_info "To install missing dependencies, run:"
            echo "brew install ${MISSING_DEPS[*]}"
        else
            log_info "Please install the following packages using your system's package manager:"
            echo "${MISSING_DEPS[*]}"
        fi
        
        read -p "Continue with installation? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        log_success "All system dependencies are installed."
    fi
}

check_aws_cli() {
    log_info "Checking AWS CLI..."
    
    if command -v aws &> /dev/null; then
        AWS_VERSION=$(aws --version 2>&1 | cut -d' ' -f1 | cut -d'/' -f2)
        log_success "AWS CLI $AWS_VERSION is installed."
    else
        log_warning "AWS CLI is not installed."
        log_info "AWS CLI is recommended for easier AWS configuration."
        log_info "You can install it later by following: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    fi
}

create_virtual_environment() {
    log_info "Creating virtual environment..."
    
    if [ -d "$VENV_DIR" ]; then
        log_warning "Virtual environment already exists at $VENV_DIR"
        read -p "Remove existing environment and create new one? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        else
            log_info "Using existing virtual environment."
            return
        fi
    fi
    
    $PYTHON_CMD -m venv "$VENV_DIR"
    log_success "Virtual environment created at $VENV_DIR"
}

install_package() {
    log_info "Installing EC2 Dynamic Sync..."
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install from PyPI or local development
    if [ "$1" = "dev" ]; then
        log_info "Installing in development mode..."
        pip install -e .
    else
        log_info "Installing from PyPI..."
        pip install ec2-dynamic-sync
    fi
    
    log_success "EC2 Dynamic Sync installed successfully."
}

create_wrapper_scripts() {
    log_info "Creating wrapper scripts..."
    
    mkdir -p "$INSTALL_DIR"
    
    # Create wrapper scripts for each command
    COMMANDS=("ec2-sync" "ec2-sync-setup" "ec2-sync-watch" "ec2-sync-doctor" "ec2-sync-daemon")
    
    for cmd in "${COMMANDS[@]}"; do
        cat > "$INSTALL_DIR/$cmd" << EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec $cmd "\$@"
EOF
        chmod +x "$INSTALL_DIR/$cmd"
    done
    
    log_success "Wrapper scripts created in $INSTALL_DIR"
}

update_path() {
    log_info "Updating PATH..."
    
    # Check if INSTALL_DIR is already in PATH
    if [[ ":$PATH:" == *":$INSTALL_DIR:"* ]]; then
        log_success "PATH already includes $INSTALL_DIR"
        return
    fi
    
    # Add to shell profile
    SHELL_PROFILE=""
    if [ -f "$HOME/.bashrc" ]; then
        SHELL_PROFILE="$HOME/.bashrc"
    elif [ -f "$HOME/.zshrc" ]; then
        SHELL_PROFILE="$HOME/.zshrc"
    elif [ -f "$HOME/.profile" ]; then
        SHELL_PROFILE="$HOME/.profile"
    fi
    
    if [ -n "$SHELL_PROFILE" ]; then
        echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$SHELL_PROFILE"
        log_success "Added $INSTALL_DIR to PATH in $SHELL_PROFILE"
        log_info "Please run 'source $SHELL_PROFILE' or restart your terminal to update PATH."
    else
        log_warning "Could not automatically update PATH."
        log_info "Please add the following line to your shell profile:"
        echo "export PATH=\"$INSTALL_DIR:\$PATH\""
    fi
}

run_initial_setup() {
    log_info "Running initial setup..."
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Run doctor to check installation
    log_info "Running system diagnostics..."
    ec2-sync-doctor --output console
    
    log_info "Installation complete! You can now run 'ec2-sync-setup init' to configure your first project."
}

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dev          Install in development mode"
    echo "  --no-venv      Skip virtual environment creation"
    echo "  --help         Show this help message"
    echo ""
    echo "This script will:"
    echo "  1. Check system requirements"
    echo "  2. Create a virtual environment"
    echo "  3. Install EC2 Dynamic Sync"
    echo "  4. Create wrapper scripts"
    echo "  5. Update PATH"
    echo "  6. Run initial setup"
}

# Main installation process
main() {
    echo "=================================================="
    echo "EC2 Dynamic Sync Installation Script"
    echo "=================================================="
    echo ""
    
    # Parse command line arguments
    DEV_MODE=false
    USE_VENV=true
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dev)
                DEV_MODE=true
                shift
                ;;
            --no-venv)
                USE_VENV=false
                shift
                ;;
            --help)
                print_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                print_usage
                exit 1
                ;;
        esac
    done
    
    # Run installation steps
    check_python_version
    check_system_dependencies
    check_aws_cli
    
    if [ "$USE_VENV" = true ]; then
        create_virtual_environment
    fi
    
    if [ "$DEV_MODE" = true ]; then
        install_package "dev"
    else
        install_package
    fi
    
    if [ "$USE_VENV" = true ]; then
        create_wrapper_scripts
        update_path
    fi
    
    run_initial_setup
    
    echo ""
    echo "=================================================="
    log_success "Installation completed successfully!"
    echo "=================================================="
    echo ""
    echo "Next steps:"
    echo "1. Run 'ec2-sync-setup init' to configure your first project"
    echo "2. Use 'ec2-sync-doctor' to verify your setup"
    echo "3. Start syncing with 'ec2-sync sync'"
    echo ""
    echo "For help, run 'ec2-sync --help' or visit the documentation."
}

# Run main function
main "$@"
