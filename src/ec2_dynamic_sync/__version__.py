"""Version information for EC2 Dynamic Sync."""

__version__ = "1.0.0"
__version_info__ = tuple(int(i) for i in __version__.split("."))

# Version history and compatibility
MINIMUM_PYTHON_VERSION = (3, 8)
MINIMUM_AWS_CLI_VERSION = "2.0.0"
MINIMUM_RSYNC_VERSION = "3.0.0"

# Feature flags for version compatibility
FEATURES = {
    "real_time_sync": True,
    "bidirectional_sync": True,
    "dynamic_ip_handling": True,
    "auto_instance_management": True,
    "conflict_resolution": True,
    "bandwidth_throttling": True,
    "ssh_key_management": True,
    "configuration_profiles": True,
    "plugin_system": False,  # Future feature
    "web_interface": False,  # Future feature
}

# Compatibility matrix
COMPATIBILITY = {
    "aws_cli": {
        "minimum": "2.0.0",
        "recommended": "2.13.0",
        "tested": ["2.13.0", "2.14.0", "2.15.0"],
    },
    "python": {
        "minimum": "3.8.0",
        "recommended": "3.11.0",
        "tested": ["3.8", "3.9", "3.10", "3.11", "3.12"],
    },
    "rsync": {
        "minimum": "3.0.0",
        "recommended": "3.2.0",
        "tested": ["3.1.3", "3.2.3", "3.2.7"],
    },
}


def get_version() -> str:
    """Get the current version string."""
    return __version__


def get_version_info() -> tuple:
    """Get the current version as a tuple."""
    return __version_info__


def is_feature_enabled(feature: str) -> bool:
    """Check if a feature is enabled in this version."""
    return FEATURES.get(feature, False)


def get_compatibility_info() -> dict:
    """Get compatibility information for external tools."""
    return COMPATIBILITY.copy()
