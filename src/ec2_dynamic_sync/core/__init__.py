"""
Core modules for EC2 Dynamic Sync.

This package contains the core functionality for EC2 file synchronization,
including AWS management, SSH connectivity, rsync operations, and configuration.
"""

from .aws_manager import AWSManager
from .ssh_manager import SSHManager
from .config_manager import ConfigManager
from .models import (
    SyncConfig,
    AWSConfig,
    SSHConfig,
    DirectoryMapping,
    SyncOptions,
    SyncResult,
    SyncStats,
    DirectoryInfo,
    SyncStatus,
    ProfileConfig,
    LoggingConfig,
    ConflictResolution,
    SyncMode,
    LogLevel,
)
from .exceptions import (
    EC2SyncError,
    ConfigurationError,
    AWSConnectionError,
    SSHConnectionError,
    SyncError,
    ValidationError,
    InstanceNotFoundError,
    PermissionError,
    DependencyError,
)

__all__ = [
    # Core managers
    "AWSManager",
    "SSHManager", 
    "ConfigManager",
    
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
