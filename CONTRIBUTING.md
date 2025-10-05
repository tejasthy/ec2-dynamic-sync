# Contributing to EC2 Dynamic Sync

Thank you for your interest in contributing to EC2 Dynamic Sync! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contributing Guidelines](#contributing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Testing](#testing)
- [Code Style](#code-style)
- [Documentation](#documentation)
- [Issue Reporting](#issue-reporting)

## Code of Conduct

This project adheres to a code of conduct that we expect all contributors to follow. Please be respectful and constructive in all interactions.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/ec2-dynamic-sync.git
   cd ec2-dynamic-sync
   ```
3. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

### Prerequisites
- Python 3.8 or higher
- pip and virtualenv
- Git
- AWS CLI (for testing AWS integration)
- SSH client and rsync

### Environment Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Project Structure
```
ec2-dynamic-sync/
├── src/ec2_dynamic_sync/     # Main package
│   ├── cli/                  # CLI commands
│   ├── core/                 # Core functionality
│   └── __init__.py
├── tests/                    # Test suite
├── docs/                     # Documentation
├── pyproject.toml           # Project configuration
└── README.md
```

## Contributing Guidelines

### Types of Contributions

1. **Bug Fixes**: Fix existing issues or bugs
2. **Features**: Add new functionality
3. **Documentation**: Improve or add documentation
4. **Tests**: Add or improve test coverage
5. **Performance**: Optimize existing code
6. **Refactoring**: Improve code structure without changing functionality

### Before You Start

1. **Check existing issues** to see if your idea is already being worked on
2. **Create an issue** to discuss major changes before implementing
3. **Keep changes focused** - one feature or fix per pull request
4. **Follow the coding standards** outlined below

## Pull Request Process

1. **Update your branch** with the latest main:
   ```bash
   git checkout main
   git pull upstream main
   git checkout your-feature-branch
   git rebase main
   ```

2. **Run the test suite**:
   ```bash
   pytest tests/ -v
   ```

3. **Run linting and formatting**:
   ```bash
   black src/ tests/
   isort src/ tests/
   flake8 src/ tests/
   mypy src/
   ```

4. **Update documentation** if needed

5. **Create a pull request** with:
   - Clear title and description
   - Reference to related issues
   - List of changes made
   - Screenshots for UI changes (if applicable)

6. **Respond to feedback** and make requested changes

## Testing

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_integration.py -v

# Run with coverage
pytest tests/ --cov=ec2_dynamic_sync --cov-report=html
```

### Writing Tests
- Write tests for all new functionality
- Maintain or improve test coverage
- Use descriptive test names
- Mock external dependencies (AWS, SSH, file system)
- Follow the existing test patterns

### Test Categories
- **Unit tests**: Test individual functions and classes
- **Integration tests**: Test component interactions
- **CLI tests**: Test command-line interface
- **End-to-end tests**: Test complete workflows

## Code Style

### Python Style Guide
- Follow [PEP 8](https://pep8.org/)
- Use [Black](https://black.readthedocs.io/) for code formatting
- Use [isort](https://isort.readthedocs.io/) for import sorting
- Use [flake8](https://flake8.pycqa.org/) for linting
- Use [mypy](https://mypy.readthedocs.io/) for type checking

### Code Quality
- Write clear, self-documenting code
- Add docstrings to all public functions and classes
- Use type hints for function parameters and return values
- Keep functions small and focused
- Use meaningful variable and function names
- Add comments for complex logic

### Example Code Style
```python
from typing import Dict, List, Optional

def sync_directories(
    local_path: str,
    remote_path: str,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Synchronize directories between local and remote locations.
    
    Args:
        local_path: Path to local directory
        remote_path: Path to remote directory  
        options: Optional sync configuration
        
    Returns:
        Dictionary containing sync results and statistics
        
    Raises:
        SyncError: If synchronization fails
    """
    # Implementation here
    pass
```

## Documentation

### Documentation Standards
- Update README.md for user-facing changes
- Add docstrings to all public APIs
- Update CLI help text for command changes
- Add examples for new features
- Keep documentation up-to-date with code changes

### Documentation Types
- **API Documentation**: Docstrings and type hints
- **User Documentation**: README, usage examples
- **Developer Documentation**: Contributing guide, architecture notes
- **CLI Documentation**: Help text and examples

## Issue Reporting

### Bug Reports
Include the following information:
- **Description**: Clear description of the issue
- **Steps to reproduce**: Detailed steps to recreate the bug
- **Expected behavior**: What should happen
- **Actual behavior**: What actually happens
- **Environment**: OS, Python version, package version
- **Logs**: Relevant error messages or logs
- **Configuration**: Sanitized configuration files (remove sensitive data)

### Feature Requests
Include the following information:
- **Description**: Clear description of the proposed feature
- **Use case**: Why this feature would be useful
- **Implementation ideas**: Suggestions for how it could be implemented
- **Alternatives**: Other solutions you've considered

### Issue Labels
- `bug`: Something isn't working
- `enhancement`: New feature or request
- `documentation`: Improvements or additions to documentation
- `good first issue`: Good for newcomers
- `help wanted`: Extra attention is needed

## Development Workflow

### Branching Strategy
- `main`: Stable release branch
- `develop`: Development branch (if used)
- `feature/*`: Feature branches
- `bugfix/*`: Bug fix branches
- `hotfix/*`: Critical fixes

### Commit Messages
Use clear, descriptive commit messages:
```
feat: add real-time file monitoring with watchdog

- Implement file system event handling
- Add configurable sync delay and batching
- Include progress reporting and statistics
- Update CLI with watch command options

Fixes #123
```

### Release Process
1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create release PR
4. Tag release after merge
5. Publish to PyPI

## Getting Help

- **Documentation**: Check README.md and docs/
- **Issues**: Search existing issues on GitHub
- **Discussions**: Use GitHub Discussions for questions
- **Contact**: Create an issue for specific problems

## Recognition

Contributors will be recognized in:
- CHANGELOG.md for significant contributions
- README.md contributors section
- Release notes for major features

Thank you for contributing to EC2 Dynamic Sync!
