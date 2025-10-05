#!/usr/bin/env python3
"""
Advanced bidirectional sync daemon for EC2 Dynamic Sync.

This module provides a daemon-like service that monitors both local and remote
directories for changes and automatically synchronizes them with intelligent
conflict resolution and change batching.
"""

import hashlib
import json
import logging
import os
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .exceptions import EC2SyncError, SyncError
from .models import ConflictResolution, DirectoryMapping, SyncConfig, SyncMode
from .sync_orchestrator import SyncOrchestrator


@dataclass
class ChangeEvent:
    """Represents a file system change event."""

    path: str
    event_type: str  # 'created', 'modified', 'deleted', 'moved'
    timestamp: float
    size: Optional[int] = None
    checksum: Optional[str] = None
    old_path: Optional[str] = None  # For move events


@dataclass
class SyncState:
    """Represents the current sync state."""

    last_sync_time: float
    local_changes: Dict[str, ChangeEvent]
    remote_changes: Dict[str, ChangeEvent]
    conflicts: List[Dict[str, Any]]
    sync_in_progress: bool = False


class ChangeDetector:
    """Detects and tracks file system changes."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.file_states: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)

    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get file information including size, mtime, and checksum."""
        try:
            stat = file_path.stat()

            # Calculate checksum for small files only (< 10MB)
            checksum = None
            if stat.st_size < 10 * 1024 * 1024:
                with open(file_path, "rb") as f:
                    checksum = hashlib.md5(f.read()).hexdigest()

            return {
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "checksum": checksum,
                "exists": True,
            }
        except (OSError, IOError):
            return {"exists": False}

    def scan_directory(self) -> Dict[str, Dict[str, Any]]:
        """Scan directory and return current file states."""
        current_states = {}

        if not self.base_path.exists():
            return current_states

        for file_path in self.base_path.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(self.base_path))
                current_states[rel_path] = self.get_file_info(file_path)

        return current_states

    def detect_changes(self) -> List[ChangeEvent]:
        """Detect changes since last scan."""
        current_states = self.scan_directory()
        changes = []

        # Find new and modified files
        for rel_path, current_info in current_states.items():
            if not current_info["exists"]:
                continue

            old_info = self.file_states.get(rel_path, {})

            if not old_info:
                # New file
                changes.append(
                    ChangeEvent(
                        path=rel_path,
                        event_type="created",
                        timestamp=time.time(),
                        size=current_info["size"],
                        checksum=current_info["checksum"],
                    )
                )
            elif current_info["mtime"] != old_info.get("mtime") or current_info[
                "checksum"
            ] != old_info.get("checksum"):
                # Modified file
                changes.append(
                    ChangeEvent(
                        path=rel_path,
                        event_type="modified",
                        timestamp=time.time(),
                        size=current_info["size"],
                        checksum=current_info["checksum"],
                    )
                )

        # Find deleted files
        for rel_path, old_info in self.file_states.items():
            if rel_path not in current_states:
                changes.append(
                    ChangeEvent(
                        path=rel_path, event_type="deleted", timestamp=time.time()
                    )
                )

        # Update stored states
        self.file_states = current_states

        return changes


class ConflictResolver:
    """Handles conflict resolution for bidirectional sync."""

    def __init__(self, strategy: ConflictResolution):
        self.strategy = strategy
        self.logger = logging.getLogger(__name__)

    def resolve_conflict(
        self, local_change: ChangeEvent, remote_change: ChangeEvent
    ) -> Tuple[str, Optional[ChangeEvent]]:
        """Resolve a conflict between local and remote changes.

        Returns:
            Tuple of (action, winning_change) where action is 'local_wins',
            'remote_wins', or 'manual_required'
        """
        if self.strategy == ConflictResolution.LOCAL:
            return "local_wins", local_change
        elif self.strategy == ConflictResolution.REMOTE:
            return "remote_wins", remote_change
        elif self.strategy == ConflictResolution.NEWER:
            if local_change.timestamp > remote_change.timestamp:
                return "local_wins", local_change
            else:
                return "remote_wins", remote_change
        else:  # MANUAL
            return "manual_required", None


class SyncQueue:
    """Manages queued sync operations with batching and prioritization."""

    def __init__(self, max_batch_size: int = 50, max_wait_time: float = 30.0):
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.queue: deque = deque()
        self.lock = threading.Lock()
        self.last_batch_time = time.time()

    def add_changes(self, changes: List[ChangeEvent]):
        """Add changes to the sync queue."""
        with self.lock:
            self.queue.extend(changes)

    def get_batch(self) -> List[ChangeEvent]:
        """Get a batch of changes ready for sync."""
        with self.lock:
            current_time = time.time()

            # Check if we should create a batch
            if len(self.queue) >= self.max_batch_size or (
                self.queue and current_time - self.last_batch_time >= self.max_wait_time
            ):

                batch_size = min(len(self.queue), self.max_batch_size)
                batch = [self.queue.popleft() for _ in range(batch_size)]
                self.last_batch_time = current_time
                return batch

            return []

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        with self.lock:
            return len(self.queue) == 0


class BidirectionalSyncDaemon:
    """Advanced bidirectional sync daemon."""

    def __init__(self, config: SyncConfig, poll_interval: float = 60.0):
        self.config = config
        self.poll_interval = poll_interval
        self.orchestrator = SyncOrchestrator(config)
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.local_detectors: Dict[str, ChangeDetector] = {}
        self.conflict_resolver = ConflictResolver(config.conflict_resolution)
        self.sync_queue = SyncQueue()

        # State management
        self.sync_state = SyncState(
            last_sync_time=time.time(),
            local_changes={},
            remote_changes={},
            conflicts=[],
        )

        # Control flags
        self.running = False
        self.threads: List[threading.Thread] = []

        # Initialize change detectors for each mapping
        for mapping in config.directory_mappings:
            if mapping.enabled:
                local_path = os.path.expanduser(mapping.local_path)
                self.local_detectors[mapping.name] = ChangeDetector(local_path)

    def start(self):
        """Start the sync daemon."""
        if self.running:
            return

        self.running = True
        self.logger.info("Starting bidirectional sync daemon")

        # Start monitoring threads
        local_thread = threading.Thread(target=self._local_monitor_loop, daemon=True)
        remote_thread = threading.Thread(target=self._remote_monitor_loop, daemon=True)
        sync_thread = threading.Thread(target=self._sync_loop, daemon=True)

        self.threads = [local_thread, remote_thread, sync_thread]

        for thread in self.threads:
            thread.start()

        self.logger.info("Sync daemon started successfully")

    def stop(self):
        """Stop the sync daemon."""
        if not self.running:
            return

        self.logger.info("Stopping sync daemon")
        self.running = False

        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=5.0)

        self.logger.info("Sync daemon stopped")

    def _local_monitor_loop(self):
        """Monitor local directories for changes."""
        while self.running:
            try:
                for mapping_name, detector in self.local_detectors.items():
                    changes = detector.detect_changes()
                    if changes:
                        self.logger.info(
                            f"Detected {len(changes)} local changes in {mapping_name}"
                        )
                        for change in changes:
                            self.sync_state.local_changes[change.path] = change
                        self.sync_queue.add_changes(changes)

                time.sleep(5)  # Check every 5 seconds

            except Exception as e:
                self.logger.error(f"Error in local monitor loop: {e}")
                time.sleep(10)

    def _remote_monitor_loop(self):
        """Monitor remote directories for changes (via SSH polling)."""
        while self.running:
            try:
                # This is a simplified version - in practice, you'd want to
                # implement more efficient remote change detection
                time.sleep(self.poll_interval)

            except Exception as e:
                self.logger.error(f"Error in remote monitor loop: {e}")
                time.sleep(30)

    def _sync_loop(self):
        """Main sync processing loop."""
        while self.running:
            try:
                batch = self.sync_queue.get_batch()
                if batch:
                    self._process_sync_batch(batch)

                time.sleep(1)

            except Exception as e:
                self.logger.error(f"Error in sync loop: {e}")
                time.sleep(5)

    def _process_sync_batch(self, changes: List[ChangeEvent]):
        """Process a batch of changes."""
        if self.sync_state.sync_in_progress:
            # Re-queue changes if sync is already in progress
            self.sync_queue.add_changes(changes)
            return

        try:
            self.sync_state.sync_in_progress = True
            self.logger.info(f"Processing sync batch with {len(changes)} changes")

            # Perform the actual sync
            results = self.orchestrator.sync_all_directories(
                mode=SyncMode.BIDIRECTIONAL, dry_run=False
            )

            if results.get("overall_success"):
                self.logger.info("Sync batch completed successfully")
                self.sync_state.last_sync_time = time.time()
            else:
                self.logger.error("Sync batch failed")
                # Re-queue changes for retry
                self.sync_queue.add_changes(changes)

        except Exception as e:
            self.logger.error(f"Error processing sync batch: {e}")
            # Re-queue changes for retry
            self.sync_queue.add_changes(changes)
        finally:
            self.sync_state.sync_in_progress = False

    def get_status(self) -> Dict[str, Any]:
        """Get current daemon status."""
        return {
            "running": self.running,
            "last_sync_time": self.sync_state.last_sync_time,
            "pending_changes": len(self.sync_queue.queue),
            "local_changes": len(self.sync_state.local_changes),
            "remote_changes": len(self.sync_state.remote_changes),
            "conflicts": len(self.sync_state.conflicts),
            "sync_in_progress": self.sync_state.sync_in_progress,
        }
