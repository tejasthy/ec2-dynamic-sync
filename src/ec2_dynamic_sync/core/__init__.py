"""
Core modules for EC2 Dynamic Sync.

This package contains the core functionality for EC2 file synchronization,
including AWS management, SSH connectivity, rsync operations, and configuration.
"""

from .aws_manager import AWSManager
from .config_manager import ConfigManager
from .enhanced_rsync import (
    EnhancedRsyncManager,
    ExcludePatternManager,
    ProgressReporter,
)
from .exceptions import (
    AWSConnectionError,
    ConfigurationError,
    DependencyError,
    EC2SyncError,
    InstanceNotFoundError,
    PermissionError,
    SSHConnectionError,
    SyncError,
    ValidationError,
)
from .models import (
    AWSConfig,
    ConflictResolution,
    DirectoryInfo,
    DirectoryMapping,
    LoggingConfig,
    LogLevel,
    ProfileConfig,
    SSHConfig,
    SyncConfig,
    SyncMode,
    SyncOptions,
    SyncResult,
    SyncStats,
    SyncStatus,
)
from .rsync_manager import RsyncManager
from .ssh_manager import SSHManager
from .sync_daemon import BidirectionalSyncDaemon, ChangeEvent, SyncState
from .sync_orchestrator import SyncOrchestrator

__all__ = [
    # Core managers
    "AWSManager",
    "SSHManager",
    "ConfigManager",
    "RsyncManager",
    "SyncOrchestrator",
    # Advanced sync components
    "BidirectionalSyncDaemon",
    "EnhancedRsyncManager",
    "ExcludePatternManager",
    "ProgressReporter",
    "ChangeEvent",
    "SyncState",
    # Models and data structures
    "SyncConfig",
    "AWSConfig",
    "SSHConfig",
    "DirectoryMapping",
    "SyncOptions",
    "SyncResult",
    "SyncStats",
    "DirectoryInfo",
    "SyncStatus",
    "ProfileConfig",
    "LoggingConfig",
    # Enums
    "ConflictResolution",
    "SyncMode",
    "LogLevel",
    # Exceptions
    "EC2SyncError",
    "ConfigurationError",
    "AWSConnectionError",
    "SSHConnectionError",
    "SyncError",
    "ValidationError",
    "InstanceNotFoundError",
    "PermissionError",
    "DependencyError",
]
