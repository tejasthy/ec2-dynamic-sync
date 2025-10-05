#!/usr/bin/env python3
"""
Test suite for CLI commands in EC2 Dynamic Sync.

This module tests all the CLI commands to ensure they work correctly
and provide proper error handling.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ec2_dynamic_sync.cli import daemon, doctor, setup, watch
from ec2_dynamic_sync.core import ConfigManager, SyncOrchestrator


class TestSetupCLI:
    """Test the setup CLI commands."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "test-config.yaml")

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ec2_dynamic_sync.cli.setup.check_dependencies")
    @patch("ec2_dynamic_sync.cli.setup.get_aws_instances")
    def test_setup_init_basic(self, mock_instances, mock_deps):
        """Test basic setup initialization."""
        # Mock dependencies
        mock_deps.return_value = {
            "aws": True,
            "ssh": True,
            "rsync": True,
            "python": True,
        }
        mock_instances.return_value = ([], None)  # (instances_list, error_message)

        # Mock user inputs (for Prompt.ask only, Confirm.ask is handled separately)
        inputs = [
            "test-project",  # project name
            "Test project",  # description
            "name",  # instance choice
            "test-instance",  # instance name
            "us-east-1",  # region
            "default",  # profile
            # auto start is handled by Confirm.ask, not Prompt.ask
            "ubuntu",  # ssh user
            "~/.ssh/test-key.pem",  # ssh key
            "22",  # ssh port
            "10",  # timeout
            "test-mapping",  # mapping name
            "~/test-local",  # local path
            "~/test-remote",  # remote path
            # enable mapping is handled by Confirm.ask
            # no more mappings is handled by Confirm.ask
            # archive, verbose, compress, delete, progress are handled by Confirm.ask
            "0",  # bandwidth limit
            "newer",  # conflict resolution
        ]

        with patch("ec2_dynamic_sync.cli.setup.Prompt.ask", side_effect=inputs):
            # Confirm.ask calls in order:
            # 1. Auto-start instance? -> True
            # 2. Enable this mapping? -> True
            # 3. Add another directory mapping? -> False
            # 4. Use archive mode? -> True
            # 5. Enable verbose output? -> False
            # 6. Enable compression? -> True
            # 7. Delete files that don't exist on source? -> False
            # 8. Show progress during sync? -> True
            with patch(
                "ec2_dynamic_sync.cli.setup.Confirm.ask",
                side_effect=[True, True, False, True, False, True, False, True],
            ):
                with patch("ec2_dynamic_sync.cli.setup.save_config") as mock_save:
                    mock_save.return_value = self.config_file

                    result = self.runner.invoke(
                        setup.init, ["--config", self.config_file]
                    )

                    assert result.exit_code == 0
                    assert "Setup completed successfully" in result.output

    def test_setup_validate_missing_config(self):
        """Test validation with missing config file."""
        result = self.runner.invoke(
            setup.validate, ["--config", "/nonexistent/config.yaml"]
        )

        assert result.exit_code == 1
        assert "Configuration validation failed" in result.output

    @patch("ec2_dynamic_sync.cli.setup.SyncOrchestrator.from_config_file")
    def test_setup_test_connectivity(self, mock_orchestrator):
        """Test connectivity testing."""
        # Mock orchestrator
        mock_orch = Mock()
        mock_orch.test_connectivity.return_value = {
            "overall_success": True,
            "ssh_connectivity": True,
        }
        mock_orch.get_sync_status.return_value = {"directories": {}}
        mock_orch.aws_manager.get_instance_info.return_value = {
            "instance_id": "i-123456",
            "state": "running",
        }
        mock_orchestrator.return_value = mock_orch

        result = self.runner.invoke(setup.test, ["--config", self.config_file])

        assert result.exit_code == 0
        assert "All tests passed" in result.output


class TestDoctorCLI:
    """Test the doctor CLI commands."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    @patch("ec2_dynamic_sync.cli.doctor.get_system_info")
    @patch("ec2_dynamic_sync.cli.doctor.check_python_dependencies")
    @patch("ec2_dynamic_sync.cli.doctor.check_system_commands")
    @patch("ec2_dynamic_sync.cli.doctor.check_network_connectivity")
    @patch("ec2_dynamic_sync.cli.doctor.check_configuration")
    @patch("ec2_dynamic_sync.cli.doctor.performance_benchmark")
    def test_doctor_console_output(
        self,
        mock_perf,
        mock_config,
        mock_network,
        mock_commands,
        mock_deps,
        mock_system,
    ):
        """Test doctor command with console output."""
        # Mock all the check functions
        mock_system.return_value = {
            "platform": "Linux",
            "python_version": "3.9.0",
            "architecture": "64bit",
            "processor": "x86_64",
            "memory_total": 8589934592,
            "memory_available": 4294967296,
            "disk_usage": Mock(total=1000000000, free=500000000, used=500000000),
            "cpu_count": 4,
            "boot_time": 1234567890,
        }

        mock_deps.return_value = {
            "boto3": {
                "installed": True,
                "version": "1.26.0",
                "status": "ok",
                "purpose": "AWS SDK",
            },
            "click": {
                "installed": True,
                "version": "8.0.0",
                "status": "ok",
                "purpose": "CLI framework",
            },
        }

        mock_commands.return_value = {
            "aws": {
                "available": True,
                "version": "aws-cli/2.0.0",
                "required": False,
                "status": "ok",
                "purpose": "AWS CLI",
            },
            "ssh": {
                "available": True,
                "version": "OpenSSH_8.0",
                "required": True,
                "status": "ok",
                "purpose": "SSH client",
            },
        }

        mock_network.return_value = {
            "aws_api": {"reachable": True, "host": "ec2.amazonaws.com", "status": "ok"},
            "github": {"reachable": True, "host": "github.com", "status": "ok"},
        }

        mock_config.return_value = {"config_found": True, "status": "ok", "issues": []}

        mock_perf.return_value = {
            "cpu_benchmark": {
                "duration_seconds": 0.5,
                "operations_per_second": 2000000,
                "status": "ok",
            },
            "memory_status": {
                "total_gb": 8.0,
                "available_gb": 4.0,
                "usage_percent": 50.0,
                "status": "ok",
            },
            "disk_status": {
                "total_gb": 1000.0,
                "free_gb": 500.0,
                "usage_percent": 50.0,
                "status": "ok",
            },
        }

        result = self.runner.invoke(doctor.doctor, ["--output", "console"])

        assert result.exit_code == 0
        assert "EC2 Dynamic Sync Diagnostic Report" in result.output

    def test_doctor_json_output(self):
        """Test doctor command with JSON output."""
        with patch("ec2_dynamic_sync.cli.doctor.get_system_info") as mock_system:
            mock_system.return_value = {"platform": "Linux"}

            with patch(
                "ec2_dynamic_sync.cli.doctor.check_python_dependencies"
            ) as mock_deps:
                mock_deps.return_value = {}

                with patch(
                    "ec2_dynamic_sync.cli.doctor.check_system_commands"
                ) as mock_commands:
                    mock_commands.return_value = {}

                    with patch(
                        "ec2_dynamic_sync.cli.doctor.check_network_connectivity"
                    ) as mock_network:
                        mock_network.return_value = {}

                        with patch(
                            "ec2_dynamic_sync.cli.doctor.check_configuration"
                        ) as mock_config:
                            mock_config.return_value = {"config_found": False}

                            with patch(
                                "ec2_dynamic_sync.cli.doctor.performance_benchmark"
                            ) as mock_perf:
                                mock_perf.return_value = {}

                                result = self.runner.invoke(
                                    doctor.doctor, ["--output", "json"]
                                )

                                assert result.exit_code == 0
                                # Should be valid JSON
                                import json

                                json.loads(result.output)


class TestWatchCLI:
    """Test the watch CLI commands."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ec2_dynamic_sync.cli.watch.SyncOrchestrator.from_config_file")
    @patch("ec2_dynamic_sync.cli.watch.Observer")
    def test_watch_no_ui_mode(self, mock_observer, mock_orchestrator):
        """Test watch command in no-UI mode."""
        # Mock orchestrator
        mock_orch = Mock()
        mock_orch.test_connectivity.return_value = {"overall_success": True}
        mock_orch.config.directory_mappings = [
            Mock(enabled=True, local_path=self.temp_dir, name="test")
        ]
        mock_orchestrator.return_value = mock_orch

        # Mock observer
        mock_obs = Mock()
        mock_observer.return_value = mock_obs

        # Run with timeout to avoid infinite loop
        import signal

        def timeout_handler(signum, frame):
            raise KeyboardInterrupt()

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(1)  # 1 second timeout

        try:
            result = self.runner.invoke(
                watch.watch, ["--no-ui", "--delay", "1", "--min-interval", "5"]
            )

            # Should exit cleanly on KeyboardInterrupt
            assert result.exit_code == 130
        finally:
            signal.alarm(0)


class TestDaemonCLI:
    """Test the daemon CLI commands."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ec2_dynamic_sync.cli.daemon.DaemonController")
    def test_daemon_status_not_running(self, mock_controller_class):
        """Test daemon status when not running."""
        mock_controller = Mock()
        mock_controller.get_status.return_value = {"running": False}
        mock_controller_class.return_value = mock_controller

        result = self.runner.invoke(daemon.status)

        assert result.exit_code == 0
        assert "Daemon is not running" in result.output

    @patch("ec2_dynamic_sync.cli.daemon.DaemonController")
    def test_daemon_status_running(self, mock_controller_class):
        """Test daemon status when running."""
        mock_controller = Mock()
        mock_controller.get_status.return_value = {
            "running": True,
            "last_sync_time": 1234567890,
            "pending_changes": 5,
            "local_changes": 3,
            "remote_changes": 2,
            "conflicts": 0,
            "sync_in_progress": False,
        }
        mock_controller_class.return_value = mock_controller

        result = self.runner.invoke(daemon.status)

        assert result.exit_code == 0
        assert "Running" in result.output
        assert "Pending Changes" in result.output

    @patch("ec2_dynamic_sync.cli.daemon.DaemonController")
    def test_daemon_start_stop(self, mock_controller_class):
        """Test daemon start and stop commands."""
        mock_controller = Mock()
        mock_controller.start_daemon.return_value = True
        mock_controller.stop_daemon.return_value = True
        mock_controller_class.return_value = mock_controller

        # Test start
        result = self.runner.invoke(daemon.start)
        assert result.exit_code == 0

        # Test stop
        result = self.runner.invoke(daemon.stop)
        assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__])
