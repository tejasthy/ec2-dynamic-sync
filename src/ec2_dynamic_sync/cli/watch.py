#!/usr/bin/env python3
"""Watch CLI for EC2 Dynamic Sync."""

import os
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional, Set

import click
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..core import ConfigManager, SyncOrchestrator
from ..core.exceptions import EC2SyncError
from ..core.models import SyncMode

console = Console()


class SyncEventHandler(FileSystemEventHandler):
    """File system event handler for automatic synchronization."""

    def __init__(
        self,
        orchestrator: SyncOrchestrator,
        delay: float = 5.0,
        min_interval: float = 30.0,
        batch_size: int = 10,
    ):
        """Initialize the event handler.

        Args:
            orchestrator: Sync orchestrator instance
            delay: Seconds to wait after detecting changes before syncing
            min_interval: Minimum seconds between sync operations
            batch_size: Maximum number of changes to batch together
        """
        super().__init__()
        self.orchestrator = orchestrator
        self.delay = delay
        self.min_interval = min_interval
        self.batch_size = batch_size

        # Event tracking
        self.pending_changes: Dict[str, Set[str]] = defaultdict(set)
        self.last_sync_time = 0
        self.sync_timer: Optional[threading.Timer] = None
        self.sync_lock = threading.Lock()

        # Statistics
        self.stats = {
            "events_detected": 0,
            "syncs_triggered": 0,
            "last_sync": None,
            "errors": 0,
        }

        # Ignore patterns
        self.ignore_patterns = {
            # Temporary files
            "*.tmp",
            "*.temp",
            "*~",
            "*.swp",
            "*.swo",
            # System files
            ".DS_Store",
            "Thumbs.db",
            "desktop.ini",
            # Version control
            ".git/*",
            ".svn/*",
            ".hg/*",
            # IDE files
            ".vscode/*",
            ".idea/*",
            "*.pyc",
            "__pycache__/*",
            # Build artifacts
            "node_modules/*",
            "dist/*",
            "build/*",
            "*.egg-info/*",
        }

    def should_ignore(self, path: str) -> bool:
        """Check if a file path should be ignored."""
        path_obj = Path(path)

        # Check if any part of the path matches ignore patterns
        for pattern in self.ignore_patterns:
            if path_obj.match(pattern) or any(
                part.match(pattern.replace("/*", "")) for part in path_obj.parents
            ):
                return True

        # Ignore hidden files and directories (starting with .)
        if any(part.startswith(".") for part in path_obj.parts):
            return True

        return False

    def on_any_event(self, event: FileSystemEvent):
        """Handle any file system event."""
        if event.is_directory or self.should_ignore(event.src_path):
            return

        self.stats["events_detected"] += 1

        # Find which directory mapping this event belongs to
        for mapping in self.orchestrator.config.directory_mappings:
            if not mapping.enabled:
                continue

            local_path = os.path.expanduser(mapping.local_path)
            if event.src_path.startswith(local_path):
                self.pending_changes[mapping.name].add(event.src_path)
                break

        # Schedule sync if we have enough changes or after delay
        self._schedule_sync()

    def _schedule_sync(self):
        """Schedule a sync operation."""
        with self.sync_lock:
            # Cancel existing timer
            if self.sync_timer:
                self.sync_timer.cancel()

            # Check if we should sync immediately (batch size reached)
            total_changes = sum(
                len(changes) for changes in self.pending_changes.values()
            )

            if total_changes >= self.batch_size:
                # Sync immediately
                self.sync_timer = threading.Timer(0.1, self._perform_sync)
            else:
                # Wait for delay period
                self.sync_timer = threading.Timer(self.delay, self._perform_sync)

            self.sync_timer.start()

    def _perform_sync(self):
        """Perform the actual sync operation."""
        with self.sync_lock:
            # Check minimum interval
            current_time = time.time()
            if current_time - self.last_sync_time < self.min_interval:
                # Reschedule for later
                wait_time = self.min_interval - (current_time - self.last_sync_time)
                self.sync_timer = threading.Timer(wait_time, self._perform_sync)
                self.sync_timer.start()
                return

            if not self.pending_changes:
                return

            try:
                # Perform sync
                console.print(
                    f"\n[cyan]🔄 Syncing {sum(len(changes) for changes in self.pending_changes.values())} changes...[/cyan]"
                )

                results = self.orchestrator.sync_all_directories(
                    mode=SyncMode.BIDIRECTIONAL, dry_run=False
                )

                if results.get("overall_success"):
                    console.print("[green]✅ Sync completed successfully[/green]")
                    self.stats["syncs_triggered"] += 1
                else:
                    console.print("[red]❌ Sync failed[/red]")
                    self.stats["errors"] += 1

                self.stats["last_sync"] = time.strftime("%H:%M:%S")
                self.last_sync_time = current_time

                # Clear pending changes
                self.pending_changes.clear()

            except Exception as e:
                console.print(f"[red]❌ Sync error: {e}[/red]")
                self.stats["errors"] += 1
                # Don't clear pending changes on error - they'll be retried


class WatchStatus:
    """Status display for watch mode."""

    def __init__(self, orchestrator: SyncOrchestrator, handler: SyncEventHandler):
        self.orchestrator = orchestrator
        self.handler = handler
        self.start_time = time.time()

    def create_layout(self) -> Layout:
        """Create the status layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(Layout(name="left"), Layout(name="right"))

        return layout

    def update_display(self, layout: Layout):
        """Update the status display."""
        # Header
        uptime = time.time() - self.start_time
        uptime_str = f"{int(uptime // 3600):02d}:{int((uptime % 3600) // 60):02d}:{int(uptime % 60):02d}"

        header_text = Text()
        header_text.append("🔍 EC2 Dynamic Sync - Watch Mode", style="bold blue")
        header_text.append(f" | Uptime: {uptime_str}", style="cyan")

        layout["header"].update(Panel(header_text, border_style="blue"))

        # Left panel - Configuration
        config_table = Table(title="Configuration", show_header=False, box=None)
        config_table.add_column("Property", style="cyan")
        config_table.add_column("Value", style="white")

        config_table.add_row("Project", self.orchestrator.config.project_name)
        config_table.add_row("Instance", self.orchestrator.instance_id or "Unknown")
        config_table.add_row("Host", self.orchestrator.current_host or "Not connected")
        config_table.add_row(
            "Directories", str(len(self.orchestrator.config.directory_mappings))
        )
        config_table.add_row("Delay", f"{self.handler.delay}s")
        config_table.add_row("Min Interval", f"{self.handler.min_interval}s")

        layout["left"].update(
            Panel(config_table, title="Configuration", border_style="green")
        )

        # Right panel - Statistics
        stats_table = Table(title="Statistics", show_header=False, box=None)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", style="white")

        stats = self.handler.stats
        stats_table.add_row("Events Detected", str(stats["events_detected"]))
        stats_table.add_row("Syncs Triggered", str(stats["syncs_triggered"]))
        stats_table.add_row("Errors", str(stats["errors"]))
        stats_table.add_row("Last Sync", stats["last_sync"] or "Never")

        # Pending changes
        total_pending = sum(
            len(changes) for changes in self.handler.pending_changes.values()
        )
        stats_table.add_row("Pending Changes", str(total_pending))

        layout["right"].update(
            Panel(stats_table, title="Statistics", border_style="yellow")
        )

        # Footer
        footer_text = Text()
        footer_text.append("Press Ctrl+C to stop watching", style="dim")

        layout["footer"].update(Panel(footer_text, border_style="dim"))


@click.command()
@click.option("--config", type=str, help="Configuration file path")
@click.option(
    "--delay",
    type=float,
    default=5.0,
    help="Seconds to wait after detecting changes before syncing",
)
@click.option(
    "--min-interval",
    type=float,
    default=30.0,
    help="Minimum seconds between sync operations",
)
@click.option(
    "--batch-size",
    type=int,
    default=10,
    help="Maximum number of changes to batch together",
)
@click.option(
    "--mode",
    type=click.Choice(["bidirectional", "push", "pull"]),
    default="bidirectional",
    help="Sync mode",
)
@click.option("--no-ui", is_flag=True, help="Disable interactive UI")
def watch(
    config: Optional[str],
    delay: float,
    min_interval: float,
    batch_size: int,
    mode: str,
    no_ui: bool,
):
    """Real-time file monitoring and automatic synchronization."""
    try:
        console.print("[bold blue]🔍 Starting EC2 Dynamic Sync Watch Mode[/bold blue]")

        # Load configuration and initialize orchestrator
        console.print("Loading configuration...")
        orchestrator = SyncOrchestrator.from_config_file(config)

        # Test connectivity first
        console.print("Testing connectivity...")
        connectivity_results = orchestrator.test_connectivity()
        if not connectivity_results["overall_success"]:
            console.print("[red]❌ Connectivity test failed[/red]")
            if "error" in connectivity_results:
                console.print(f"Error: {connectivity_results['error']}")
            sys.exit(1)

        console.print("[green]✅ Connectivity test passed[/green]")

        # Convert mode string to SyncMode enum
        sync_mode = {
            "bidirectional": SyncMode.BIDIRECTIONAL,
            "push": SyncMode.LOCAL_TO_REMOTE,
            "pull": SyncMode.REMOTE_TO_LOCAL,
        }[mode]

        # Create event handler
        handler = SyncEventHandler(
            orchestrator=orchestrator,
            delay=delay,
            min_interval=min_interval,
            batch_size=batch_size,
        )

        # Set up file system observer
        observer = Observer()

        # Watch all configured directories
        watched_paths = []
        for mapping in orchestrator.config.directory_mappings:
            if not mapping.enabled:
                continue

            local_path = os.path.expanduser(mapping.local_path)
            if os.path.exists(local_path):
                observer.schedule(handler, local_path, recursive=True)
                watched_paths.append(local_path)
                console.print(f"[green]👁️  Watching: {local_path}[/green]")
            else:
                console.print(f"[yellow]⚠️  Directory not found: {local_path}[/yellow]")

        if not watched_paths:
            console.print("[red]❌ No directories to watch[/red]")
            sys.exit(1)

        # Start observer
        observer.start()
        console.print(f"\n[green]🚀 Watch mode started![/green]")
        console.print(f"Monitoring {len(watched_paths)} directories")
        console.print(
            f"Sync delay: {delay}s | Min interval: {min_interval}s | Batch size: {batch_size}"
        )
        console.print("Press Ctrl+C to stop...\n")

        if no_ui:
            # Simple mode without live UI
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                raise  # Re-raise to be caught by outer handler
        else:
            # Interactive UI mode
            status = WatchStatus(orchestrator, handler)
            layout = status.create_layout()

            try:
                with Live(layout, refresh_per_second=1, screen=True):
                    while True:
                        status.update_display(layout)
                        time.sleep(1)
            except KeyboardInterrupt:
                raise  # Re-raise to be caught by outer handler

        # Cleanup
        console.print("\n[yellow]🛑 Stopping watch mode...[/yellow]")
        observer.stop()
        observer.join()

        # Cancel any pending sync
        if handler.sync_timer:
            handler.sync_timer.cancel()

        # Show final statistics
        stats = handler.stats
        console.print("\n[bold]📊 Final Statistics[/bold]")
        console.print(f"Events detected: {stats['events_detected']}")
        console.print(f"Syncs triggered: {stats['syncs_triggered']}")
        console.print(f"Errors: {stats['errors']}")

        console.print("\n[green]✅ Watch mode stopped[/green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Watch mode interrupted by user[/yellow]")
        sys.exit(130)
    except EC2SyncError as e:
        console.print(f"\n[red]❌ Sync error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]❌ Unexpected error: {e}[/red]")
        sys.exit(1)


def main():
    """Main entry point for the watch CLI."""
    try:
        watch()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Watch mode interrupted by user[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
