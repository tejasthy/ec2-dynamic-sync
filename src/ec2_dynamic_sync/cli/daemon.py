#!/usr/bin/env python3
"""Daemon CLI for EC2 Dynamic Sync."""

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from ..core import BidirectionalSyncDaemon, ConfigManager
from ..core.exceptions import EC2SyncError

console = Console()


class DaemonController:
    """Controls the sync daemon lifecycle."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_manager = ConfigManager(config_path)
        self.daemon: Optional[BidirectionalSyncDaemon] = None
        self.pid_file = Path.home() / ".ec2-sync" / "daemon.pid"
        self.status_file = Path.home() / ".ec2-sync" / "daemon.status"

        # Ensure directory exists
        self.pid_file.parent.mkdir(exist_ok=True)

    def start_daemon(self, poll_interval: float = 60.0) -> bool:
        """Start the sync daemon."""
        if self.is_running():
            console.print("[yellow]⚠️  Daemon is already running[/yellow]")
            return False

        try:
            config = self.config_manager.get_config()
            self.daemon = BidirectionalSyncDaemon(config, poll_interval)

            # Start daemon
            self.daemon.start()

            # Write PID file
            with open(self.pid_file, "w") as f:
                f.write(str(os.getpid()))

            console.print("[green]✅ Daemon started successfully[/green]")
            return True

        except Exception as e:
            console.print(f"[red]❌ Failed to start daemon: {e}[/red]")
            return False

    def stop_daemon(self) -> bool:
        """Stop the sync daemon."""
        if not self.is_running():
            console.print("[yellow]⚠️  Daemon is not running[/yellow]")
            return False

        try:
            if self.daemon:
                self.daemon.stop()

            # Remove PID file
            if self.pid_file.exists():
                self.pid_file.unlink()

            # Remove status file
            if self.status_file.exists():
                self.status_file.unlink()

            console.print("[green]✅ Daemon stopped successfully[/green]")
            return True

        except Exception as e:
            console.print(f"[red]❌ Failed to stop daemon: {e}[/red]")
            return False

    def is_running(self) -> bool:
        """Check if daemon is running."""
        if not self.pid_file.exists():
            return False

        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())

            # Check if process exists
            os.kill(pid, 0)
            return True

        except (OSError, ValueError):
            # Process doesn't exist, clean up stale PID file
            if self.pid_file.exists():
                self.pid_file.unlink()
            return False

    def get_status(self) -> dict:
        """Get daemon status."""
        if not self.is_running():
            return {"running": False}

        if self.daemon:
            return self.daemon.get_status()

        # Try to read status from file
        if self.status_file.exists():
            try:
                with open(self.status_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        return {"running": True, "status": "unknown"}


@click.group()
def daemon():
    """Daemon management for EC2 Dynamic Sync."""
    pass


@daemon.command()
@click.option("--config", type=str, help="Configuration file path")
@click.option(
    "--poll-interval",
    type=float,
    default=60.0,
    help="Remote polling interval in seconds",
)
@click.option("--foreground", is_flag=True, help="Run in foreground (don't daemonize)")
def start(config: Optional[str], poll_interval: float, foreground: bool):
    """Start the sync daemon."""
    try:
        controller = DaemonController(config)

        if foreground:
            # Run in foreground with status display
            console.print("[bold blue]🚀 Starting EC2 Dynamic Sync Daemon[/bold blue]")

            if not controller.start_daemon(poll_interval):
                sys.exit(1)

            # Setup signal handlers
            def signal_handler(signum, frame):
                console.print("\n[yellow]📡 Received shutdown signal[/yellow]")
                controller.stop_daemon()
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            # Status display loop
            layout = Layout()
            layout.split_column(
                Layout(name="header", size=3),
                Layout(name="main"),
                Layout(name="footer", size=3),
            )

            try:
                with Live(layout, refresh_per_second=1, screen=True):
                    while True:
                        status = controller.get_status()

                        # Header
                        uptime = time.time() - status.get("last_sync_time", time.time())
                        header_text = (
                            f"🔄 EC2 Dynamic Sync Daemon | Uptime: {uptime:.0f}s"
                        )
                        layout["header"].update(Panel(header_text, style="blue"))

                        # Main status
                        status_table = Table(title="Daemon Status")
                        status_table.add_column("Metric", style="cyan")
                        status_table.add_column("Value", style="white")

                        status_table.add_row(
                            "Running", "✅ Yes" if status["running"] else "❌ No"
                        )
                        status_table.add_row(
                            "Pending Changes", str(status.get("pending_changes", 0))
                        )
                        status_table.add_row(
                            "Local Changes", str(status.get("local_changes", 0))
                        )
                        status_table.add_row(
                            "Remote Changes", str(status.get("remote_changes", 0))
                        )
                        status_table.add_row(
                            "Conflicts", str(status.get("conflicts", 0))
                        )
                        status_table.add_row(
                            "Sync In Progress",
                            "Yes" if status.get("sync_in_progress") else "No",
                        )

                        layout["main"].update(status_table)

                        # Footer
                        layout["footer"].update(
                            Panel("Press Ctrl+C to stop", style="dim")
                        )

                        time.sleep(1)

            except KeyboardInterrupt:
                controller.stop_daemon()

        else:
            # Background daemon mode
            if controller.start_daemon(poll_interval):
                console.print("Daemon started in background")
            else:
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]❌ Failed to start daemon: {e}[/red]")
        sys.exit(1)


@daemon.command()
@click.option("--config", type=str, help="Configuration file path")
def stop(config: Optional[str]):
    """Stop the sync daemon."""
    try:
        controller = DaemonController(config)

        if controller.stop_daemon():
            console.print("Daemon stopped successfully")
        else:
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]❌ Failed to stop daemon: {e}[/red]")
        sys.exit(1)


@daemon.command()
@click.option("--config", type=str, help="Configuration file path")
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
def status(config: Optional[str], output_json: bool):
    """Show daemon status."""
    try:
        controller = DaemonController(config)
        status_info = controller.get_status()

        if output_json:
            console.print(json.dumps(status_info, indent=2))
        else:
            console.print("\n[bold blue]🔄 EC2 Dynamic Sync Daemon Status[/bold blue]")

            if not status_info["running"]:
                console.print("[red]❌ Daemon is not running[/red]")
                console.print("Use 'ec2-sync daemon start' to start the daemon")
                return

            # Create status table
            status_table = Table()
            status_table.add_column("Metric", style="cyan")
            status_table.add_column("Value", style="white")

            status_table.add_row("Status", "✅ Running")

            if "last_sync_time" in status_info:
                last_sync = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(status_info["last_sync_time"])
                )
                status_table.add_row("Last Sync", last_sync)

            status_table.add_row(
                "Pending Changes", str(status_info.get("pending_changes", 0))
            )
            status_table.add_row(
                "Local Changes", str(status_info.get("local_changes", 0))
            )
            status_table.add_row(
                "Remote Changes", str(status_info.get("remote_changes", 0))
            )
            status_table.add_row("Conflicts", str(status_info.get("conflicts", 0)))

            sync_status = "Yes" if status_info.get("sync_in_progress") else "No"
            status_table.add_row("Sync In Progress", sync_status)

            console.print(status_table)

    except Exception as e:
        console.print(f"[red]❌ Failed to get status: {e}[/red]")
        sys.exit(1)


@daemon.command()
@click.option("--config", type=str, help="Configuration file path")
def restart(config: Optional[str]):
    """Restart the sync daemon."""
    try:
        controller = DaemonController(config)

        console.print("Stopping daemon...")
        controller.stop_daemon()

        time.sleep(2)  # Give it time to stop

        console.print("Starting daemon...")
        if controller.start_daemon():
            console.print("[green]✅ Daemon restarted successfully[/green]")
        else:
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]❌ Failed to restart daemon: {e}[/red]")
        sys.exit(1)


def main():
    """Main entry point for the daemon CLI."""
    try:
        daemon()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Operation interrupted by user[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
