#!/usr/bin/env python3
"""Setup CLI for EC2 Dynamic Sync."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ..core import AWSManager, ConfigManager, SSHManager, SyncOrchestrator
from ..core.exceptions import ConfigurationError, EC2SyncError
from ..core.models import AWSConfig, DirectoryMapping, SSHConfig, SyncConfig

console = Console()


def check_dependencies() -> Dict[str, bool]:
    """Check if required system dependencies are available."""
    dependencies = {
        "aws": False,
        "ssh": False,
        "rsync": False,
        "python": True,  # We're running Python, so this is always True
    }

    # Check AWS CLI
    try:
        result = subprocess.run(["aws", "--version"], capture_output=True, text=True)
        dependencies["aws"] = result.returncode == 0
    except FileNotFoundError:
        pass

    # Check SSH
    try:
        result = subprocess.run(["ssh", "-V"], capture_output=True, text=True)
        dependencies["ssh"] = result.returncode == 0 or "OpenSSH" in result.stderr
    except FileNotFoundError:
        pass

    # Check rsync
    try:
        result = subprocess.run(["rsync", "--version"], capture_output=True, text=True)
        dependencies["rsync"] = result.returncode == 0
    except FileNotFoundError:
        pass

    return dependencies


def get_aws_instances(
    region: str = "us-east-1",
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Get list of available EC2 instances.

    Returns:
        Tuple of (instances_list, error_message)
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

        # Try to create EC2 client with specified region
        ec2 = boto3.client("ec2", region_name=region)
        response = ec2.describe_instances()

        instances = []
        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                if instance["State"]["Name"] in ["running", "stopped"]:
                    name = "Unknown"
                    for tag in instance.get("Tags", []):
                        if tag["Key"] == "Name":
                            name = tag["Value"]
                            break

                    instances.append(
                        {
                            "id": instance["InstanceId"],
                            "name": name,
                            "state": instance["State"]["Name"],
                            "type": instance["InstanceType"],
                            "region": region,
                        }
                    )

        return instances, None
    except NoCredentialsError:
        return (
            [],
            "AWS credentials not configured. Run 'aws configure' to set up credentials.",
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "UnauthorizedOperation":
            return (
                [],
                "AWS credentials don't have permission to describe EC2 instances.",
            )
        else:
            return [], f"AWS API error: {e}"
    except ImportError:
        return [], "boto3 not installed. Install with: pip install boto3"
    except Exception as e:
        return [], f"Unexpected error accessing AWS: {e}"


def validate_ssh_key(key_path: str) -> bool:
    """Validate SSH key file exists and has correct permissions."""
    if not os.path.exists(key_path):
        return False

    # Check permissions (should be 600 or 400)
    stat_info = os.stat(key_path)
    permissions = oct(stat_info.st_mode)[-3:]
    return permissions in ["600", "400"]


def create_config_interactive() -> Dict[str, Any]:
    """Interactive configuration creation wizard."""
    console.print("\n[bold blue]🚀 EC2 Dynamic Sync Configuration Wizard[/bold blue]")
    console.print("Let's set up your EC2 synchronization configuration.\n")

    config = {}

    # Project information
    console.print("[bold]Project Information[/bold]")
    config["project_name"] = Prompt.ask("Project name", default="my-ec2-project")
    config["project_description"] = Prompt.ask(
        "Project description (optional)", default=""
    )

    # AWS Configuration
    console.print("\n[bold]AWS Configuration[/bold]")

    # Ask for region first
    config["aws"] = {}
    config["aws"]["region"] = Prompt.ask("AWS Region", default="us-east-1")
    config["aws"]["profile"] = Prompt.ask("AWS Profile", default="default")

    # Get available instances from the specified region
    instances, aws_error = get_aws_instances(config["aws"]["region"])
    if aws_error:
        console.print(f"[yellow]⚠️  Could not fetch EC2 instances: {aws_error}[/yellow]")
        console.print("You can still continue with manual configuration.")

    if instances:
        console.print("Available EC2 instances:")
        table = Table()
        table.add_column("Index", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Instance ID", style="yellow")
        table.add_column("State", style="magenta")
        table.add_column("Type", style="blue")

        for i, instance in enumerate(instances):
            table.add_row(
                str(i + 1),
                instance["name"],
                instance["id"],
                instance["state"],
                instance["type"],
            )
        console.print(table)

        choice = Prompt.ask(
            "Select instance by index, or press Enter to specify manually", default=""
        )

        if choice and choice.isdigit() and 1 <= int(choice) <= len(instances):
            selected = instances[int(choice) - 1]
            config["aws"] = {
                "instance_id": selected["id"],
                "instance_name": (
                    selected["name"] if selected["name"] != "Unknown" else None
                ),
            }
        else:
            config["aws"] = {}
    else:
        config["aws"] = {}
        console.print("[yellow]No instances found or AWS CLI not configured.[/yellow]")

    # Manual AWS configuration if needed
    if "instance_id" not in config["aws"]:
        instance_choice = Prompt.ask(
            "Specify instance by", choices=["id", "name"], default="name"
        )

        if instance_choice == "id":
            config["aws"]["instance_id"] = Prompt.ask("EC2 Instance ID")
        else:
            config["aws"]["instance_name"] = Prompt.ask("EC2 Instance Name (tag)")

    config["aws"]["auto_start_instance"] = Confirm.ask(
        "Auto-start instance if stopped?", default=True
    )

    return config


def complete_ssh_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Complete SSH configuration section."""
    console.print("\n[bold]SSH Configuration[/bold]")

    config["ssh"] = {}
    config["ssh"]["user"] = Prompt.ask("SSH Username", default="ubuntu")

    # SSH key file
    default_key_paths = ["~/.ssh/id_rsa", "~/.ssh/id_ed25519", "~/.ssh/ec2-key.pem"]

    existing_keys = []
    for key_path in default_key_paths:
        expanded_path = os.path.expanduser(key_path)
        if os.path.exists(expanded_path):
            existing_keys.append(key_path)

    if existing_keys:
        console.print("Found existing SSH keys:")
        for i, key in enumerate(existing_keys):
            console.print(f"  {i + 1}. {key}")

        choice = Prompt.ask(
            "Select key by index, or specify custom path",
            default="1" if existing_keys else "",
        )

        if choice.isdigit() and 1 <= int(choice) <= len(existing_keys):
            config["ssh"]["key_file"] = existing_keys[int(choice) - 1]
        else:
            config["ssh"]["key_file"] = choice
    else:
        config["ssh"]["key_file"] = Prompt.ask(
            "SSH Key File Path", default="~/.ssh/id_rsa"
        )

    # Validate SSH key
    key_path = os.path.expanduser(config["ssh"]["key_file"])
    if not validate_ssh_key(key_path):
        console.print(
            f"[yellow]Warning: SSH key at {key_path} not found or has incorrect permissions[/yellow]"
        )
        if os.path.exists(key_path):
            console.print("Fixing permissions...")
            os.chmod(key_path, 0o600)
            console.print("[green]✅ Fixed SSH key permissions[/green]")

    config["ssh"]["port"] = int(Prompt.ask("SSH Port", default="22"))
    config["ssh"]["connect_timeout"] = int(
        Prompt.ask("SSH Connect Timeout (seconds)", default="10")
    )

    return config


def complete_directory_mappings(config: Dict[str, Any]) -> Dict[str, Any]:
    """Complete directory mappings configuration."""
    console.print("\n[bold]Directory Mappings[/bold]")
    console.print(
        "Configure which directories to synchronize between local and remote."
    )

    config["directory_mappings"] = []

    while True:
        console.print(
            f"\n[cyan]Directory Mapping #{len(config['directory_mappings']) + 1}[/cyan]"
        )

        mapping = {}
        mapping["name"] = Prompt.ask(
            "Mapping name", default=f"mapping_{len(config['directory_mappings']) + 1}"
        )
        mapping["local_path"] = Prompt.ask("Local directory path", default="~/projects")
        mapping["remote_path"] = Prompt.ask(
            "Remote directory path", default="~/projects"
        )
        mapping["enabled"] = Confirm.ask("Enable this mapping?", default=True)

        config["directory_mappings"].append(mapping)

        if not Confirm.ask("Add another directory mapping?", default=False):
            break

    return config


def complete_sync_options(config: Dict[str, Any]) -> Dict[str, Any]:
    """Complete sync options configuration."""
    console.print("\n[bold]Sync Options[/bold]")

    config["sync_options"] = {}
    config["sync_options"]["archive"] = Confirm.ask(
        "Use archive mode (preserves permissions, timestamps)?", default=True
    )
    config["sync_options"]["verbose"] = Confirm.ask(
        "Enable verbose output?", default=False
    )
    config["sync_options"]["compress"] = Confirm.ask(
        "Enable compression?", default=True
    )
    config["sync_options"]["delete"] = Confirm.ask(
        "Delete files that don't exist on source?", default=False
    )
    config["sync_options"]["progress"] = Confirm.ask(
        "Show progress during sync?", default=True
    )

    bandwidth_limit = Prompt.ask("Bandwidth limit (KB/s, 0 for unlimited)", default="0")
    if bandwidth_limit != "0":
        config["sync_options"]["bandwidth_limit"] = bandwidth_limit

    # Conflict resolution
    config["conflict_resolution"] = Prompt.ask(
        "Conflict resolution strategy",
        choices=["newer", "local", "remote", "manual"],
        default="newer",
    )

    return config


def save_config(config: Dict[str, Any], config_path: Optional[str] = None) -> str:
    """Save configuration to file."""
    if not config_path:
        config_path = os.path.expanduser("~/.ec2-sync.yaml")

    # Ensure directory exists
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, indent=2)

    console.print(f"[green]✅ Configuration saved to {config_path}[/green]")
    return config_path


@click.group()
def setup():
    """Setup and configuration management for EC2 Dynamic Sync."""
    pass


@setup.command()
@click.option("--config", type=str, help="Configuration file path")
@click.option(
    "--template",
    type=click.Choice(["basic", "advanced", "scientific"]),
    default="basic",
    help="Configuration template to use",
)
def init(config: Optional[str], template: str):
    """Interactive configuration wizard."""
    try:
        console.print("[bold blue]🔧 EC2 Dynamic Sync Setup[/bold blue]")

        # Check dependencies first
        console.print("\n[bold]Checking system dependencies...[/bold]")
        deps = check_dependencies()

        dep_table = Table()
        dep_table.add_column("Dependency", style="cyan")
        dep_table.add_column("Status", style="green")
        dep_table.add_column("Required", style="yellow")

        for dep, available in deps.items():
            status = "✅ Available" if available else "❌ Missing"
            required = "Yes" if dep in ["python", "ssh", "rsync"] else "Recommended"
            dep_table.add_row(dep.upper(), status, required)

        console.print(dep_table)

        missing_required = [
            dep
            for dep, available in deps.items()
            if not available and dep in ["ssh", "rsync"]
        ]

        if missing_required:
            console.print(
                f"\n[red]❌ Missing required dependencies: {', '.join(missing_required)}[/red]"
            )
            console.print("Please install missing dependencies and try again.")
            sys.exit(1)

        if not deps["aws"]:
            console.print(
                "\n[yellow]⚠️  AWS CLI not found. Some features may be limited.[/yellow]"
            )
            if not Confirm.ask("Continue anyway?", default=True):
                sys.exit(1)

        # Start configuration wizard
        config_data = create_config_interactive()
        config_data = complete_ssh_config(config_data)
        config_data = complete_directory_mappings(config_data)
        config_data = complete_sync_options(config_data)

        # Save configuration
        config_path = save_config(config_data, config)

        console.print(f"\n[green]🎉 Setup completed successfully![/green]")
        console.print(f"Configuration saved to: {config_path}")
        console.print("\nNext steps:")
        console.print("1. Run 'ec2-sync-setup validate' to verify your configuration")
        console.print("2. Run 'ec2-sync-setup test' to test connectivity")
        console.print("3. Run 'ec2-sync status' to check sync status")

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Setup cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]❌ Setup failed: {e}[/red]")
        sys.exit(1)


@setup.command()
@click.option("--config", type=str, help="Configuration file path")
def validate(config: Optional[str]):
    """Validate configuration file."""
    try:
        console.print("[bold blue]🔍 Validating Configuration[/bold blue]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Loading configuration...", total=None)

            # Load configuration
            config_manager = ConfigManager(config)
            if not config_manager.config_path:
                console.print("[red]❌ No configuration file found[/red]")
                console.print(
                    "Run 'ec2-sync-setup init' to create a configuration file."
                )
                sys.exit(1)

            progress.update(task, description="Validating YAML syntax...")

            try:
                sync_config = config_manager.get_config()
                console.print(
                    f"[green]✅ Configuration loaded from {config_manager.config_path}[/green]"
                )
            except ConfigurationError as e:
                console.print(
                    f"[red]❌ Configuration validation failed: {e.message}[/red]"
                )
                sys.exit(1)

            progress.update(task, description="Checking AWS configuration...")

            # Validate AWS configuration
            aws_issues = []
            if not sync_config.aws.instance_id and not sync_config.aws.instance_name:
                aws_issues.append("No instance ID or name specified")

            if aws_issues:
                console.print("[yellow]⚠️  AWS Configuration Issues:[/yellow]")
                for issue in aws_issues:
                    console.print(f"  • {issue}")
            else:
                console.print("[green]✅ AWS configuration valid[/green]")

            progress.update(task, description="Checking SSH configuration...")

            # Validate SSH configuration
            ssh_issues = []
            key_path = os.path.expanduser(sync_config.ssh.key_file)
            if not os.path.exists(key_path):
                ssh_issues.append(f"SSH key file not found: {key_path}")
            elif not validate_ssh_key(key_path):
                ssh_issues.append(f"SSH key has incorrect permissions: {key_path}")

            if ssh_issues:
                console.print("[yellow]⚠️  SSH Configuration Issues:[/yellow]")
                for issue in ssh_issues:
                    console.print(f"  • {issue}")
            else:
                console.print("[green]✅ SSH configuration valid[/green]")

            progress.update(task, description="Checking directory mappings...")

            # Validate directory mappings
            dir_issues = []
            for mapping in sync_config.directory_mappings:
                local_path = os.path.expanduser(mapping.local_path)
                if not os.path.exists(local_path):
                    dir_issues.append(f"Local directory not found: {local_path}")

            if dir_issues:
                console.print("[yellow]⚠️  Directory Mapping Issues:[/yellow]")
                for issue in dir_issues:
                    console.print(f"  • {issue}")
            else:
                console.print("[green]✅ Directory mappings valid[/green]")

            progress.remove_task(task)

        # Summary
        total_issues = len(aws_issues) + len(ssh_issues) + len(dir_issues)
        if total_issues == 0:
            console.print("\n[green]🎉 Configuration validation passed![/green]")
        else:
            console.print(
                f"\n[yellow]⚠️  Found {total_issues} issue(s) that should be addressed[/yellow]"
            )
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[red]❌ Validation failed: {e}[/red]")
        sys.exit(1)


@setup.command()
@click.option("--config", type=str, help="Configuration file path")
def test(config: Optional[str]):
    """Test connectivity and functionality."""
    try:
        console.print("[bold blue]🧪 Testing Connectivity[/bold blue]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing...", total=None)

            # Load configuration
            orchestrator = SyncOrchestrator.from_config_file(config)

            progress.update(task, description="Testing AWS connectivity...")

            # Test AWS connectivity
            try:
                instance_info = orchestrator.aws_manager.get_instance_info()
                if instance_info:
                    console.print(f"[green]✅ AWS connectivity successful[/green]")
                    console.print(
                        f"  Instance: {instance_info['instance_id']} ({instance_info['state']})"
                    )
                else:
                    console.print("[red]❌ Failed to get instance information[/red]")
                    sys.exit(1)
            except Exception as e:
                console.print(f"[red]❌ AWS connectivity failed: {e}[/red]")
                sys.exit(1)

            progress.update(task, description="Testing instance connectivity...")

            # Test instance connectivity
            try:
                connectivity_results = orchestrator.test_connectivity()
                if connectivity_results["overall_success"]:
                    console.print("[green]✅ Instance connectivity successful[/green]")
                    console.print(
                        f"  SSH: {'✅' if connectivity_results['ssh_connectivity'] else '❌'}"
                    )
                else:
                    console.print("[red]❌ Instance connectivity failed[/red]")
                    if "error" in connectivity_results:
                        console.print(f"  Error: {connectivity_results['error']}")
                    sys.exit(1)
            except Exception as e:
                console.print(f"[red]❌ Connectivity test failed: {e}[/red]")
                sys.exit(1)

            progress.update(task, description="Testing directory access...")

            # Test directory access
            try:
                status = orchestrator.get_sync_status()
                if "error" not in status:
                    console.print("[green]✅ Directory access successful[/green]")
                    for local_path, info in status.get("directories", {}).items():
                        if "error" in info:
                            console.print(
                                f"  [yellow]⚠️  {local_path}: {info['error']}[/yellow]"
                            )
                        else:
                            console.print(f"  [green]✅ {local_path}[/green]")
                else:
                    console.print(
                        f"[red]❌ Directory access failed: {status['error']}[/red]"
                    )
                    sys.exit(1)
            except Exception as e:
                console.print(f"[red]❌ Directory test failed: {e}[/red]")
                sys.exit(1)

            progress.remove_task(task)

        console.print("\n[green]🎉 All tests passed![/green]")
        console.print("Your EC2 Dynamic Sync setup is ready to use.")

    except Exception as e:
        console.print(f"\n[red]❌ Testing failed: {e}[/red]")
        sys.exit(1)


@setup.command()
@click.option(
    "--schedule",
    type=str,
    required=True,
    help='Cron schedule (e.g., "*/15 * * * *" for every 15 minutes)',
)
@click.option("--config", type=str, help="Configuration file path")
@click.option(
    "--mode",
    type=click.Choice(["sync", "push", "pull"]),
    default="sync",
    help="Sync mode for cron job",
)
@click.option("--user", type=str, help="User to run cron job as (requires sudo)")
def cron(schedule: str, config: Optional[str], mode: str, user: Optional[str]):
    """Set up automated synchronization with cron."""
    try:
        console.print("[bold blue]⏰ Setting up Cron Job[/bold blue]")

        # Validate cron schedule format
        schedule_parts = schedule.split()
        if len(schedule_parts) != 5:
            console.print("[red]❌ Invalid cron schedule format[/red]")
            console.print("Expected format: 'minute hour day month weekday'")
            console.print("Example: '*/15 * * * *' (every 15 minutes)")
            sys.exit(1)

        # Get the ec2-sync command path
        ec2_sync_path = shutil.which("ec2-sync")
        if not ec2_sync_path:
            console.print("[red]❌ ec2-sync command not found in PATH[/red]")
            console.print("Make sure EC2 Dynamic Sync is properly installed.")
            sys.exit(1)

        # Build cron command
        cron_command = f"{ec2_sync_path} {mode}"
        if config:
            cron_command += f" --config {config}"

        # Add output redirection for logging
        log_dir = os.path.expanduser("~/.ec2-sync/logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "cron.log")
        cron_command += f" >> {log_file} 2>&1"

        # Create cron entry
        cron_entry = f"{schedule} {cron_command}"

        console.print(f"Cron entry: {cron_entry}")

        if Confirm.ask("Add this cron job?", default=True):
            try:
                # Get current crontab
                if user:
                    result = subprocess.run(
                        ["sudo", "crontab", "-u", user, "-l"],
                        capture_output=True,
                        text=True,
                    )
                else:
                    result = subprocess.run(
                        ["crontab", "-l"], capture_output=True, text=True
                    )

                current_crontab = result.stdout if result.returncode == 0 else ""

                # Check if entry already exists
                if cron_command in current_crontab:
                    console.print("[yellow]⚠️  Similar cron job already exists[/yellow]")
                    if not Confirm.ask("Continue anyway?", default=False):
                        sys.exit(0)

                # Add new entry
                new_crontab = current_crontab.rstrip() + "\n" + cron_entry + "\n"

                # Install new crontab
                if user:
                    process = subprocess.Popen(
                        ["sudo", "crontab", "-u", user, "-"],
                        stdin=subprocess.PIPE,
                        text=True,
                    )
                else:
                    process = subprocess.Popen(
                        ["crontab", "-"], stdin=subprocess.PIPE, text=True
                    )

                process.communicate(input=new_crontab)

                if process.returncode == 0:
                    console.print("[green]✅ Cron job added successfully![/green]")
                    console.print(f"Logs will be written to: {log_file}")
                    console.print(f"Schedule: {schedule}")
                    console.print(f"Command: ec2-sync {mode}")
                else:
                    console.print("[red]❌ Failed to add cron job[/red]")
                    sys.exit(1)

            except subprocess.CalledProcessError as e:
                console.print(f"[red]❌ Cron setup failed: {e}[/red]")
                sys.exit(1)
        else:
            console.print("Cron job setup cancelled.")

    except Exception as e:
        console.print(f"\n[red]❌ Cron setup failed: {e}[/red]")
        sys.exit(1)


def main():
    """Main entry point for the setup CLI."""
    try:
        setup()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Operation interrupted by user[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
