"""
Exception classes for EC2 Dynamic Sync.

This module defines all custom exceptions used throughout the EC2 Dynamic Sync
application, providing clear error hierarchies and detailed error information.
"""

from typing import Optional, Dict, Any


class EC2SyncError(Exception):
    """Base exception for all EC2 Dynamic Sync errors."""
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize EC2SyncError.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code for programmatic handling
            details: Additional error details and context
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
    
    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} (Details: {self.details})"
        return self.message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for serialization."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


class ConfigurationError(EC2SyncError):
    """Raised when there are configuration-related errors."""
    
    def __init__(
        self, 
        message: str, 
        config_path: Optional[str] = None,
        validation_errors: Optional[list] = None
    ):
        """Initialize ConfigurationError.
        
        Args:
            message: Error message
            config_path: Path to the configuration file with issues
            validation_errors: List of specific validation errors
        """
        details = {}
        if config_path:
            details["config_path"] = config_path
        if validation_errors:
            details["validation_errors"] = validation_errors
        
        super().__init__(message, "CONFIG_ERROR", details)
        self.config_path = config_path
        self.validation_errors = validation_errors or []


class AWSConnectionError(EC2SyncError):
    """Raised when AWS connection or authentication fails."""
    
    def __init__(
        self, 
        message: str, 
        aws_error_code: Optional[str] = None,
        region: Optional[str] = None,
        profile: Optional[str] = None
    ):
        """Initialize AWSConnectionError.
        
        Args:
            message: Error message
            aws_error_code: AWS-specific error code
            region: AWS region where error occurred
            profile: AWS profile being used
        """
        details = {}
        if aws_error_code:
            details["aws_error_code"] = aws_error_code
        if region:
            details["region"] = region
        if profile:
            details["profile"] = profile
        
        super().__init__(message, "AWS_CONNECTION_ERROR", details)
        self.aws_error_code = aws_error_code
        self.region = region
        self.profile = profile


class SSHConnectionError(EC2SyncError):
    """Raised when SSH connection fails."""
    
    def __init__(
        self, 
        message: str, 
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        key_file: Optional[str] = None
    ):
        """Initialize SSHConnectionError.
        
        Args:
            message: Error message
            host: SSH host that failed
            port: SSH port
            username: SSH username
            key_file: SSH key file path
        """
        details = {}
        if host:
            details["host"] = host
        if port:
            details["port"] = port
        if username:
            details["username"] = username
        if key_file:
            details["key_file"] = key_file
        
        super().__init__(message, "SSH_CONNECTION_ERROR", details)
        self.host = host
        self.port = port
        self.username = username
        self.key_file = key_file


class SyncError(EC2SyncError):
    """Raised when file synchronization fails."""
    
    def __init__(
        self, 
        message: str, 
        sync_direction: Optional[str] = None,
        local_path: Optional[str] = None,
        remote_path: Optional[str] = None,
        rsync_exit_code: Optional[int] = None
    ):
        """Initialize SyncError.
        
        Args:
            message: Error message
            sync_direction: Direction of sync (local_to_remote, remote_to_local, bidirectional)
            local_path: Local path involved in sync
            remote_path: Remote path involved in sync
            rsync_exit_code: Exit code from rsync command
        """
        details = {}
        if sync_direction:
            details["sync_direction"] = sync_direction
        if local_path:
            details["local_path"] = local_path
        if remote_path:
            details["remote_path"] = remote_path
        if rsync_exit_code is not None:
            details["rsync_exit_code"] = rsync_exit_code
        
        super().__init__(message, "SYNC_ERROR", details)
        self.sync_direction = sync_direction
        self.local_path = local_path
        self.remote_path = remote_path
        self.rsync_exit_code = rsync_exit_code


class ValidationError(EC2SyncError):
    """Raised when input validation fails."""
    
    def __init__(
        self, 
        message: str, 
        field_name: Optional[str] = None,
        field_value: Optional[Any] = None,
        expected_type: Optional[str] = None
    ):
        """Initialize ValidationError.
        
        Args:
            message: Error message
            field_name: Name of the field that failed validation
            field_value: Value that failed validation
            expected_type: Expected type or format
        """
        details = {}
        if field_name:
            details["field_name"] = field_name
        if field_value is not None:
            details["field_value"] = str(field_value)
        if expected_type:
            details["expected_type"] = expected_type
        
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field_name = field_name
        self.field_value = field_value
        self.expected_type = expected_type


class InstanceNotFoundError(AWSConnectionError):
    """Raised when EC2 instance cannot be found."""
    
    def __init__(
        self, 
        message: str, 
        instance_id: Optional[str] = None,
        instance_name: Optional[str] = None
    ):
        """Initialize InstanceNotFoundError.
        
        Args:
            message: Error message
            instance_id: EC2 instance ID that wasn't found
            instance_name: EC2 instance name that wasn't found
        """
        details = {}
        if instance_id:
            details["instance_id"] = instance_id
        if instance_name:
            details["instance_name"] = instance_name
        
        super().__init__(message, "INSTANCE_NOT_FOUND", details)
        self.instance_id = instance_id
        self.instance_name = instance_name


class PermissionError(EC2SyncError):
    """Raised when permission-related errors occur."""
    
    def __init__(
        self, 
        message: str, 
        resource_type: Optional[str] = None,
        resource_path: Optional[str] = None,
        required_permissions: Optional[list] = None
    ):
        """Initialize PermissionError.
        
        Args:
            message: Error message
            resource_type: Type of resource (file, directory, aws_service, etc.)
            resource_path: Path to the resource
            required_permissions: List of required permissions
        """
        details = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_path:
            details["resource_path"] = resource_path
        if required_permissions:
            details["required_permissions"] = required_permissions
        
        super().__init__(message, "PERMISSION_ERROR", details)
        self.resource_type = resource_type
        self.resource_path = resource_path
        self.required_permissions = required_permissions or []


class DependencyError(EC2SyncError):
    """Raised when required dependencies are missing or incompatible."""
    
    def __init__(
        self, 
        message: str, 
        dependency_name: Optional[str] = None,
        required_version: Optional[str] = None,
        found_version: Optional[str] = None
    ):
        """Initialize DependencyError.
        
        Args:
            message: Error message
            dependency_name: Name of the missing/incompatible dependency
            required_version: Required version
            found_version: Version that was found (if any)
        """
        details = {}
        if dependency_name:
            details["dependency_name"] = dependency_name
        if required_version:
            details["required_version"] = required_version
        if found_version:
            details["found_version"] = found_version
        
        super().__init__(message, "DEPENDENCY_ERROR", details)
        self.dependency_name = dependency_name
        self.required_version = required_version
        self.found_version = found_version
