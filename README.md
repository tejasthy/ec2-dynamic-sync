# EC2 Dynamic Sync

[![PyPI version](https://badge.fury.io/py/ec2-dynamic-sync.svg)](https://badge.fury.io/py/ec2-dynamic-sync)
[![Python Support](https://img.shields.io/pypi/pyversions/ec2-dynamic-sync.svg)](https://pypi.org/project/ec2-dynamic-sync/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Professional-grade EC2 file synchronization with dynamic IP handling, bidirectional sync, and real-time monitoring.**

EC2 Dynamic Sync is a comprehensive tool for synchronizing files between local machines and EC2 instances. It handles the complexities of dynamic IP addresses, provides intelligent conflict resolution, and offers multiple execution modes for different use cases.

## 🚀 Quick Start

### Installation

```bash
# Install from PyPI
pip install ec2-dynamic-sync

# Or install with development dependencies
pip install ec2-dynamic-sync[dev]
```

### 5-Minute Setup

```bash
# 1. Initialize configuration (interactive setup)
ec2-sync-setup init

# 2. Validate configuration
ec2-sync-setup validate

# 3. Test connectivity
ec2-sync-setup test

# 4. Check sync status
ec2-sync status

# 5. Perform your first sync
ec2-sync sync
```

## ✨ Key Features

- **🔄 Dynamic IP Handling**: Automatically resolves EC2 public IPs that change with instance restarts
- **⚡ Automatic Instance Management**: Can start stopped instances and wait for them to be ready
- **🔀 Bidirectional Sync**: Intelligent synchronization with configurable conflict resolution
- **👀 Real-time Monitoring**: File system monitoring with automatic sync triggers
- **🛡️ Comprehensive Error Handling**: Retry logic, exponential backoff, and graceful failure modes
- **🔐 Security First**: SSH key authentication with proper permission handling
- **⚙️ Performance Optimized**: Bandwidth throttling, compression, and efficient rsync options
- **📊 Rich CLI Interface**: Beautiful terminal output with progress indicators and status tables
- **🏗️ Multiple Execution Modes**: Manual, cron-compatible, and real-time monitoring
- **📝 Professional Logging**: Comprehensive logging with configurable levels and rotation

## 🎯 Use Cases

### Scientific Computing & Research
- Sync analysis scripts, datasets, and results between local workstation and EC2 compute instances
- Automatically transfer generated plots, models, and publications
- Handle large datasets with bandwidth optimization

### Web Development
- Deploy code, assets, and configuration files to EC2 instances
- Sync build artifacts and static files
- Maintain development/staging/production environments

### Data Science & Machine Learning
- Transfer notebooks, datasets, and trained models
- Sync experiment results and visualizations
- Handle large data files with efficient compression

### DevOps & Infrastructure
- Sync configuration files and deployment scripts
- Transfer logs and monitoring data
- Maintain backup copies of critical files

## 📖 Documentation

### Basic Commands

```bash
# Check sync status and directory information
ec2-sync status

# Perform bidirectional synchronization
ec2-sync sync

# Push local changes to remote only
ec2-sync push

# Pull remote changes to local only
ec2-sync pull

# Show what would be synced (dry run)
ec2-sync sync --dry-run

# Use specific configuration file
ec2-sync sync --config /path/to/config.yaml

# Use specific profile
ec2-sync sync --profile production
```

## ⚙️ Configuration

### Basic Configuration

Create `~/.ec2-sync.yaml`:

```yaml
project_name: "my-project"
project_description: "My EC2 sync project"

aws:
  instance_name: "my-ec2-instance"  # or use instance_id
  region: "us-east-1"
  profile: "default"
  auto_start_instance: true

ssh:
  user: "ubuntu"
  key_file: "~/.ssh/my-key.pem"

directory_mappings:
  - name: "project_files"
    local_path: "~/my-project"
    remote_path: "~/my-project"
    enabled: true

conflict_resolution: "newer"  # newer, local, remote, manual
```

## 🔧 Prerequisites

### System Requirements

- **Local Machine**: macOS, Linux, or Windows WSL with Python 3.8+
- **EC2 Instance**: Ubuntu/Amazon Linux with rsync installed
- **Network**: SSH access to EC2 instance

### Required Tools

- `python3` with pip
- `aws` CLI v2 configured with appropriate credentials
- `ssh` client
- `rsync` (usually pre-installed)

### AWS Permissions

Your AWS credentials need the following EC2 permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:StartInstances",
                "ec2:StopInstances"
            ],
            "Resource": "*"
        }
    ]
}
```

## 🔄 Automation

### Cron Jobs

Set up automated synchronization:

```bash
# Every 15 minutes
ec2-sync-setup cron --schedule "*/15 * * * *"

# Every hour during business hours
ec2-sync-setup cron --schedule "0 9-17 * * 1-5"
```

### Real-time Sync

Monitor file changes and sync automatically:

```bash
# Start monitoring (syncs after 5-second delay)
ec2-sync-watch

# Custom delay and minimum interval
ec2-sync-watch --delay 10 --min-interval 60
```

## 🐛 Troubleshooting

### Common Issues

1. **SSH Connection Failed**
   ```bash
   # Check SSH key permissions
   chmod 600 ~/.ssh/your-key.pem
   
   # Test SSH manually
   ssh -i ~/.ssh/your-key.pem ubuntu@your-ec2-ip
   
   # Run diagnostics
   ec2-sync-doctor
   ```

2. **Instance Not Found**
   ```bash
   # Verify instance ID/name and region
   aws ec2 describe-instances --region us-east-1
   
   # Check configuration
   ec2-sync-setup validate
   ```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone repository
git clone https://github.com/ec2-dynamic-sync/ec2-dynamic-sync.git
cd ec2-dynamic-sync

# Install in development mode
pip install -e .[dev]

# Run tests
pytest

# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Click](https://click.palletsprojects.com/) for CLI interface
- Uses [Rich](https://rich.readthedocs.io/) for beautiful terminal output
- Powered by [Boto3](https://boto3.amazonaws.com/) for AWS integration
- File monitoring with [Watchdog](https://python-watchdog.readthedocs.io/)

---

**Made with ❤️ for the developer community**
