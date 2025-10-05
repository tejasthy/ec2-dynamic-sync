#!/usr/bin/env python3
"""
Sync Orchestrator for EC2 Dynamic Sync

This module coordinates all sync operations and provides the main interface
for the synchronization system.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .aws_manager import AWSManager
from .config_manager import ConfigManager
from .enhanced_rsync import EnhancedRsyncManager
from .exceptions import AWSConnectionError, EC2SyncError, SSHConnectionError, SyncError
from .models import SyncConfig, SyncMode, SyncResult
from .ssh_manager import SSHManager


class SyncOrchestrator:
    """Main orchestrator for EC2 synchronization operations."""

    def __init__(self, config: SyncConfig):
        """Initialize the sync orchestrator."""
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize managers
        self.aws_manager = AWSManager(config.aws)
        self.ssh_manager = SSHManager(config.ssh)
        self.rsync_manager = EnhancedRsyncManager(config, self.ssh_manager)

        # State tracking
        self.current_host = None
        self.instance_id = None

        self.logger.info("EC2 Dynamic Sync Orchestrator initialized")

    @classmethod
    def from_config_file(
        cls, config_path: Optional[str] = None, profile: Optional[str] = None
    ):
        """Create orchestrator from configuration file."""
        config_manager = ConfigManager()
        # Note: Profile support not yet implemented in ConfigManager
        config = config_manager.load_config(config_path)
        return cls(config)

    def prepare_instance(self) -> bool:
        """Prepare EC2 instance for synchronization."""
        try:
            self.logger.info("Preparing EC2 instance for sync...")

            # Get instance information
            instance_info = self.aws_manager.get_instance_info()
            if not instance_info:
                self.logger.error("Failed to get instance information")
                return False

            self.instance_id = instance_info["instance_id"]
            instance_state = instance_info["state"]

            self.logger.info(
                f"Instance {self.instance_id} is in state: {instance_state}"
            )

            # Start instance if needed
            if instance_state != "running":
                if self.config.aws.auto_start_instance:
                    self.logger.info("Starting EC2 instance...")
                    if not self.aws_manager.start_instance():
                        self.logger.error("Failed to start instance")
                        return False

                    # Wait for instance to be running
                    if not self.aws_manager.wait_for_instance_running():
                        self.logger.error("Instance failed to reach running state")
                        return False
                else:
                    self.logger.error(
                        "Instance is not running and auto-start is disabled"
                    )
                    return False

            # Get current IP address
            self.current_host = self.aws_manager.get_instance_ip()
            if not self.current_host:
                self.logger.error("Failed to get instance IP address")
                return False

            self.logger.info(f"Instance IP: {self.current_host}")

            # Test SSH connectivity
            if not self.ssh_manager.test_connectivity(self.current_host):
                self.logger.error("SSH connectivity test failed")
                return False

            self.logger.info("Instance preparation completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Instance preparation failed: {e}")
            return False

    def sync_all_directories(
        self, mode: SyncMode = SyncMode.BIDIRECTIONAL, dry_run: bool = False
    ) -> Dict[str, Any]:
        """Sync all configured directories."""
        if not self.current_host:
            if not self.prepare_instance():
                return {
                    "overall_success": False,
                    "error": "Instance preparation failed",
                }

        mappings = [m for m in self.config.directory_mappings if m.enabled]
        results = {
            "overall_success": True,
            "directories": {},
            "summary": {
                "total_dirs": len(mappings),
                "successful_dirs": 0,
                "failed_dirs": 0,
                "total_duration": 0,
            },
        }

        start_time = time.time()

        for mapping in mappings:
            self.logger.info(f"Syncing directory: {mapping.local_path}")

            try:
                if mode == SyncMode.BIDIRECTIONAL:
                    result = self.rsync_manager.sync_bidirectional(
                        self.current_host, mapping, dry_run
                    )
                elif mode == SyncMode.LOCAL_TO_REMOTE:
                    result = self.rsync_manager.sync_local_to_remote(
                        self.current_host, mapping, dry_run
                    )
                elif mode == SyncMode.REMOTE_TO_LOCAL:
                    result = self.rsync_manager.sync_remote_to_local(
                        self.current_host, mapping, dry_run
                    )
                else:
                    result = {"success": False, "error": f"Unknown sync mode: {mode}"}

                results["directories"][mapping.name] = result

                if result.get("success") or result.get("overall_success"):
                    results["summary"]["successful_dirs"] += 1
                else:
                    results["summary"]["failed_dirs"] += 1
                    results["overall_success"] = False

            except Exception as e:
                self.logger.error(f"Exception syncing {mapping.local_path}: {e}")
                results["directories"][mapping.local_path] = {
                    "success": False,
                    "error": str(e),
                }
                results["summary"]["failed_dirs"] += 1
                results["overall_success"] = False

        results["summary"]["total_duration"] = time.time() - start_time

        # Log summary
        summary = results["summary"]
        self.logger.info(
            f"Sync completed: {summary['successful_dirs']}/{summary['total_dirs']} "
            f"directories successful in {summary['total_duration']:.1f}s"
        )

        return results

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and directory information."""
        if not self.current_host:
            if not self.prepare_instance():
                return {"success": False, "error": "Instance preparation failed"}

        mappings = [m for m in self.config.directory_mappings if m.enabled]
        status = {
            "instance_id": self.instance_id,
            "host": self.current_host,
            "directories": {},
        }

        for mapping in mappings:
            try:
                info = self.rsync_manager.get_directory_info(self.current_host, mapping)
                status["directories"][mapping.name] = info
            except Exception as e:
                self.logger.error(f"Error getting status for {mapping.local_path}: {e}")
                status["directories"][mapping.name] = {"error": str(e)}

        return status

    def test_connectivity(self) -> Dict[str, Any]:
        """Test connectivity to EC2 instance."""
        results = {
            "aws_connectivity": False,
            "instance_reachable": False,
            "ssh_connectivity": False,
            "overall_success": False,
        }

        try:
            # Test AWS connectivity
            instance_info = self.aws_manager.get_instance_info()
            if instance_info:
                results["aws_connectivity"] = True
                results["instance_reachable"] = True

                # Get IP and test SSH
                ip = self.aws_manager.get_instance_ip()
                if ip:
                    self.current_host = ip
                    if self.ssh_manager.test_connectivity(ip):
                        results["ssh_connectivity"] = True
                        results["overall_success"] = True

        except Exception as e:
            results["error"] = str(e)

        return results
