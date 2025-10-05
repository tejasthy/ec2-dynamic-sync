#!/usr/bin/env python3
"""Doctor CLI for EC2 Dynamic Sync."""

import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import psutil
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from ..__version__ import __version__
from ..core import ConfigManager, SyncOrchestrator
from ..core.exceptions import EC2SyncError

console = Console()


def get_system_info() -> Dict[str, Any]:
    """Get comprehensive system information."""
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "architecture": platform.architecture()[0],
        "processor": platform.processor() or "Unknown",
        "memory_total": psutil.virtual_memory().total,
        "memory_available": psutil.virtual_memory().available,
        "disk_usage": psutil.disk_usage("/"),
        "cpu_count": psutil.cpu_count(),
        "boot_time": psutil.boot_time(),
    }


def check_python_dependencies() -> Dict[str, Dict[str, Any]]:
    """Check Python package dependencies."""
    required_packages = {
        "boto3": {"min_version": "1.26.0", "purpose": "AWS SDK"},
        "click": {"min_version": "8.0.0", "purpose": "CLI framework"},
        "rich": {"min_version": "12.0.0", "purpose": "Terminal formatting"},
        "pydantic": {"min_version": "2.0.0", "purpose": "Data validation"},
        "PyYAML": {"min_version": "6.0", "purpose": "YAML parsing"},
        "watchdog": {"min_version": "3.0.0", "purpose": "File monitoring"},
        "psutil": {"min_version": "5.9.0", "purpose": "System monitoring"},
    }

    results = {}

    for package, info in required_packages.items():
        try:
            if package == "PyYAML":
                import yaml

                module = yaml
                package_name = "yaml"
            else:
                module = __import__(package.lower())
                package_name = package.lower()

            version = getattr(module, "__version__", "Unknown")

            results[package] = {
                "installed": True,
                "version": version,
                "min_version": info["min_version"],
                "purpose": info["purpose"],
                "status": "ok",  # We'll do version checking later if needed
            }
        except ImportError:
            results[package] = {
                "installed": False,
                "version": None,
                "min_version": info["min_version"],
                "purpose": info["purpose"],
                "status": "missing",
            }

    return results


def check_system_commands() -> Dict[str, Dict[str, Any]]:
    """Check availability of required system commands."""
    commands = {
        "aws": {"required": False, "purpose": "AWS CLI for instance management"},
        "ssh": {"required": True, "purpose": "SSH client for remote connections"},
        "rsync": {"required": True, "purpose": "File synchronization"},
        "crontab": {"required": False, "purpose": "Scheduled task management"},
        "git": {"required": False, "purpose": "Version control (optional)"},
    }

    results = {}

    for cmd, info in commands.items():
        try:
            if cmd == "ssh":
                # SSH might return version info to stderr
                result = subprocess.run(
                    [cmd, "-V"], capture_output=True, text=True, timeout=5
                )
                available = result.returncode == 0 or "OpenSSH" in result.stderr
                version_info = (
                    result.stderr.split("\n")[0]
                    if result.stderr
                    else result.stdout.split("\n")[0]
                )
            elif cmd == "aws":
                result = subprocess.run(
                    [cmd, "--version"], capture_output=True, text=True, timeout=5
                )
                available = result.returncode == 0
                version_info = result.stdout.strip() if result.stdout else "Unknown"
            else:
                result = subprocess.run(
                    [cmd, "--version"], capture_output=True, text=True, timeout=5
                )
                available = result.returncode == 0
                version_info = (
                    result.stdout.split("\n")[0] if result.stdout else "Unknown"
                )

            results[cmd] = {
                "available": available,
                "version": version_info if available else None,
                "required": info["required"],
                "purpose": info["purpose"],
                "status": (
                    "ok"
                    if available
                    else ("critical" if info["required"] else "warning")
                ),
            }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            results[cmd] = {
                "available": False,
                "version": None,
                "required": info["required"],
                "purpose": info["purpose"],
                "status": "critical" if info["required"] else "warning",
            }

    return results


def check_network_connectivity() -> Dict[str, Any]:
    """Check network connectivity to AWS and other services."""
    tests = {
        "aws_api": {"host": "ec2.amazonaws.com", "port": 443},
        "github": {"host": "github.com", "port": 443},
        "pypi": {"host": "pypi.org", "port": 443},
    }

    results = {}

    for test_name, config in tests.items():
        try:
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((config["host"], config["port"]))
            sock.close()

            results[test_name] = {
                "reachable": result == 0,
                "host": config["host"],
                "port": config["port"],
                "status": "ok" if result == 0 else "warning",
            }
        except Exception as e:
            results[test_name] = {
                "reachable": False,
                "host": config["host"],
                "port": config["port"],
                "error": str(e),
                "status": "warning",
            }

    return results


def check_configuration() -> Dict[str, Any]:
    """Check EC2 Dynamic Sync configuration."""
    try:
        config_manager = ConfigManager()

        if not config_manager.config_path:
            return {
                "config_found": False,
                "status": "warning",
                "message": "No configuration file found",
            }

        config = config_manager.get_config()

        # Check configuration completeness
        issues = []

        if not config.aws.instance_id and not config.aws.instance_name:
            issues.append("No AWS instance specified")

        if not os.path.exists(os.path.expanduser(config.ssh.key_file)):
            issues.append(f"SSH key file not found: {config.ssh.key_file}")

        if not config.directory_mappings:
            issues.append("No directory mappings configured")

        return {
            "config_found": True,
            "config_path": config_manager.config_path,
            "project_name": config.project_name,
            "aws_region": config.aws.region,
            "ssh_user": config.ssh.user,
            "directory_count": len(config.directory_mappings),
            "issues": issues,
            "status": "warning" if issues else "ok",
        }

    except Exception as e:
        return {"config_found": False, "error": str(e), "status": "critical"}


def performance_benchmark() -> Dict[str, Any]:
    """Run basic performance benchmarks."""
    results = {}

    # CPU benchmark
    start_time = time.time()
    # Simple CPU test
    total = 0
    for i in range(1000000):
        total += i * i
    cpu_time = time.time() - start_time

    results["cpu_benchmark"] = {
        "duration_seconds": cpu_time,
        "operations_per_second": 1000000 / cpu_time,
        "status": "ok" if cpu_time < 1.0 else "warning",
    }

    # Memory test
    memory = psutil.virtual_memory()
    results["memory_status"] = {
        "total_gb": memory.total / (1024**3),
        "available_gb": memory.available / (1024**3),
        "usage_percent": memory.percent,
        "status": "ok" if memory.percent < 80 else "warning",
    }

    # Disk test
    disk = psutil.disk_usage("/")
    results["disk_status"] = {
        "total_gb": disk.total / (1024**3),
        "free_gb": disk.free / (1024**3),
        "usage_percent": (disk.used / disk.total) * 100,
        "status": "ok" if (disk.used / disk.total) < 0.9 else "warning",
    }

    return results


def generate_report(diagnostics: Dict[str, Any]) -> None:
    """Generate and display comprehensive diagnostic report."""
    console.print("\n[bold blue]📊 EC2 Dynamic Sync Diagnostic Report[/bold blue]")
    console.print(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"Version: {__version__}\n")

    # System Information
    system_info = diagnostics["system_info"]
    console.print("[bold]🖥️  System Information[/bold]")

    system_table = Table(show_header=False, box=None)
    system_table.add_column("Property", style="cyan")
    system_table.add_column("Value", style="white")

    system_table.add_row("Platform", system_info["platform"])
    system_table.add_row("Python Version", system_info["python_version"])
    system_table.add_row("Architecture", system_info["architecture"])
    system_table.add_row("CPU Cores", str(system_info["cpu_count"]))
    system_table.add_row("Memory", f"{system_info['memory_total'] / (1024**3):.1f} GB")

    console.print(system_table)

    # Python Dependencies
    console.print("\n[bold]🐍 Python Dependencies[/bold]")

    deps_table = Table()
    deps_table.add_column("Package", style="cyan")
    deps_table.add_column("Status", style="green")
    deps_table.add_column("Version", style="yellow")
    deps_table.add_column("Purpose", style="blue")

    for package, info in diagnostics["python_deps"].items():
        status = "✅ Installed" if info["installed"] else "❌ Missing"
        version = info["version"] or "N/A"
        deps_table.add_row(package, status, version, info["purpose"])

    console.print(deps_table)

    # System Commands
    console.print("\n[bold]⚙️  System Commands[/bold]")

    cmd_table = Table()
    cmd_table.add_column("Command", style="cyan")
    cmd_table.add_column("Status", style="green")
    cmd_table.add_column("Required", style="yellow")
    cmd_table.add_column("Purpose", style="blue")

    for cmd, info in diagnostics["system_commands"].items():
        status = "✅ Available" if info["available"] else "❌ Missing"
        required = "Yes" if info["required"] else "Optional"
        cmd_table.add_row(cmd, status, required, info["purpose"])

    console.print(cmd_table)

    # Network Connectivity
    console.print("\n[bold]🌐 Network Connectivity[/bold]")

    net_table = Table()
    net_table.add_column("Service", style="cyan")
    net_table.add_column("Status", style="green")
    net_table.add_column("Host", style="yellow")

    for service, info in diagnostics["network"].items():
        status = "✅ Reachable" if info["reachable"] else "❌ Unreachable"
        net_table.add_row(service.upper(), status, info["host"])

    console.print(net_table)

    # Configuration Status
    console.print("\n[bold]⚙️  Configuration Status[/bold]")

    config_info = diagnostics["configuration"]
    if config_info["config_found"]:
        console.print("[green]✅ Configuration file found[/green]")
        if "config_path" in config_info:
            console.print(f"  Path: {config_info['config_path']}")
            console.print(f"  Project: {config_info.get('project_name', 'Unknown')}")
            console.print(f"  AWS Region: {config_info.get('aws_region', 'Unknown')}")
            console.print(
                f"  Directory Mappings: {config_info.get('directory_count', 0)}"
            )

        if config_info.get("issues"):
            console.print("\n[yellow]⚠️  Configuration Issues:[/yellow]")
            for issue in config_info["issues"]:
                console.print(f"  • {issue}")
    else:
        console.print("[red]❌ No configuration file found[/red]")
        console.print("  Run 'ec2-sync-setup init' to create a configuration")

    # Performance Metrics
    console.print("\n[bold]⚡ Performance Metrics[/bold]")

    perf_info = diagnostics["performance"]

    perf_table = Table()
    perf_table.add_column("Metric", style="cyan")
    perf_table.add_column("Value", style="green")
    perf_table.add_column("Status", style="yellow")

    cpu_bench = perf_info["cpu_benchmark"]
    perf_table.add_row(
        "CPU Performance",
        f"{cpu_bench['operations_per_second']:,.0f} ops/sec",
        "✅ Good" if cpu_bench["status"] == "ok" else "⚠️  Slow",
    )

    memory = perf_info["memory_status"]
    perf_table.add_row(
        "Memory Usage",
        f"{memory['usage_percent']:.1f}% ({memory['available_gb']:.1f} GB free)",
        "✅ Good" if memory["status"] == "ok" else "⚠️  High",
    )

    disk = perf_info["disk_status"]
    perf_table.add_row(
        "Disk Usage",
        f"{disk['usage_percent']:.1f}% ({disk['free_gb']:.1f} GB free)",
        "✅ Good" if disk["status"] == "ok" else "⚠️  Full",
    )

    console.print(perf_table)


def get_recommendations(diagnostics: Dict[str, Any]) -> List[str]:
    """Generate recommendations based on diagnostic results."""
    recommendations = []

    # Check for missing critical dependencies
    missing_critical = [
        cmd
        for cmd, info in diagnostics["system_commands"].items()
        if not info["available"] and info["required"]
    ]

    if missing_critical:
        recommendations.append(
            f"Install missing critical commands: {', '.join(missing_critical)}"
        )

    # Check for missing Python packages
    missing_packages = [
        pkg for pkg, info in diagnostics["python_deps"].items() if not info["installed"]
    ]

    if missing_packages:
        recommendations.append(
            f"Install missing Python packages: pip install {' '.join(missing_packages)}"
        )

    # Check configuration
    config_info = diagnostics["configuration"]
    if not config_info["config_found"]:
        recommendations.append("Run 'ec2-sync-setup init' to create configuration")
    elif config_info.get("issues"):
        recommendations.append("Fix configuration issues listed above")

    # Check performance
    perf_info = diagnostics["performance"]
    if perf_info["memory_status"]["status"] == "warning":
        recommendations.append("Consider closing other applications to free memory")

    if perf_info["disk_status"]["status"] == "warning":
        recommendations.append("Free up disk space to improve performance")

    # Check network
    unreachable = [
        service
        for service, info in diagnostics["network"].items()
        if not info["reachable"]
    ]

    if unreachable:
        recommendations.append("Check network connectivity for unreachable services")

    return recommendations


@click.command()
@click.option("--config", type=str, help="Configuration file path")
@click.option(
    "--output",
    type=click.Choice(["console", "json", "yaml"]),
    default="console",
    help="Output format",
)
@click.option("--save-report", type=str, help="Save report to file")
def doctor(config: Optional[str], output: str, save_report: Optional[str]):
    """Comprehensive system diagnostics and health checks."""
    try:
        # Only show UI elements for console output
        if output == "console":
            console.print("[bold blue]🏥 EC2 Dynamic Sync Doctor[/bold blue]")
            console.print("Running comprehensive system diagnostics...\n")

        progress_console = console if output == "console" else None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=progress_console,
        ) as progress:

            # Collect diagnostics
            diagnostics = {}

            task = progress.add_task("Gathering system information...", total=None)
            diagnostics["system_info"] = get_system_info()

            progress.update(task, description="Checking Python dependencies...")
            diagnostics["python_deps"] = check_python_dependencies()

            progress.update(task, description="Checking system commands...")
            diagnostics["system_commands"] = check_system_commands()

            progress.update(task, description="Testing network connectivity...")
            diagnostics["network"] = check_network_connectivity()

            progress.update(task, description="Analyzing configuration...")
            diagnostics["configuration"] = check_configuration()

            progress.update(task, description="Running performance benchmarks...")
            diagnostics["performance"] = performance_benchmark()

            progress.remove_task(task)

        # Generate output
        if output == "console":
            generate_report(diagnostics)

            # Show recommendations
            recommendations = get_recommendations(diagnostics)
            if recommendations:
                console.print("\n[bold]💡 Recommendations[/bold]")
                for i, rec in enumerate(recommendations, 1):
                    console.print(f"  {i}. {rec}")
            else:
                console.print(
                    "\n[green]🎉 No issues found! Your system is ready for EC2 Dynamic Sync.[/green]"
                )

        elif output == "json":
            import json

            console.print(json.dumps(diagnostics, indent=2, default=str))

        elif output == "yaml":
            import yaml

            console.print(yaml.dump(diagnostics, default_flow_style=False))

        # Save report if requested
        if save_report:
            with open(save_report, "w") as f:
                if save_report.endswith(".json"):
                    import json

                    json.dump(diagnostics, f, indent=2, default=str)
                else:
                    import yaml

                    yaml.dump(diagnostics, f, default_flow_style=False)
            console.print(f"\n[green]📄 Report saved to {save_report}[/green]")

    except Exception as e:
        console.print(f"\n[red]❌ Diagnostic failed: {e}[/red]")
        sys.exit(1)


def main():
    """Main entry point for the doctor CLI."""
    try:
        doctor()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Diagnostic interrupted by user[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
