# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of EC2 Dynamic Sync
- Bidirectional file synchronization between local machines and EC2 instances
- Interactive setup wizard (`ec2-sync-setup init`)
- Real-time file monitoring with automatic sync (`ec2-sync-watch`)
- System diagnostics and health checks (`ec2-sync-doctor`)
- Background daemon mode (`ec2-sync-daemon`)
- Configuration validation and testing tools
- Support for multiple directory mappings
- Exclude/include pattern support similar to .gitignore
- Bandwidth throttling and progress reporting
- Conflict resolution strategies
- AWS instance auto-start functionality
- SSH key validation and permission fixing
- Comprehensive CLI with rich terminal UI
- Docker support for containerized environments
- Cron job integration for scheduled syncs

### Features
- **Multi-directional sync**: Bidirectional, push-only, or pull-only modes
- **Smart conflict resolution**: Configurable strategies (newer, larger, manual)
- **Real-time monitoring**: File system events trigger automatic syncs
- **Robust error handling**: Retry logic and graceful failure recovery
- **Security focused**: SSH key validation, secure credential handling
- **Performance optimized**: Incremental syncs, compression, bandwidth limiting
- **User-friendly**: Interactive setup, rich terminal UI, comprehensive help

### CLI Commands
- `ec2-sync` - Main sync operations (status, sync, push, pull)
- `ec2-sync-setup` - Configuration management (init, validate, test, cron)
- `ec2-sync-watch` - Real-time file monitoring and sync
- `ec2-sync-doctor` - System diagnostics and health checks
- `ec2-sync-daemon` - Background sync daemon management

### Configuration
- YAML-based configuration with validation
- Support for multiple profiles
- Environment variable overrides
- Automatic AWS region and instance detection
- SSH key auto-discovery and validation

### AWS Integration
- EC2 instance discovery and management
- Support for instance auto-start when stopped
- IAM permission validation and recommendations
- Multi-region support
- AWS CLI integration

### Documentation
- Comprehensive README with setup instructions
- CLI usage examples and best practices
- AWS permissions guide with minimal and full access options
- Troubleshooting guide and FAQ
- Contributing guidelines for developers

## [0.1.0] - 2024-01-XX

### Added
- Initial project structure and core functionality
- Basic sync operations and CLI framework
- AWS and SSH integration
- Configuration management system
- Test suite with comprehensive coverage

---

## Release Notes

### System Requirements
- **Local Machine**: macOS, Linux, or Windows WSL with Python 3.8+
- **EC2 Instance**: Ubuntu/Amazon Linux with rsync installed
- **Dependencies**: AWS CLI (optional), SSH client, rsync

### Installation
```bash
pip install ec2-dynamic-sync
```

### Quick Start
```bash
# Interactive setup
ec2-sync-setup init

# Test configuration
ec2-sync-setup test

# Start real-time monitoring
ec2-sync-watch

# Manual sync
ec2-sync sync
```

### Breaking Changes
None in this initial release.

### Migration Guide
This is the initial release, no migration needed.

### Known Issues
- None currently identified

### Contributors
- Initial development and architecture
- CLI design and implementation
- AWS integration and security
- Documentation and testing

---

For more information, see the [README.md](README.md) and [documentation](docs/).
