#!/usr/bin/env python3
"""
Integration tests for EC2 Dynamic Sync.

This module provides comprehensive integration tests that verify
the entire sync workflow from configuration to execution.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ec2_dynamic_sync.core import (
    BidirectionalSyncDaemon,
    ConfigManager,
    EnhancedRsyncManager,
    ExcludePatternManager,
    SyncOrchestrator,
)
from ec2_dynamic_sync.core.models import DirectoryMapping, SyncConfig, SyncMode


class TestConfigurationWorkflow:
    """Test the complete configuration workflow."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "test-config.yaml")

        # Create test SSH key file for validation
        self.test_key_file = os.path.join(self.temp_dir, "test-key.pem")
        with open(self.test_key_file, "w") as f:
            f.write(
                "-----BEGIN PRIVATE KEY-----\ntest key content\n-----END PRIVATE KEY-----\n"
            )
        os.chmod(self.test_key_file, 0o600)

        # Create test configuration
        self.test_config = {
            "project_name": "test-project",
            "project_description": "Test project for integration testing",
            "aws": {
                "instance_name": "test-instance",
                "region": "us-east-1",
                "profile": "default",
                "auto_start_instance": True,
            },
            "ssh": {
                "user": "ubuntu",
                "key_file": self.test_key_file,
                "port": 22,
                "connect_timeout": 10,
            },
            "directory_mappings": [
                {
                    "name": "test-mapping",
                    "local_path": "~/test-local",
                    "remote_path": "~/test-remote",
                    "enabled": True,
                }
            ],
            "sync_options": {
                "archive": True,
                "verbose": False,
                "compress": True,
                "delete": False,
                "progress": True,
                "bandwidth_limit": "0",
            },
            "conflict_resolution": "newer",
        }

        # Save test configuration
        with open(self.config_file, "w") as f:
            yaml.dump(self.test_config, f)

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_loading_and_validation(self):
        """Test configuration loading and validation."""
        config_manager = ConfigManager(self.config_file)
        config = config_manager.get_config()

        assert config.project_name == "test-project"
        assert config.aws.instance_name == "test-instance"
        assert config.aws.region == "us-east-1"
        assert len(config.directory_mappings) == 1
        assert config.directory_mappings[0].name == "test-mapping"

    @patch("ec2_dynamic_sync.core.aws_manager.boto3.Session")
    def test_orchestrator_initialization(self, mock_session):
        """Test sync orchestrator initialization."""
        # Mock AWS session
        mock_session.return_value = Mock()

        orchestrator = SyncOrchestrator.from_config_file(self.config_file)

        assert orchestrator.config.project_name == "test-project"
        assert orchestrator.aws_manager is not None
        assert orchestrator.ssh_manager is not None
        assert orchestrator.rsync_manager is not None


class TestSyncWorkflow:
    """Test the complete sync workflow."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.local_dir = os.path.join(self.temp_dir, "local")
        self.remote_dir = os.path.join(self.temp_dir, "remote")

        # Create directories
        os.makedirs(self.local_dir, exist_ok=True)
        os.makedirs(self.remote_dir, exist_ok=True)

        # Create test files
        with open(os.path.join(self.local_dir, "test1.txt"), "w") as f:
            f.write("Local file content")

        with open(os.path.join(self.remote_dir, "test2.txt"), "w") as f:
            f.write("Remote file content")

        # Create test SSH key file
        self.test_key_file = os.path.join(self.temp_dir, "test-key.pem")
        with open(self.test_key_file, "w") as f:
            f.write(
                "-----BEGIN PRIVATE KEY-----\ntest key content\n-----END PRIVATE KEY-----\n"
            )
        os.chmod(self.test_key_file, 0o600)

        # Create test configuration
        self.config = SyncConfig(
            project_name="test-sync",
            project_description="Test sync project",
            aws={
                "instance_name": "test-instance",
                "region": "us-east-1",
                "profile": "default",
                "auto_start_instance": True,
            },
            ssh={
                "user": "ubuntu",
                "key_file": self.test_key_file,
                "port": 22,
                "connect_timeout": 10,
            },
            directory_mappings=[
                DirectoryMapping(
                    name="test-mapping",
                    local_path=self.local_dir,
                    remote_path=self.remote_dir,
                    enabled=True,
                )
            ],
            sync_options={
                "archive": True,
                "verbose": False,
                "compress": True,
                "delete": False,
                "progress": True,
                "bandwidth_limit": "0",
            },
            conflict_resolution="newer",
        )

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ec2_dynamic_sync.core.enhanced_rsync.subprocess.Popen")
    @patch("ec2_dynamic_sync.core.ssh_manager.subprocess.run")
    def test_dry_run_sync(self, mock_ssh_run, mock_rsync_popen):
        """Test dry run sync operation."""
        # Mock SSH connectivity test
        mock_ssh_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Mock rsync dry run
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.poll.side_effect = [None, None, 0] + [
            0
        ] * 10  # Return None twice, then 0 to exit loop
        mock_process.stdout.readline.side_effect = [
            "sending incremental file list\n",
            "test1.txt\n",
            "",  # Empty string to exit loop
        ] + [
            ""
        ] * 10  # Add more empty strings to avoid StopIteration
        mock_process.communicate.return_value = ("", "")
        mock_rsync_popen.return_value = mock_process

        orchestrator = SyncOrchestrator(self.config)

        # Mock AWS and SSH managers
        orchestrator.aws_manager = Mock()
        orchestrator.aws_manager.get_instance_info.return_value = {
            "instance_id": "i-123456",
            "state": "running",
            "public_ip": "1.2.3.4",
        }

        orchestrator.ssh_manager = Mock()
        orchestrator.ssh_manager.test_connection.return_value = True
        orchestrator.ssh_manager.config = Mock()
        orchestrator.ssh_manager.config.user = "ubuntu"

        # Perform dry run
        results = orchestrator.sync_all_directories(
            mode=SyncMode.BIDIRECTIONAL, dry_run=True
        )

        assert "test-mapping" in results["directories"]
        assert results["directories"]["test-mapping"]["success"] is True


class TestExcludePatterns:
    """Test exclude pattern functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

        # Create .ec2syncignore file
        ignore_content = """
# Test ignore patterns
*.tmp
*.log
node_modules/
.git/
__pycache__/
!important.tmp
"""

        with open(os.path.join(self.temp_dir, ".ec2syncignore"), "w") as f:
            f.write(ignore_content)

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_exclude_pattern_loading(self):
        """Test loading and parsing of exclude patterns."""
        manager = ExcludePatternManager(self.temp_dir)

        # Test exclusions - *.tmp is excluded by default patterns
        assert (
            manager.should_exclude("test.tmp") is True
        )  # Excluded by default *.tmp pattern
        assert manager.should_exclude("test.log") is True  # Excluded by custom pattern
        assert manager.should_exclude("node_modules/package.json") is True
        assert manager.should_exclude(".git/config") is True
        assert manager.should_exclude("__pycache__/module.pyc") is True

        # Test normal files
        assert manager.should_exclude("test.txt") is False
        assert manager.should_exclude("src/main.py") is False

    def test_rsync_exclude_generation(self):
        """Test generation of rsync exclude arguments."""
        manager = ExcludePatternManager(self.temp_dir)
        excludes = manager.get_rsync_excludes()

        # Should contain default excludes
        assert "--exclude" in excludes
        assert "*.tmp" in excludes
        assert "node_modules" in excludes

        # Should contain custom excludes from file
        assert "*.log" in excludes


class TestBidirectionalDaemon:
    """Test the bidirectional sync daemon."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.local_dir = os.path.join(self.temp_dir, "local")
        os.makedirs(self.local_dir, exist_ok=True)

        # Create test SSH key file
        self.test_key_file = os.path.join(self.temp_dir, "test-key.pem")
        with open(self.test_key_file, "w") as f:
            f.write(
                "-----BEGIN PRIVATE KEY-----\ntest key content\n-----END PRIVATE KEY-----\n"
            )
        os.chmod(self.test_key_file, 0o600)

        # Create test configuration
        self.config = SyncConfig(
            project_name="test-daemon",
            project_description="Test daemon project",
            aws={
                "instance_name": "test-instance",
                "region": "us-east-1",
                "profile": "default",
                "auto_start_instance": True,
            },
            ssh={
                "user": "ubuntu",
                "key_file": self.test_key_file,
                "port": 22,
                "connect_timeout": 10,
            },
            directory_mappings=[
                DirectoryMapping(
                    name="test-mapping",
                    local_path=self.local_dir,
                    remote_path="~/remote",
                    enabled=True,
                )
            ],
            sync_options={
                "archive": True,
                "verbose": False,
                "compress": True,
                "delete": False,
                "progress": True,
                "bandwidth_limit": "0",
            },
            conflict_resolution="newer",
        )

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_daemon_initialization(self):
        """Test daemon initialization."""
        daemon = BidirectionalSyncDaemon(self.config, poll_interval=30.0)

        assert daemon.config == self.config
        assert daemon.poll_interval == 30.0
        assert not daemon.running
        assert len(daemon.local_detectors) == 1
        assert "test-mapping" in daemon.local_detectors

    def test_daemon_status(self):
        """Test daemon status reporting."""
        daemon = BidirectionalSyncDaemon(self.config)
        status = daemon.get_status()

        assert "running" in status
        assert "last_sync_time" in status
        assert "pending_changes" in status
        assert "local_changes" in status
        assert "remote_changes" in status
        assert "conflicts" in status
        assert "sync_in_progress" in status

        assert status["running"] is False
        assert status["sync_in_progress"] is False


class TestErrorHandling:
    """Test error handling and recovery."""

    def test_invalid_config_handling(self):
        """Test handling of invalid configuration."""
        with pytest.raises(Exception):
            ConfigManager("/nonexistent/config.yaml").get_config()

    def test_missing_dependencies_handling(self):
        """Test handling of missing system dependencies."""
        # This would be tested with actual system calls in a real environment
        pass

    @patch("ec2_dynamic_sync.core.aws_manager.boto3.Session")
    def test_aws_connection_failure(self, mock_session):
        """Test handling of AWS connection failures."""
        # Mock AWS session to raise an exception
        mock_session.side_effect = Exception("AWS connection failed")

        # Create test SSH key file
        temp_dir = tempfile.mkdtemp()
        test_key_file = os.path.join(temp_dir, "test-key.pem")
        with open(test_key_file, "w") as f:
            f.write(
                "-----BEGIN PRIVATE KEY-----\ntest key content\n-----END PRIVATE KEY-----\n"
            )
        os.chmod(test_key_file, 0o600)

        config = SyncConfig(
            project_name="test-error",
            project_description="Test error handling",
            aws={
                "instance_name": "test-instance",
                "region": "us-east-1",
                "profile": "default",
                "auto_start_instance": True,
            },
            ssh={
                "user": "ubuntu",
                "key_file": test_key_file,
                "port": 22,
                "connect_timeout": 10,
            },
            directory_mappings=[
                DirectoryMapping(
                    name="test-mapping",
                    local_path=temp_dir,
                    remote_path="~/remote",
                    enabled=True,
                )
            ],
            sync_options={
                "archive": True,
                "verbose": False,
                "compress": True,
                "delete": False,
                "progress": True,
                "bandwidth_limit": "0",
            },
            conflict_resolution="newer",
        )

        with pytest.raises(Exception):
            SyncOrchestrator(config)


if __name__ == "__main__":
    pytest.main([__file__])
