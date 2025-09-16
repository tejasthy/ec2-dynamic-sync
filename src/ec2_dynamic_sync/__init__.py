"""
EC2 Dynamic Sync - Professional-grade EC2 file synchronization

A comprehensive tool for synchronizing files between local machines and EC2 instances
with dynamic IP handling, bidirectional sync, and real-time monitoring capabilities.

Key Features:
- Dynamic IP resolution for EC2 instances
- Automatic instance start/stop management
- Bidirectional synchronization with conflict resolution
- Real-time file monitoring and sync
- Comprehensive error handling and retry logic
- Multiple execution modes (manual, cron, real-time)
- Professional logging and monitoring
- Cross-platform compatibility

Example Usage:
    >>> from ec2_dynamic_sync import SyncOrchestrator
    >>> orchestrator = SyncOrchestrator(config_path="config.yaml")
    >>> results = orchestrator.sync_all_directories()
    >>> print(f"Sync completed: {results['overall_success']}")

CLI Usage:
    $ ec2-sync init          # Interactive setup
    $ ec2-sync status        # Check sync status
    $ ec2-sync sync          # Perform bidirectional sync
    $ ec2-sync push          # Local to remote sync
    $ ec2-sync pull          # Remote to local sync
    $ ec2-sync watch         # Real-time monitoring
    $ ec2-sync doctor        # Health check and diagnostics
"""

from .__version__ import (
    __version__,
    __version_info__,
    get_version,
    get_version_info,
    is_feature_enabled,
    get_compatibility_info,
    FEATURES,
    COMPATIBILITY,
)

# Core components
from .core.sync_orchestrator import SyncOrchestrator
from .core.aws_manager import AWSManager
from .core.ssh_manager import SSHManager
from .core.rsync_manager import RsyncManager
from .core.config_manager import ConfigManager

# Exceptions
from .core.exceptions import (
    EC2SyncError,
    ConfigurationError,
    AWSConnectionError,
    SSHConnectionError,
    SyncError,
    ValidationError,
)

# Configuration and utilities
from .core.models import SyncConfig, AWSConfig, SSHConfig, SyncResult

__all__ = [
    # Version information
    "__version__",
    "__version_info__",
    "get_version",
    "get_version_info",
    "is_feature_enabled",
    "get_compatibility_info",
    "FEATURES",
    "COMPATIBILITY",
    
    # Core classes
    "SyncOrchestrator",
    "AWSManager", 
    "SSHManager",
    "RsyncManager",
    "ConfigManager",
    
    # Exceptions
    "EC2SyncError",
    "ConfigurationError",
    "AWSConnectionError", 
    "SSHConnectionError",
    "SyncError",
    "ValidationError",
    
    # Models
    "SyncConfig",
    "AWSConfig", 
    "SSHConfig",
    "SyncResult",
]

# Package metadata
__title__ = "ec2-dynamic-sync"
__description__ = "Professional-grade EC2 file synchronization with dynamic IP handling"
__url__ = "https://github.com/ec2-dynamic-sync/ec2-dynamic-sync"
__author__ = "EC2 Dynamic Sync Contributors"
__author_email__ = "ec2-dynamic-sync@example.com"
__license__ = "MIT"
__copyright__ = "Copyright 2024 EC2 Dynamic Sync Contributors"

# Compatibility check
import sys
from .__version__ import MINIMUM_PYTHON_VERSION

if sys.version_info < MINIMUM_PYTHON_VERSION:
    raise RuntimeError(
        f"EC2 Dynamic Sync requires Python {'.'.join(map(str, MINIMUM_PYTHON_VERSION))} "
        f"or higher. You are using Python {sys.version_info.major}.{sys.version_info.minor}."
    )
