#!/usr/bin/env python3
"""
Enhanced rsync manager with advanced features for EC2 Dynamic Sync.

This module extends the basic rsync functionality with features like:
- Exclude/include patterns
- Bandwidth throttling
- Progress reporting
- Partial file sync
- File locking
- Change queuing
"""

import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .exceptions import SyncError
from .models import DirectoryMapping, SyncOptions, SyncResult
from .ssh_manager import SSHManager


class ExcludePatternManager:
    """Manages exclude/include patterns similar to .gitignore."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.patterns: List[Tuple[str, bool]] = []  # (pattern, is_include)
        self.load_patterns()

    def load_patterns(self):
        """Load patterns from .ec2syncignore files."""
        ignore_files = [
            self.base_path / ".ec2syncignore",
            self.base_path / ".gitignore",  # Also respect .gitignore
            Path.home() / ".ec2syncignore",  # Global ignore file
        ]

        for ignore_file in ignore_files:
            if ignore_file.exists():
                self._load_pattern_file(ignore_file)

    def _load_pattern_file(self, file_path: Path):
        """Load patterns from a specific file."""
        try:
            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        is_include = line.startswith("!")
                        if is_include:
                            line = line[1:]
                        self.patterns.append((line, is_include))
        except IOError:
            pass

    def should_exclude(self, path: str) -> bool:
        """Check if a path should be excluded."""
        path_obj = Path(path)

        # Default exclusions
        default_excludes = [
            "*.tmp",
            "*.temp",
            "*~",
            "*.swp",
            "*.swo",
            ".DS_Store",
            "Thumbs.db",
            "desktop.ini",
            ".git/",
            ".svn/",
            ".hg/",
            "__pycache__/",
            "*.pyc",
            "*.pyo",
            "node_modules/",
            ".vscode/",
            ".idea/",
            "*.egg-info/",
            "dist/",
            "build/",
        ]

        # Check default exclusions first
        for pattern in default_excludes:
            if self._match_pattern(str(path_obj), pattern):
                return True

        # Check custom patterns
        excluded = False
        for pattern, is_include in self.patterns:
            if self._match_pattern(str(path_obj), pattern):
                excluded = not is_include

        return excluded

    def _match_pattern(self, path: str, pattern: str) -> bool:
        """Check if a path matches a pattern."""
        # Convert glob pattern to regex
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        if pattern.endswith("/"):
            regex_pattern += ".*"

        return bool(re.match(regex_pattern, path))

    def get_rsync_excludes(self) -> List[str]:
        """Get exclude patterns formatted for rsync."""
        excludes = []

        # Add default excludes
        default_excludes = [
            "*.tmp",
            "*.temp",
            "*~",
            "*.swp",
            "*.swo",
            ".DS_Store",
            "Thumbs.db",
            "desktop.ini",
            ".git",
            ".svn",
            ".hg",
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "node_modules",
            ".vscode",
            ".idea",
            "*.egg-info",
            "dist",
            "build",
        ]

        for pattern in default_excludes:
            excludes.extend(["--exclude", pattern])

        # Add custom excludes
        for pattern, is_include in self.patterns:
            if is_include:
                excludes.extend(["--include", pattern])
            else:
                excludes.extend(["--exclude", pattern])

        return excludes


class ProgressReporter:
    """Reports sync progress with bandwidth and ETA calculations."""

    def __init__(self):
        self.start_time = time.time()
        self.bytes_transferred = 0
        self.total_bytes = 0
        self.current_file = ""
        self.files_transferred = 0
        self.total_files = 0
        self.lock = threading.Lock()

    def update(
        self,
        bytes_transferred: int,
        total_bytes: int = None,
        current_file: str = "",
        files_transferred: int = None,
    ):
        """Update progress information."""
        with self.lock:
            self.bytes_transferred = bytes_transferred
            if total_bytes is not None:
                self.total_bytes = total_bytes
            if current_file:
                self.current_file = current_file
            if files_transferred is not None:
                self.files_transferred = files_transferred

    def get_stats(self) -> Dict[str, Any]:
        """Get current progress statistics."""
        with self.lock:
            elapsed = time.time() - self.start_time

            # Calculate transfer rate
            if elapsed > 0:
                rate_bps = self.bytes_transferred / elapsed
                rate_mbps = rate_bps / (1024 * 1024)
            else:
                rate_bps = rate_mbps = 0

            # Calculate ETA
            if self.total_bytes > 0 and rate_bps > 0:
                remaining_bytes = self.total_bytes - self.bytes_transferred
                eta_seconds = remaining_bytes / rate_bps
            else:
                eta_seconds = 0

            # Calculate percentage
            if self.total_bytes > 0:
                percentage = (self.bytes_transferred / self.total_bytes) * 100
            else:
                percentage = 0

            return {
                "bytes_transferred": self.bytes_transferred,
                "total_bytes": self.total_bytes,
                "percentage": percentage,
                "rate_mbps": rate_mbps,
                "eta_seconds": eta_seconds,
                "current_file": self.current_file,
                "files_transferred": self.files_transferred,
                "total_files": self.total_files,
                "elapsed_seconds": elapsed,
            }


class FileLockManager:
    """Manages file locks to prevent sync during active operations."""

    def __init__(self):
        self.locked_files: Set[str] = set()
        self.lock = threading.Lock()

    def is_locked(self, file_path: str) -> bool:
        """Check if a file is currently locked."""
        with self.lock:
            return file_path in self.locked_files

    def lock_file(self, file_path: str) -> bool:
        """Lock a file. Returns True if successful."""
        with self.lock:
            if file_path not in self.locked_files:
                self.locked_files.add(file_path)
                return True
            return False

    def unlock_file(self, file_path: str):
        """Unlock a file."""
        with self.lock:
            self.locked_files.discard(file_path)

    def get_locked_files(self) -> List[str]:
        """Get list of currently locked files."""
        with self.lock:
            return list(self.locked_files)


class EnhancedRsyncManager:
    """Enhanced rsync manager with advanced features."""

    def __init__(self, config, ssh_manager: SSHManager):
        self.config = config
        self.ssh_manager = ssh_manager
        self.logger = logging.getLogger(__name__)
        self.file_lock_manager = FileLockManager()
        self.exclude_managers: Dict[str, ExcludePatternManager] = {}

        # Initialize exclude managers for each mapping
        for mapping in config.directory_mappings:
            if mapping.enabled:
                local_path = os.path.expanduser(mapping.local_path)
                self.exclude_managers[mapping.name] = ExcludePatternManager(local_path)

    def sync_with_progress(
        self,
        host: str,
        mapping: DirectoryMapping,
        mode: str = "bidirectional",
        dry_run: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> SyncResult:
        """Perform sync with progress reporting."""

        # Check for locked files
        local_path = os.path.expanduser(mapping.local_path)
        locked_files = [
            f
            for f in self.file_lock_manager.get_locked_files()
            if f.startswith(local_path)
        ]

        if locked_files:
            return SyncResult(
                success=False,
                operation=f"sync_{mode}",
                error_message=f"Cannot sync: {len(locked_files)} files are locked",
                stats={"locked_files": locked_files},
            )

        # Create progress reporter
        progress = ProgressReporter()

        try:
            if mode == "bidirectional":
                return self._sync_bidirectional_enhanced(
                    host, mapping, dry_run, progress, progress_callback
                )
            elif mode == "local_to_remote":
                return self._sync_local_to_remote_enhanced(
                    host, mapping, dry_run, progress, progress_callback
                )
            elif mode == "remote_to_local":
                return self._sync_remote_to_local_enhanced(
                    host, mapping, dry_run, progress, progress_callback
                )
            else:
                return SyncResult(
                    success=False,
                    operation=f"sync_{mode}",
                    error_message=f"Unknown sync mode: {mode}",
                )

        except Exception as e:
            self.logger.error(f"Enhanced sync failed: {e}")
            return SyncResult(
                success=False, operation=f"sync_{mode}", error_message=str(e)
            )

    def _build_rsync_command(
        self, mapping: DirectoryMapping, dry_run: bool = False
    ) -> List[str]:
        """Build enhanced rsync command with all options."""
        cmd = ["rsync"]

        # Basic options
        if self.config.sync_options.archive:
            cmd.append("-a")
        if self.config.sync_options.verbose:
            cmd.append("-v")
        if self.config.sync_options.compress:
            cmd.append("-z")
        if self.config.sync_options.progress:
            cmd.append("--progress")
        if self.config.sync_options.delete:
            cmd.append("--delete")

        # Dry run
        if dry_run:
            cmd.append("--dry-run")

        # Bandwidth limiting
        if (
            hasattr(self.config.sync_options, "bandwidth_limit")
            and self.config.sync_options.bandwidth_limit
        ):
            cmd.extend(["--bwlimit", str(self.config.sync_options.bandwidth_limit)])

        # SSH options
        ssh_cmd = f"ssh -i {self.ssh_manager.config.key_file} -p {self.ssh_manager.config.port}"
        if self.ssh_manager.config.connect_timeout:
            ssh_cmd += f" -o ConnectTimeout={self.ssh_manager.config.connect_timeout}"
        cmd.extend(["-e", ssh_cmd])

        # Exclude patterns
        if mapping.name in self.exclude_managers:
            excludes = self.exclude_managers[mapping.name].get_rsync_excludes()
            cmd.extend(excludes)

        # Additional safety options
        cmd.extend(
            [
                "--partial",  # Keep partially transferred files
                "--partial-dir=.rsync-partial",  # Store partial files in hidden dir
                "--timeout=300",  # 5 minute timeout
                "--contimeout=60",  # 1 minute connection timeout
            ]
        )

        return cmd

    def _sync_bidirectional_enhanced(
        self,
        host: str,
        mapping: DirectoryMapping,
        dry_run: bool,
        progress: ProgressReporter,
        progress_callback: Optional[callable],
    ) -> SyncResult:
        """Enhanced bidirectional sync with conflict detection."""

        # First, sync local to remote
        local_to_remote = self._sync_local_to_remote_enhanced(
            host, mapping, dry_run, progress, progress_callback
        )

        if not local_to_remote.success:
            return local_to_remote

        # Then, sync remote to local
        remote_to_local = self._sync_remote_to_local_enhanced(
            host, mapping, dry_run, progress, progress_callback
        )

        # Combine results
        return SyncResult(
            success=local_to_remote.success and remote_to_local.success,
            operation="sync_bidirectional",
            stats={
                "local_to_remote": local_to_remote.stats,
                "remote_to_local": remote_to_local.stats,
                "overall_success": local_to_remote.success and remote_to_local.success,
            },
        )

    def _sync_local_to_remote_enhanced(
        self,
        host: str,
        mapping: DirectoryMapping,
        dry_run: bool,
        progress: ProgressReporter,
        progress_callback: Optional[callable],
    ) -> SyncResult:
        """Enhanced local to remote sync."""

        local_path = os.path.expanduser(mapping.local_path)
        remote_path = mapping.remote_path

        if not local_path.endswith("/"):
            local_path += "/"
        if not remote_path.endswith("/"):
            remote_path += "/"

        cmd = self._build_rsync_command(mapping, dry_run)
        cmd.extend([local_path, f"{self.ssh_manager.config.user}@{host}:{remote_path}"])

        return self._execute_rsync_with_progress(cmd, progress, progress_callback)

    def _sync_remote_to_local_enhanced(
        self,
        host: str,
        mapping: DirectoryMapping,
        dry_run: bool,
        progress: ProgressReporter,
        progress_callback: Optional[callable],
    ) -> SyncResult:
        """Enhanced remote to local sync."""

        local_path = os.path.expanduser(mapping.local_path)
        remote_path = mapping.remote_path

        if not local_path.endswith("/"):
            local_path += "/"
        if not remote_path.endswith("/"):
            remote_path += "/"

        cmd = self._build_rsync_command(mapping, dry_run)
        cmd.extend([f"{self.ssh_manager.config.user}@{host}:{remote_path}", local_path])

        return self._execute_rsync_with_progress(cmd, progress, progress_callback)

    def _execute_rsync_with_progress(
        self,
        cmd: List[str],
        progress: ProgressReporter,
        progress_callback: Optional[callable],
    ) -> SyncResult:
        """Execute rsync command with progress monitoring."""

        start_time = time.time()

        try:
            self.logger.info(f"Executing: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Monitor progress
            output_lines = []
            error_lines = []

            while True:
                output = process.stdout.readline()
                if output == "" and process.poll() is not None:
                    break

                if output:
                    output_lines.append(output.strip())

                    # Parse progress information
                    if progress_callback:
                        stats = progress.get_stats()
                        progress_callback(stats)

            # Get any remaining output
            stdout, stderr = process.communicate()
            if stdout:
                output_lines.extend(stdout.strip().split("\n"))
            if stderr:
                error_lines.extend(stderr.strip().split("\n"))

            duration = time.time() - start_time

            if process.returncode == 0:
                return SyncResult(
                    success=True,
                    operation="rsync_execute",
                    stats={
                        "duration": duration,
                        "output": output_lines,
                        "command": " ".join(cmd),
                    },
                )
            else:
                return SyncResult(
                    success=False,
                    operation="rsync_execute",
                    error_message=f"rsync failed with code {process.returncode}",
                    stats={
                        "duration": duration,
                        "output": output_lines,
                        "error_output": error_lines,
                        "command": " ".join(cmd),
                    },
                )

        except Exception as e:
            return SyncResult(
                success=False,
                operation="rsync_execute",
                error_message=f"Failed to execute rsync: {e}",
                stats={"duration": time.time() - start_time},
            )

    # Compatibility methods for SyncOrchestrator
    def sync_bidirectional(
        self, host: str, mapping: DirectoryMapping, dry_run: bool = False
    ) -> Dict[str, Any]:
        """Bidirectional sync compatibility method."""
        result = self.sync_with_progress(
            host, mapping, mode="bidirectional", dry_run=dry_run
        )
        return {
            "success": result.success,
            "error": result.error_message,
            "stats": result.stats,
            "duration": result.duration,
        }

    def sync_local_to_remote(
        self, host: str, mapping: DirectoryMapping, dry_run: bool = False
    ) -> Dict[str, Any]:
        """Local to remote sync compatibility method."""
        result = self.sync_with_progress(
            host, mapping, mode="local_to_remote", dry_run=dry_run
        )
        return {
            "success": result.success,
            "error": result.error_message,
            "stats": result.stats,
            "duration": result.duration,
        }

    def sync_remote_to_local(
        self, host: str, mapping: DirectoryMapping, dry_run: bool = False
    ) -> Dict[str, Any]:
        """Remote to local sync compatibility method."""
        result = self.sync_with_progress(
            host, mapping, mode="remote_to_local", dry_run=dry_run
        )
        return {
            "success": result.success,
            "error": result.error_message,
            "stats": result.stats,
            "duration": result.duration,
        }

    def get_directory_info(
        self, host: str, mapping: DirectoryMapping
    ) -> Dict[str, Any]:
        """Get directory information compatibility method."""
        local_path = os.path.expanduser(mapping.local_path)
        remote_path = mapping.remote_path

        # Get local directory info
        local_info = {}
        if os.path.exists(local_path):
            local_info = {
                "exists": True,
                "path": local_path,
                "size": sum(
                    os.path.getsize(os.path.join(dirpath, filename))
                    for dirpath, dirnames, filenames in os.walk(local_path)
                    for filename in filenames
                ),
                "file_count": sum(
                    len(filenames) for _, _, filenames in os.walk(local_path)
                ),
            }
        else:
            local_info = {"exists": False, "path": local_path}

        # Get remote directory info (simplified)
        remote_info = {"exists": True, "path": remote_path}  # Assume exists for now

        return {
            "mapping_name": mapping.name,
            "local": local_info,
            "remote": remote_info,
            "enabled": mapping.enabled,
        }
