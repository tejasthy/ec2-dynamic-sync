"""
Configuration management for EC2 Dynamic Sync.

This module handles loading, validating, and managing configuration files
with support for multiple profiles and environment-specific overrides.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .exceptions import ConfigurationError, ValidationError
from .models import LoggingConfig, ProfileConfig, SyncConfig


class ConfigManager:
    """Manages configuration loading, validation, and profile handling."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration manager.

        Args:
            config_path: Path to configuration file. If None, auto-detect.
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = self._resolve_config_path(config_path)
        self.config: Optional[SyncConfig] = None
        self.profiles: Dict[str, ProfileConfig] = {}
        self.active_profile: Optional[str] = None

        if self.config_path and os.path.exists(self.config_path):
            self.load_config()

    def _resolve_config_path(self, config_path: Optional[str]) -> Optional[str]:
        """Resolve configuration file path with auto-detection."""
        if config_path:
            return os.path.expanduser(config_path)

        # Auto-detect configuration file
        search_paths = [
            # Current directory
            "./ec2-sync.yaml",
            "./ec2-sync.yml",
            "./.ec2-sync.yaml",
            "./.ec2-sync.yml",
            # User home directory
            "~/.ec2-sync/config.yaml",
            "~/.ec2-sync/config.yml",
            "~/.ec2-sync.yaml",
            "~/.ec2-sync.yml",
            # System-wide configuration
            "/etc/ec2-sync/config.yaml",
            "/etc/ec2-sync/config.yml",
        ]

        for path in search_paths:
            expanded_path = os.path.expanduser(path)
            if os.path.exists(expanded_path):
                self.logger.debug(f"Found configuration file: {expanded_path}")
                return expanded_path

        return None

    def load_config(self, config_path: Optional[str] = None) -> SyncConfig:
        """Load configuration from file.

        Args:
            config_path: Path to configuration file

        Returns:
            Loaded and validated configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        if config_path:
            self.config_path = os.path.expanduser(config_path)

        if not self.config_path or not os.path.exists(self.config_path):
            raise ConfigurationError(
                f"Configuration file not found: {self.config_path}",
                config_path=self.config_path,
            )

        try:
            with open(self.config_path, "r") as f:
                raw_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Invalid YAML in configuration file: {e}", config_path=self.config_path
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to read configuration file: {e}", config_path=self.config_path
            )

        # Handle profiles if present
        if "profiles" in raw_config:
            self._load_profiles(raw_config["profiles"])

            # Use active profile or default
            active_profile = raw_config.get("active_profile", "default")
            if active_profile in self.profiles:
                self.active_profile = active_profile
                config_data = self.profiles[active_profile].sync_config.dict()
            else:
                raise ConfigurationError(
                    f"Active profile '{active_profile}' not found in profiles",
                    config_path=self.config_path,
                )
        else:
            # Single configuration (no profiles)
            config_data = raw_config

        # Validate and create configuration
        try:
            self.config = SyncConfig(**config_data)
        except Exception as e:
            raise ConfigurationError(
                f"Configuration validation failed: {e}",
                config_path=self.config_path,
                validation_errors=[str(e)],
            )

        self.logger.info(f"Loaded configuration from {self.config_path}")
        return self.config

    def _load_profiles(self, profiles_data: Dict[str, Any]):
        """Load configuration profiles."""
        self.profiles = {}

        for profile_name, profile_data in profiles_data.items():
            try:
                # Handle profile inheritance
                if "inherits_from" in profile_data:
                    parent_name = profile_data["inherits_from"]
                    if parent_name in self.profiles:
                        # Merge with parent profile
                        parent_config = self.profiles[parent_name].sync_config.dict()
                        merged_config = self._merge_configs(
                            parent_config, profile_data.get("sync_config", {})
                        )
                        profile_data["sync_config"] = merged_config

                profile = ProfileConfig(name=profile_name, **profile_data)
                self.profiles[profile_name] = profile

            except Exception as e:
                raise ConfigurationError(
                    f"Failed to load profile '{profile_name}': {e}",
                    config_path=self.config_path,
                )

    def _merge_configs(
        self, base_config: Dict[str, Any], override_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recursively merge configuration dictionaries."""
        merged = base_config.copy()

        for key, value in override_config.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._merge_configs(merged[key], value)
            else:
                merged[key] = value

        return merged

    def get_config(self, profile: Optional[str] = None) -> SyncConfig:
        """Get configuration for specified profile.

        Args:
            profile: Profile name. If None, use active profile or main config.

        Returns:
            Configuration object

        Raises:
            ConfigurationError: If profile not found or no configuration loaded
        """
        if profile:
            if profile not in self.profiles:
                raise ConfigurationError(f"Profile '{profile}' not found")
            return self.profiles[profile].sync_config

        if self.config is None:
            raise ConfigurationError("No configuration loaded")

        return self.config

    def list_profiles(self) -> List[str]:
        """List available configuration profiles."""
        return list(self.profiles.keys())

    def get_active_profile(self) -> Optional[str]:
        """Get the name of the active profile."""
        return self.active_profile

    def validate_config(self, config_path: Optional[str] = None) -> List[str]:
        """Validate configuration file and return list of issues.

        Args:
            config_path: Path to configuration file

        Returns:
            List of validation error messages (empty if valid)
        """
        issues = []

        try:
            if config_path:
                temp_manager = ConfigManager(config_path)
            else:
                temp_manager = self

            temp_manager.load_config()

        except ConfigurationError as e:
            issues.extend(e.validation_errors or [e.message])
        except Exception as e:
            issues.append(f"Unexpected error: {e}")

        return issues

    def create_default_config(
        self, output_path: str, template_type: str = "basic"
    ) -> str:
        """Create a default configuration file.

        Args:
            output_path: Path where to create the configuration file
            template_type: Type of template (basic, advanced, scientific, web_dev)

        Returns:
            Path to created configuration file
        """
        templates = {
            "basic": self._get_basic_template(),
            "advanced": self._get_advanced_template(),
            "scientific": self._get_scientific_template(),
            "web_dev": self._get_web_dev_template(),
        }

        if template_type not in templates:
            raise ValidationError(
                f"Unknown template type: {template_type}",
                field_name="template_type",
                expected_type="one of: " + ", ".join(templates.keys()),
            )

        template_data = templates[template_type]

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Write configuration file
        with open(output_path, "w") as f:
            yaml.dump(template_data, f, default_flow_style=False, indent=2)

        self.logger.info(
            f"Created {template_type} configuration template: {output_path}"
        )
        return output_path

    def _get_basic_template(self) -> Dict[str, Any]:
        """Get basic configuration template."""
        return {
            "project_name": "my-project",
            "project_description": "My EC2 sync project",
            "aws": {
                "instance_name": "my-ec2-instance",
                "region": "us-east-1",
                "profile": "default",
                "auto_start_instance": True,
                "max_wait_time": 600,
            },
            "ssh": {
                "user": "ubuntu",
                "key_file": "~/.ssh/my-key.pem",
                "connect_timeout": 10,
                "max_retries": 3,
                "retry_delay": 10,
            },
            "directory_mappings": [
                {
                    "name": "project_files",
                    "local_path": "~/my-project",
                    "remote_path": "~/my-project",
                    "enabled": True,
                }
            ],
            "conflict_resolution": "newer",
            "max_retries": 3,
            "retry_delay": 30,
        }

    def _get_advanced_template(self) -> Dict[str, Any]:
        """Get advanced configuration template with profiles."""
        return {
            "active_profile": "development",
            "profiles": {
                "development": {
                    "description": "Development environment",
                    "sync_config": {
                        "project_name": "my-project-dev",
                        "aws": {
                            "instance_name": "my-project-dev",
                            "region": "us-east-1",
                            "auto_start_instance": True,
                        },
                        "ssh": {"user": "ubuntu", "key_file": "~/.ssh/dev-key.pem"},
                        "directory_mappings": [
                            {
                                "name": "source_code",
                                "local_path": "~/projects/my-project/src",
                                "remote_path": "~/my-project/src",
                                "enabled": True,
                            },
                            {
                                "name": "data",
                                "local_path": "~/projects/my-project/data",
                                "remote_path": "~/my-project/data",
                                "enabled": True,
                            },
                        ],
                        "sync_options": {"delete": False, "bandwidth_limit": "1000"},
                    },
                },
                "production": {
                    "description": "Production environment",
                    "inherits_from": "development",
                    "sync_config": {
                        "project_name": "my-project-prod",
                        "aws": {
                            "instance_name": "my-project-prod",
                            "auto_start_instance": False,
                        },
                        "ssh": {"key_file": "~/.ssh/prod-key.pem"},
                        "sync_options": {"delete": True, "verbose": False},
                    },
                },
            },
        }

    def _get_scientific_template(self) -> Dict[str, Any]:
        """Get scientific computing template."""
        basic = self._get_basic_template()
        basic.update(
            {
                "project_name": "scientific-analysis",
                "project_description": "Scientific data analysis project",
                "directory_mappings": [
                    {
                        "name": "scripts",
                        "local_path": "~/analysis/scripts",
                        "remote_path": "~/analysis/scripts",
                        "enabled": True,
                    },
                    {
                        "name": "data",
                        "local_path": "~/analysis/data",
                        "remote_path": "~/analysis/data",
                        "enabled": True,
                        "exclude_patterns": ["*.tmp", "*.cache"],
                    },
                    {
                        "name": "results",
                        "local_path": "~/analysis/results",
                        "remote_path": "~/analysis/results",
                        "enabled": True,
                    },
                    {
                        "name": "notebooks",
                        "local_path": "~/analysis/notebooks",
                        "remote_path": "~/analysis/notebooks",
                        "enabled": True,
                        "exclude_patterns": [".ipynb_checkpoints/"],
                    },
                ],
                "sync_options": {
                    "exclude_patterns": [
                        "*.log",
                        "*.tmp",
                        "__pycache__/",
                        ".DS_Store",
                        "*.pyc",
                        ".git/",
                        ".ipynb_checkpoints/",
                        "*.cache",
                        "*.pickle",
                        "*.pkl",
                    ]
                },
            }
        )
        return basic

    def _get_web_dev_template(self) -> Dict[str, Any]:
        """Get web development template."""
        basic = self._get_basic_template()
        basic.update(
            {
                "project_name": "web-application",
                "project_description": "Web development project",
                "directory_mappings": [
                    {
                        "name": "source",
                        "local_path": "~/webapp/src",
                        "remote_path": "~/webapp/src",
                        "enabled": True,
                    },
                    {
                        "name": "assets",
                        "local_path": "~/webapp/assets",
                        "remote_path": "~/webapp/assets",
                        "enabled": True,
                    },
                    {
                        "name": "config",
                        "local_path": "~/webapp/config",
                        "remote_path": "~/webapp/config",
                        "enabled": True,
                    },
                ],
                "sync_options": {
                    "exclude_patterns": [
                        "*.log",
                        "*.tmp",
                        "__pycache__/",
                        ".DS_Store",
                        "*.pyc",
                        ".git/",
                        "node_modules/",
                        "dist/",
                        "build/",
                        ".next/",
                        ".nuxt/",
                        "coverage/",
                    ]
                },
            }
        )
        return basic
