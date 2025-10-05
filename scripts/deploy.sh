#!/bin/bash
"""
Deployment script for EC2 Dynamic Sync.

This script handles the complete deployment process including:
- Version validation
- Testing
- Building
- Publishing to PyPI
- Git tagging
"""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PACKAGE_NAME="ec2-dynamic-sync"
PYPI_REPO="pypi"  # or "testpypi" for testing

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

check_git_status() {
    log_info "Checking git status..."
    
    if [ -n "$(git status --porcelain)" ]; then
        log_error "Working directory is not clean. Please commit or stash changes."
        git status --short
        exit 1
    fi
    
    # Check if we're on main branch
    CURRENT_BRANCH=$(git branch --show-current)
    if [ "$CURRENT_BRANCH" != "main" ]; then
        log_warning "Not on main branch (currently on $CURRENT_BRANCH)"
        read -p "Continue with deployment? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    log_success "Git status is clean."
}

get_version() {
    # Extract version from pyproject.toml
    VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
    echo "$VERSION"
}

validate_version() {
    log_info "Validating version..."
    
    VERSION=$(get_version)
    if [ -z "$VERSION" ]; then
        log_error "Could not extract version from pyproject.toml"
        exit 1
    fi
    
    log_info "Current version: $VERSION"
    
    # Check if version tag already exists
    if git tag -l | grep -q "^v$VERSION$"; then
        log_error "Version tag v$VERSION already exists"
        exit 1
    fi
    
    # Validate version format (semantic versioning)
    if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)?$'; then
        log_error "Version $VERSION does not follow semantic versioning"
        exit 1
    fi
    
    log_success "Version $VERSION is valid."
}

run_tests() {
    log_info "Running tests..."
    
    # Install test dependencies
    pip install pytest pytest-cov pytest-mock
    
    # Run tests with coverage
    if pytest tests/ --cov=src/ec2_dynamic_sync --cov-report=term-missing --cov-report=html; then
        log_success "All tests passed."
    else
        log_error "Tests failed. Please fix issues before deploying."
        exit 1
    fi
}

run_linting() {
    log_info "Running code quality checks..."
    
    # Install linting tools
    pip install black flake8 mypy
    
    # Check code formatting
    if black --check src/ tests/; then
        log_success "Code formatting is correct."
    else
        log_error "Code formatting issues found. Run 'black src/ tests/' to fix."
        exit 1
    fi
    
    # Run flake8
    if flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203,W503; then
        log_success "Linting passed."
    else
        log_error "Linting issues found. Please fix before deploying."
        exit 1
    fi
}

build_package() {
    log_info "Building package..."
    
    # Clean previous builds
    rm -rf dist/ build/ *.egg-info/
    
    # Install build tools
    pip install build twine
    
    # Build package
    python -m build
    
    # Check package
    twine check dist/*
    
    log_success "Package built successfully."
}

test_installation() {
    log_info "Testing package installation..."
    
    # Create temporary virtual environment
    TEMP_VENV=$(mktemp -d)
    python -m venv "$TEMP_VENV"
    source "$TEMP_VENV/bin/activate"
    
    # Install from built package
    pip install dist/*.whl
    
    # Test basic functionality
    if ec2-sync --version; then
        log_success "Package installation test passed."
    else
        log_error "Package installation test failed."
        exit 1
    fi
    
    # Cleanup
    deactivate
    rm -rf "$TEMP_VENV"
}

publish_to_pypi() {
    log_info "Publishing to PyPI..."
    
    VERSION=$(get_version)
    
    if [ "$PYPI_REPO" = "testpypi" ]; then
        log_warning "Publishing to Test PyPI"
        twine upload --repository testpypi dist/*
    else
        log_info "Publishing to PyPI"
        twine upload dist/*
    fi
    
    log_success "Package published successfully."
}

create_git_tag() {
    log_info "Creating git tag..."
    
    VERSION=$(get_version)
    
    # Create annotated tag
    git tag -a "v$VERSION" -m "Release version $VERSION"
    
    # Push tag to remote
    git push origin "v$VERSION"
    
    log_success "Git tag v$VERSION created and pushed."
}

create_github_release() {
    log_info "Creating GitHub release..."
    
    VERSION=$(get_version)
    
    # Check if gh CLI is available
    if command -v gh &> /dev/null; then
        # Create release notes
        RELEASE_NOTES="Release notes for version $VERSION

## What's New

- Complete implementation of all CLI commands
- Real-time file monitoring with ec2-sync-watch
- Background daemon mode with ec2-sync-daemon
- Comprehensive system diagnostics with ec2-sync-doctor
- Enhanced configuration wizard with ec2-sync-setup
- Improved error handling and user experience

## Installation

\`\`\`bash
pip install ec2-dynamic-sync==$VERSION
\`\`\`

## Full Changelog

See the commit history for detailed changes."
        
        # Create release
        echo "$RELEASE_NOTES" | gh release create "v$VERSION" --title "Release v$VERSION" --notes-file -
        
        log_success "GitHub release created."
    else
        log_warning "GitHub CLI not available. Please create release manually."
    fi
}

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --test-pypi    Deploy to Test PyPI instead of PyPI"
    echo "  --skip-tests   Skip running tests"
    echo "  --skip-lint    Skip linting checks"
    echo "  --help         Show this help message"
    echo ""
    echo "This script will:"
    echo "  1. Check git status and version"
    echo "  2. Run tests and linting"
    echo "  3. Build the package"
    echo "  4. Test installation"
    echo "  5. Publish to PyPI"
    echo "  6. Create git tag"
    echo "  7. Create GitHub release"
}

# Main deployment process
main() {
    echo "=================================================="
    echo "EC2 Dynamic Sync Deployment Script"
    echo "=================================================="
    echo ""
    
    # Parse command line arguments
    SKIP_TESTS=false
    SKIP_LINT=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --test-pypi)
                PYPI_REPO="testpypi"
                shift
                ;;
            --skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --skip-lint)
                SKIP_LINT=true
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
    
    # Confirm deployment
    VERSION=$(get_version)
    echo "About to deploy version $VERSION to $PYPI_REPO"
    read -p "Continue with deployment? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled."
        exit 0
    fi
    
    # Run deployment steps
    check_git_status
    validate_version
    
    if [ "$SKIP_LINT" = false ]; then
        run_linting
    fi
    
    if [ "$SKIP_TESTS" = false ]; then
        run_tests
    fi
    
    build_package
    test_installation
    publish_to_pypi
    create_git_tag
    create_github_release
    
    echo ""
    echo "=================================================="
    log_success "Deployment completed successfully!"
    echo "=================================================="
    echo ""
    echo "Version $VERSION has been deployed to $PYPI_REPO"
    echo ""
    echo "Next steps:"
    echo "1. Verify the package on PyPI: https://pypi.org/project/$PACKAGE_NAME/"
    echo "2. Test installation: pip install $PACKAGE_NAME==$VERSION"
    echo "3. Update documentation if needed"
    echo "4. Announce the release"
}

# Run main function
main "$@"
