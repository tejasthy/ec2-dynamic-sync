"""
Main CLI entry point for EC2 Dynamic Sync.

This module provides the primary command-line interface for manual sync operations
with comprehensive error handling, progress reporting, and user-friendly output.
"""

import json
import logging
import sys
import threading
import time
from typing import Any, Dict, Optional

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text

from ..__version__ import __version__
from ..core import ConfigManager, SyncOrchestrator
from ..core.exceptions import ConfigurationError, EC2SyncError

console = Console()


class SyncProgressTracker:
    """Real-time progress tracker for sync operations."""

    def __init__(self):
        self.progress_data = {
            "current_phase": "Initializing",
            "current_file": "",
            "files_completed": 0,
            "total_files": 0,
            "bytes_transferred": 0,
            "total_bytes": 0,
            "transfer_rate": 0,
            "eta_seconds": 0,
            "percentage": 0,
            "start_time": time.time(),
        }
        self.lock = threading.Lock()
        self.live_display = None

    def update_progress(self, stats: Dict[str, Any]):
        """Update progress with new stats from rsync."""
        with self.lock:
            self.progress_data.update({
                "current_file": stats.get("current_file", ""),
                "files_completed": stats.get("files_transferred", 0),
                "bytes_transferred": stats.get("bytes_transferred", 0),
                "transfer_rate": stats.get("rate_bps", 0),
                "eta_seconds": stats.get("eta_seconds", 0),
                "percentage": stats.get("percentage", 0),
            })

            # Update sync phase if provided
            if stats.get("sync_phase"):
                self.progress_data["current_phase"] = stats["sync_phase"]

            # Update total bytes if we have it
            if stats.get("total_bytes", 0) > 0:
                self.progress_data["total_bytes"] = stats["total_bytes"]

    def set_phase(self, phase: str):
        """Set the current sync phase."""
        with self.lock:
            self.progress_data["current_phase"] = phase

    def create_progress_panel(self) -> Panel:
        """Create a Rich panel showing current progress."""
        with self.lock:
            data = self.progress_data.copy()

        # Format transfer rate
        rate_bps = data["transfer_rate"]
        if rate_bps > 1024 * 1024:
            rate_str = f"{rate_bps / (1024 * 1024):.1f} MB/s"
        elif rate_bps > 1024:
            rate_str = f"{rate_bps / 1024:.1f} KB/s"
        else:
            rate_str = f"{rate_bps:.0f} B/s"

        # Format bytes transferred
        bytes_transferred = data["bytes_transferred"]
        total_bytes = data["total_bytes"]
        if total_bytes > 0:
            # Use the larger of the two for display formatting to handle cases where
            # bytes_transferred might exceed total_bytes due to rsync quirks
            display_total = max(total_bytes, bytes_transferred)

            if display_total > 1024 * 1024:
                size_str = f"{bytes_transferred / (1024 * 1024):.1f} / {total_bytes / (1024 * 1024):.1f} MB"
            elif display_total > 1024:
                size_str = f"{bytes_transferred / 1024:.1f} / {total_bytes / 1024:.1f} KB"
            else:
                size_str = f"{bytes_transferred} / {total_bytes} bytes"
        else:
            if bytes_transferred > 1024 * 1024:
                size_str = f"{bytes_transferred / (1024 * 1024):.1f} MB"
            elif bytes_transferred > 1024:
                size_str = f"{bytes_transferred / 1024:.1f} KB"
            else:
                size_str = f"{bytes_transferred} bytes"

        # Format ETA
        eta_seconds = data["eta_seconds"]
        if eta_seconds > 0:
            if eta_seconds > 3600:
                eta_str = f"{eta_seconds // 3600:.0f}h {(eta_seconds % 3600) // 60:.0f}m"
            elif eta_seconds > 60:
                eta_str = f"{eta_seconds // 60:.0f}m {eta_seconds % 60:.0f}s"
            else:
                eta_str = f"{eta_seconds:.0f}s"
        else:
            eta_str = "Calculating..."

        # Format elapsed time
        elapsed = time.time() - data["start_time"]
        if elapsed > 3600:
            elapsed_str = f"{elapsed // 3600:.0f}h {(elapsed % 3600) // 60:.0f}m"
        elif elapsed > 60:
            elapsed_str = f"{elapsed // 60:.0f}m {elapsed % 60:.0f}s"
        else:
            elapsed_str = f"{elapsed:.0f}s"

        # Create progress content
        content = []
        content.append(f"🔄 Phase: [bold]{data['current_phase']}[/bold]")

        if data["current_file"]:
            content.append(f"📄 Current: {data['current_file']}")

        if data["percentage"] > 0:
            # Cap percentage at 100% for display (rsync can sometimes report > 100%)
            display_percentage = min(100.0, data["percentage"])
            content.append(f"📊 Progress: {display_percentage:.1f}%")

        content.append(f"📦 Transferred: {size_str}")

        if rate_bps > 0:
            content.append(f"⚡ Speed: {rate_str}")

        content.append(f"⏱️  Elapsed: {elapsed_str}")

        if eta_seconds > 0:
            content.append(f"⏳ ETA: {eta_str}")

        return Panel(
            "\n".join(content),
            title="🔄 Sync Progress",
            border_style="blue",
        )


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )


def print_status(status: dict):
    """Print sync status in a rich formatted table."""
    console.print("\n[bold blue]🔗 EC2 Sync Status[/bold blue]")

    # Instance information
    info_table = Table(show_header=False, box=None)
    info_table.add_column("Field", style="cyan")
    info_table.add_column("Value", style="white")

    info_table.add_row("Instance ID", status.get("instance_id", "Unknown"))
    info_table.add_row("Host IP", status.get("host", "Unknown"))
    info_table.add_row(
        "SSH Connected", "✅ Yes" if status.get("ssh_connected") else "❌ No"
    )
    info_table.add_row("Instance State", status.get("instance_state", "Unknown"))

    console.print(info_table)

    # Directory status
    console.print("\n[bold blue]📁 Directory Status[/bold blue]")

    for mapping_name, info in status.get("directory_mappings", {}).items():
        if "error" in info:
            console.print(f"[red]❌ {mapping_name}: Error - {info['error']}[/red]")
            continue

        local = info.get("local", {})
        remote = info.get("remote", {})

        dir_table = Table(title=f"📂 {mapping_name}", show_header=True)
        dir_table.add_column("Location", style="cyan")
        dir_table.add_column("Path", style="white")
        dir_table.add_column("Exists", style="green")
        dir_table.add_column("Files", style="yellow")
        dir_table.add_column("Size", style="magenta")

        dir_table.add_row(
            "Local",
            local.get("path", "Unknown"),
            "✅" if local.get("exists") else "❌",
            str(local.get("file_count", "Unknown")),
            local.get("size", "Unknown"),
        )

        dir_table.add_row(
            "Remote",
            remote.get("path", "Unknown"),
            "✅" if remote.get("exists") else "❌",
            str(remote.get("file_count", "Unknown")),
            remote.get("size", "Unknown"),
        )

        console.print(dir_table)
        console.print()


def print_sync_results(results: dict):
    """Print sync results in a rich formatted display."""
    summary = results.get("summary", {})

    if results.get("overall_success"):
        console.print("\n[bold green]✅ Sync Completed Successfully![/bold green]")
    else:
        console.print("\n[bold red]❌ Sync Completed with Errors[/bold red]")

    # Summary information
    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row(
        "Directories",
        f"{summary.get('successful_dirs', 0)}/{summary.get('total_dirs', 0)} successful",
    )
    summary_table.add_row("Duration", f"{summary.get('total_duration', 0):.1f} seconds")

    console.print(summary_table)

    # Detailed results
    console.print("\n[bold blue]📁 Directory Results[/bold blue]")

    for dir_name, result in results.get("directories", {}).items():
        if result.get("success") or result.get("overall_success"):
            console.print(f"[green]✅ {dir_name}: Success[/green]")

            # Show transfer stats if available
            if "local_to_remote" in result and result["local_to_remote"]:
                l2r = result["local_to_remote"]
                if (
                    l2r.get("success")
                    and l2r.get("stats", {}).get("files_transferred", 0) > 0
                ):
                    stats = l2r["stats"]
                    console.print(
                        f"      [blue]→ Local to Remote: {stats.get('files_transferred', 0)} files[/blue]"
                    )

            if "remote_to_local" in result and result["remote_to_local"]:
                r2l = result["remote_to_local"]
                if (
                    r2l.get("success")
                    and r2l.get("stats", {}).get("files_transferred", 0) > 0
                ):
                    stats = r2l["stats"]
                    console.print(
                        f"      [blue]← Remote to Local: {stats.get('files_transferred', 0)} files[/blue]"
                    )
        else:
            console.print(f"[red]❌ {dir_name}: Failed[/red]")
            error = result.get("error", "Unknown error")
            console.print(f"      [red]Error: {error}[/red]")


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version and exit")
@click.option("--config", type=str, help="Path to configuration file")
@click.option("--profile", type=str, help="Configuration profile to use")
@click.option("--verbose", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, version, config, profile, verbose):
    """EC2 Dynamic Sync - Professional-grade EC2 file synchronization.

    Synchronize files between local machines and EC2 instances with dynamic IP
    handling, bidirectional sync, and real-time monitoring capabilities.
    """
    if version:
        console.print(f"EC2 Dynamic Sync version {__version__}")
        sys.exit(0)

    # Setup logging
    setup_logging(verbose)

    # Store context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["profile"] = profile
    ctx.obj["verbose"] = verbose

    # If no subcommand, show help
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
@click.pass_context
def status(ctx, output_json):
    """Show current sync status and directory information."""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Getting sync status...", total=None)

            # Initialize orchestrator
            orchestrator = SyncOrchestrator.from_config_file(
                config_path=ctx.obj["config_path"], profile=ctx.obj["profile"]
            )

            # Get status
            status_info = orchestrator.get_sync_status()

            progress.remove_task(task)

        if output_json:
            console.print(json.dumps(status_info, indent=2, default=str))
        else:
            print_status(status_info)

    except EC2SyncError as e:
        console.print(f"[red]❌ Error: {e.message}[/red]")
        if ctx.obj["verbose"]:
            console.print(f"[red]Details: {e.details}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Unexpected error: {e}[/red]")
        if ctx.obj["verbose"]:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be synced without making changes"
)
@click.pass_context
def sync(ctx, output_json, dry_run):
    """Perform bidirectional synchronization."""
    try:
        # Initialize orchestrator
        orchestrator = SyncOrchestrator.from_config_file(
            config_path=ctx.obj["config_path"], profile=ctx.obj["profile"]
        )

        if dry_run:
            # For dry run, use simple spinner
            action = "Dry run - showing what would be synced"
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(action + "...", total=None)
                results = orchestrator.sync_all_directories(
                    mode="bidirectional", dry_run=dry_run
                )
                progress.remove_task(task)
        else:
            # For actual sync, use real-time progress tracking
            progress_tracker = SyncProgressTracker()

            def progress_callback(stats: Dict[str, Any]):
                """Handle progress updates from rsync."""
                progress_tracker.update_progress(stats)

            # Start live display
            with Live(
                progress_tracker.create_progress_panel(),
                console=console,
                refresh_per_second=4,
                transient=False
            ) as live:
                progress_tracker.live_display = live

                # Update display periodically
                def update_display():
                    while hasattr(progress_tracker, 'live_display') and progress_tracker.live_display:
                        try:
                            live.update(progress_tracker.create_progress_panel())
                            time.sleep(0.25)
                        except:
                            break

                # Start display update thread
                display_thread = threading.Thread(target=update_display, daemon=True)
                display_thread.start()

                try:
                    # Perform sync with progress callback
                    progress_tracker.set_phase("Preparing sync")
                    results = orchestrator.sync_all_directories(
                        mode="bidirectional", dry_run=dry_run, progress_callback=progress_callback
                    )
                    progress_tracker.set_phase("Completed")
                finally:
                    # Stop live display
                    progress_tracker.live_display = None

        if output_json:
            console.print(json.dumps(results, indent=2, default=str))
        else:
            print_sync_results(results)

        # Exit with appropriate code
        if results.get("overall_success"):
            sys.exit(0)
        else:
            sys.exit(1)

    except EC2SyncError as e:
        console.print(f"[red]❌ Error: {e.message}[/red]")
        if ctx.obj["verbose"]:
            console.print(f"[red]Details: {e.details}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Unexpected error: {e}[/red]")
        if ctx.obj["verbose"]:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be synced without making changes"
)
@click.pass_context
def push(ctx, output_json, dry_run):
    """Push local changes to remote (local to remote sync)."""
    try:
        action = (
            "Dry run - showing what would be pushed"
            if dry_run
            else "Pushing local changes to remote"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(action + "...", total=None)

            orchestrator = SyncOrchestrator.from_config_file(
                config_path=ctx.obj["config_path"], profile=ctx.obj["profile"]
            )

            results = orchestrator.sync_all_directories(
                mode="local_to_remote", dry_run=dry_run
            )

            progress.remove_task(task)

        if output_json:
            console.print(json.dumps(results, indent=2, default=str))
        else:
            print_sync_results(results)

        if results.get("overall_success"):
            sys.exit(0)
        else:
            sys.exit(1)

    except EC2SyncError as e:
        console.print(f"[red]❌ Error: {e.message}[/red]")
        if ctx.obj["verbose"]:
            console.print(f"[red]Details: {e.details}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Unexpected error: {e}[/red]")
        if ctx.obj["verbose"]:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be synced without making changes"
)
@click.pass_context
def pull(ctx, output_json, dry_run):
    """Pull remote changes to local (remote to local sync)."""
    try:
        action = (
            "Dry run - showing what would be pulled"
            if dry_run
            else "Pulling remote changes to local"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(action + "...", total=None)

            orchestrator = SyncOrchestrator.from_config_file(
                config_path=ctx.obj["config_path"], profile=ctx.obj["profile"]
            )

            results = orchestrator.sync_all_directories(
                mode="remote_to_local", dry_run=dry_run
            )

            progress.remove_task(task)

        if output_json:
            console.print(json.dumps(results, indent=2, default=str))
        else:
            print_sync_results(results)

        if results.get("overall_success"):
            sys.exit(0)
        else:
            sys.exit(1)

    except EC2SyncError as e:
        console.print(f"[red]❌ Error: {e.message}[/red]")
        if ctx.obj["verbose"]:
            console.print(f"[red]Details: {e.details}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Unexpected error: {e}[/red]")
        if ctx.obj["verbose"]:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(1)


# Import and register the watch command
from .watch import watch
cli.add_command(watch)


def main():
    """Main entry point for the CLI."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Operation interrupted by user[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
