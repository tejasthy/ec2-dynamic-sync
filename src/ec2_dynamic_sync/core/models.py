"""
Pydantic models for EC2 Dynamic Sync configuration and data structures.

This module defines all data models used throughout the application,
providing validation, serialization, and type safety.
"""

from typing import Optional, List, Dict, Any, Union
from pathlib import Path
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
import os


class ConflictResolution(str, Enum):
    """Conflict resolution strategies for bidirectional sync."""
    NEWER = "newer"
    LOCAL = "local"
    REMOTE = "remote"
    MANUAL = "manual"


class SyncMode(str, Enum):
    """Sync operation modes."""
    BIDIRECTIONAL = "bidirectional"
    LOCAL_TO_REMOTE = "local_to_remote"
    REMOTE_TO_LOCAL = "remote_to_local"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AWSConfig(BaseModel):
    """AWS configuration settings."""
    
    instance_id: Optional[str] = Field(None, description="EC2 instance ID")
    instance_name: Optional[str] = Field(None, description="EC2 instance name tag")
    region: str = Field("us-east-1", description="AWS region")
    profile: str = Field("default", description="AWS CLI profile")
    auto_start_instance: bool = Field(True, description="Auto-start stopped instances")
    max_wait_time: int = Field(600, description="Maximum wait time for instance operations")
    
    @model_validator(mode='after')
    def validate_instance_identification(self):
        """Ensure either instance_id or instance_name is provided."""
        if not self.instance_id and not self.instance_name:
            raise ValueError("Either instance_id or instance_name must be provided")
        
        return self
    
    @field_validator('max_wait_time')
    @classmethod
    def validate_max_wait_time(cls, v):
        """Validate max_wait_time is reasonable."""
        if v < 60 or v > 3600:
            raise ValueError("max_wait_time must be between 60 and 3600 seconds")
        return v


class SSHConfig(BaseModel):
    """SSH configuration settings."""
    
    user: str = Field("ubuntu", description="SSH username")
    key_file: str = Field(description="Path to SSH private key file")
    port: int = Field(22, description="SSH port")
    connect_timeout: int = Field(10, description="SSH connection timeout")
    strict_host_checking: bool = Field(False, description="Enable strict host key checking")
    max_retries: int = Field(3, description="Maximum SSH retry attempts")
    retry_delay: int = Field(10, description="Delay between SSH retries")
    
    @field_validator('key_file')
    @classmethod
    def validate_key_file(cls, v):
        """Validate SSH key file exists and has correct permissions."""
        expanded_path = os.path.expanduser(v)
        if not os.path.exists(expanded_path):
            raise ValueError(f"SSH key file not found: {expanded_path}")
        
        # Check permissions (should be 600)
        stat_info = os.stat(expanded_path)
        permissions = oct(stat_info.st_mode)[-3:]
        if permissions != '600':
            raise ValueError(
                f"SSH key file has incorrect permissions {permissions}, should be 600. "
                f"Run: chmod 600 {expanded_path}"
            )
        
        return v
    
    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        """Validate SSH port is in valid range."""
        if v < 1 or v > 65535:
            raise ValueError("SSH port must be between 1 and 65535")
        return v


class DirectoryMapping(BaseModel):
    """Configuration for a single directory sync mapping."""
    
    name: str = Field(description="Descriptive name for this mapping")
    local_path: str = Field(description="Local directory path")
    remote_path: str = Field(description="Remote directory path")
    enabled: bool = Field(True, description="Whether this mapping is enabled")
    exclude_patterns: List[str] = Field(default_factory=list, description="Patterns to exclude")
    
    @field_validator('local_path')
    @classmethod
    def validate_local_path(cls, v):
        """Validate local path exists or can be created."""
        expanded_path = os.path.expanduser(v)
        parent_dir = os.path.dirname(expanded_path)
        
        if not os.path.exists(parent_dir):
            raise ValueError(f"Parent directory does not exist: {parent_dir}")
        
        return expanded_path


class SyncOptions(BaseModel):
    """Rsync operation options."""
    
    archive: bool = Field(True, description="Use archive mode (-a)")
    verbose: bool = Field(True, description="Verbose output (-v)")
    compress: bool = Field(True, description="Compress during transfer (-z)")
    progress: bool = Field(True, description="Show progress (--progress)")
    delete: bool = Field(False, description="Delete extraneous files (--delete)")
    partial: bool = Field(True, description="Keep partial transfers (--partial)")
    dry_run: bool = Field(False, description="Dry run mode (--dry-run)")
    backup: bool = Field(False, description="Make backups (--backup)")
    bandwidth_limit: Optional[str] = Field(None, description="Bandwidth limit (--bwlimit)")
    exclude_patterns: List[str] = Field(
        default_factory=lambda: [
            "*.log", "*.tmp", "__pycache__/", ".DS_Store", "*.pyc",
            ".git/", "node_modules/", "*.swp", "*.swo", ".vscode/", "Thumbs.db"
        ],
        description="Global exclude patterns"
    )
    
    @field_validator('bandwidth_limit')
    @classmethod
    def validate_bandwidth_limit(cls, v):
        """Validate bandwidth limit format."""
        if v is not None and v.strip():
            try:
                int(v)
            except ValueError:
                raise ValueError("bandwidth_limit must be a number (KB/s)")
        return v


class SyncConfig(BaseModel):
    """Main synchronization configuration."""
    
    project_name: str = Field(description="Project name for identification")
    project_description: Optional[str] = Field(None, description="Project description")
    
    aws: AWSConfig = Field(description="AWS configuration")
    ssh: SSHConfig = Field(description="SSH configuration")
    
    directory_mappings: List[DirectoryMapping] = Field(
        description="Directory sync mappings"
    )
    sync_options: SyncOptions = Field(
        default_factory=SyncOptions,
        description="Rsync options"
    )
    
    # Sync behavior
    conflict_resolution: ConflictResolution = Field(
        ConflictResolution.NEWER,
        description="Conflict resolution strategy"
    )
    
    # Automation settings
    max_retries: int = Field(3, description="Maximum retry attempts")
    retry_delay: int = Field(30, description="Delay between retries")
    exponential_backoff: bool = Field(True, description="Use exponential backoff")
    
    @field_validator('directory_mappings')
    @classmethod
    def validate_directory_mappings(cls, v):
        """Ensure at least one directory mapping is provided."""
        if not v:
            raise ValueError("At least one directory mapping must be provided")
        return v


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    log_file: Optional[str] = Field(None, description="Log file path")
    console_level: LogLevel = Field(LogLevel.INFO, description="Console log level")
    file_level: LogLevel = Field(LogLevel.DEBUG, description="File log level")
    max_log_size: str = Field("10MB", description="Maximum log file size")
    backup_count: int = Field(5, description="Number of log backups to keep")
    format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )
    date_format: str = Field("%Y-%m-%d %H:%M:%S", description="Date format string")


class SyncStats(BaseModel):
    """Statistics from a sync operation."""
    
    files_transferred: int = Field(0, description="Number of files transferred")
    files_skipped: int = Field(0, description="Number of files skipped")
    total_size: int = Field(0, description="Total bytes transferred")
    transfer_rate: Optional[float] = Field(None, description="Transfer rate in bytes/sec")
    speedup: float = Field(0.0, description="Rsync speedup factor")
    duration: float = Field(0.0, description="Operation duration in seconds")


class SyncResult(BaseModel):
    """Result of a sync operation."""
    
    success: bool = Field(description="Whether the operation succeeded")
    operation: str = Field(description="Type of operation performed")
    sync_direction: Optional[SyncMode] = Field(None, description="Direction of sync")
    local_path: Optional[str] = Field(None, description="Local path involved")
    remote_path: Optional[str] = Field(None, description="Remote path involved")
    
    stats: Optional[SyncStats] = Field(None, description="Transfer statistics")
    duration: float = Field(0.0, description="Total operation duration")
    
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_code: Optional[str] = Field(None, description="Error code if failed")
    
    stdout: Optional[str] = Field(None, description="Command stdout")
    stderr: Optional[str] = Field(None, description="Command stderr")
    returncode: Optional[int] = Field(None, description="Command return code")


class DirectoryInfo(BaseModel):
    """Information about a directory (local or remote)."""
    
    path: str = Field(description="Directory path")
    exists: bool = Field(description="Whether directory exists")
    size: Optional[str] = Field(None, description="Human-readable size")
    file_count: Optional[int] = Field(None, description="Number of files")
    last_modified: Optional[str] = Field(None, description="Last modification time")
    permissions: Optional[str] = Field(None, description="Directory permissions")


class SyncStatus(BaseModel):
    """Current sync status information."""
    
    instance_id: Optional[str] = Field(None, description="EC2 instance ID")
    instance_state: Optional[str] = Field(None, description="EC2 instance state")
    host: Optional[str] = Field(None, description="Current host IP")
    ssh_connected: bool = Field(False, description="SSH connection status")
    
    directory_mappings: Dict[str, Dict[str, DirectoryInfo]] = Field(
        default_factory=dict,
        description="Status of each directory mapping"
    )
    
    last_sync: Optional[str] = Field(None, description="Last sync timestamp")
    sync_in_progress: bool = Field(False, description="Whether sync is currently running")


class ProfileConfig(BaseModel):
    """Configuration profile for different environments."""
    
    name: str = Field(description="Profile name")
    description: Optional[str] = Field(None, description="Profile description")
    inherits_from: Optional[str] = Field(None, description="Parent profile to inherit from")
    
    sync_config: SyncConfig = Field(description="Sync configuration for this profile")
    logging_config: Optional[LoggingConfig] = Field(None, description="Logging configuration")
    
    # Environment-specific overrides
    environment_variables: Dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set"
    )
    
    active: bool = Field(True, description="Whether this profile is active")
