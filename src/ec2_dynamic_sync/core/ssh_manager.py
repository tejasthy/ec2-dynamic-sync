"""
SSH Connection Management for EC2 Dynamic Sync.

This module handles SSH connectivity testing and management for EC2 instances
with enhanced security, error handling, and connection management.
"""

import subprocess
import time
import logging
import os
import stat
from typing import Optional, Dict, Any, List
from pathlib import Path

from .models import SSHConfig
from .exceptions import SSHConnectionError, PermissionError as SyncPermissionError


class SSHManager:
    """Manages SSH connections to EC2 instances."""
    
    def __init__(self, ssh_config: SSHConfig):
        """Initialize SSH manager with configuration.
        
        Args:
            ssh_config: SSH configuration object
            
        Raises:
            SSHConnectionError: If SSH configuration is invalid
            PermissionError: If SSH key permissions are incorrect
        """
        self.config = ssh_config
        self.logger = logging.getLogger(__name__)
        
        # Expand SSH key path
        self.key_file = os.path.expanduser(self.config.key_file)
        
        # Validate SSH key file
        self._validate_key_file()
        
        # Check and fix key file permissions
        self._check_key_permissions()
    
    def _validate_key_file(self):
        """Validate SSH key file exists and is readable."""
        if not os.path.exists(self.key_file):
            raise SSHConnectionError(
                f"SSH key file not found: {self.key_file}",
                key_file=self.key_file
            )
        
        if not os.path.isfile(self.key_file):
            raise SSHConnectionError(
                f"SSH key path is not a file: {self.key_file}",
                key_file=self.key_file
            )
        
        # Check if file is readable
        if not os.access(self.key_file, os.R_OK):
            raise SyncPermissionError(
                f"SSH key file is not readable: {self.key_file}",
                resource_type="file",
                resource_path=self.key_file,
                required_permissions=["read"]
            )
    
    def _check_key_permissions(self):
        """Check and fix SSH key file permissions."""
        try:
            stat_info = os.stat(self.key_file)
            current_perms = stat.filemode(stat_info.st_mode)
            octal_perms = oct(stat_info.st_mode)[-3:]
            
            if octal_perms != '600':
                self.logger.warning(
                    f"SSH key permissions are {octal_perms} ({current_perms}), should be 600"
                )
                
                try:
                    os.chmod(self.key_file, 0o600)
                    self.logger.info(f"Fixed SSH key permissions to 600")
                except PermissionError as e:
                    raise SyncPermissionError(
                        f"Cannot fix SSH key permissions: {e}. Please run: chmod 600 {self.key_file}",
                        resource_type="file",
                        resource_path=self.key_file,
                        required_permissions=["write"]
                    ) from e
                    
        except Exception as e:
            self.logger.warning(f"Could not check SSH key permissions: {e}")
    
    def build_ssh_command(self, host: str, command: str = None) -> List[str]:
        """Build SSH command with proper options.
        
        Args:
            host: Target host
            command: Optional command to execute
            
        Returns:
            List of command arguments
        """
        ssh_cmd = [
            'ssh',
            '-i', self.key_file,
            '-p', str(self.config.port),
            '-o', f"ConnectTimeout={self.config.connect_timeout}",
            '-o', 'BatchMode=yes',  # Don't prompt for passwords
            '-o', 'PasswordAuthentication=no',
            '-o', 'PubkeyAuthentication=yes',
            '-o', 'PreferredAuthentications=publickey',
        ]
        
        if self.config.strict_host_checking:
            ssh_cmd.extend(['-o', 'StrictHostKeyChecking=yes'])
        else:
            ssh_cmd.extend(['-o', 'StrictHostKeyChecking=no'])
            ssh_cmd.extend(['-o', 'UserKnownHostsFile=/dev/null'])
            ssh_cmd.extend(['-o', 'LogLevel=ERROR'])  # Reduce noise from host key warnings
        
        # Add compression for better performance over slow connections
        ssh_cmd.extend(['-o', 'Compression=yes'])
        
        # Add host
        user_host = f"{self.config.user}@{host}"
        ssh_cmd.append(user_host)
        
        # Add command if provided
        if command:
            ssh_cmd.append(command)
        
        return ssh_cmd
    
    def test_connection(self, host: str, timeout: int = None) -> bool:
        """Test SSH connection to host.
        
        Args:
            host: Target host
            timeout: Connection timeout
            
        Returns:
            True if connection successful, False otherwise
        """
        if timeout is None:
            timeout = self.config.connect_timeout
        
        try:
            cmd = self.build_ssh_command(host, 'echo "SSH connection successful"')
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                self.logger.debug(f"SSH connection to {host} successful")
                return True
            else:
                self.logger.debug(f"SSH connection to {host} failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.debug(f"SSH connection to {host} timed out")
            return False
        except FileNotFoundError:
            self.logger.error("SSH client not found. Please install OpenSSH client.")
            return False
        except Exception as e:
            self.logger.debug(f"SSH connection to {host} failed: {e}")
            return False
    
    def wait_for_ssh(self, host: str, max_wait: int = 300) -> bool:
        """Wait for SSH to become available on host.
        
        Args:
            host: Target host
            max_wait: Maximum wait time in seconds
            
        Returns:
            True if SSH becomes available, False if timeout
        """
        self.logger.info(f"Waiting for SSH to become available on {host}...")
        
        max_retries = self.config.max_retries
        retry_delay = self.config.retry_delay
        
        start_time = time.time()
        attempt = 0
        
        while time.time() - start_time < max_wait:
            attempt += 1
            
            if self.test_connection(host):
                self.logger.info(f"SSH connection to {host} established (attempt {attempt})")
                return True
            
            if attempt >= max_retries:
                self.logger.debug(f"SSH attempt {attempt} failed, waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)
                attempt = 0  # Reset attempt counter
            else:
                time.sleep(2)  # Short delay between quick retries
        
        self.logger.error(f"SSH connection to {host} failed after {max_wait}s")
        return False
    
    def execute_command(self, host: str, command: str, timeout: int = 60) -> Dict[str, Any]:
        """Execute a command on the remote host via SSH.
        
        Args:
            host: Target host
            command: Command to execute
            timeout: Command timeout
            
        Returns:
            Dictionary with execution results
        """
        try:
            cmd = self.build_ssh_command(host, command)
            
            self.logger.debug(f"Executing SSH command on {host}: {command}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                'success': result.returncode == 0,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'command': command,
                'host': host
            }
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"SSH command timed out after {timeout}s: {command}")
            return {
                'success': False,
                'returncode': -1,
                'stdout': '',
                'stderr': f'Command timed out after {timeout}s',
                'command': command,
                'host': host
            }
        except Exception as e:
            self.logger.error(f"SSH command failed: {e}")
            return {
                'success': False,
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'command': command,
                'host': host
            }
    
    def check_remote_directory(self, host: str, directory: str) -> bool:
        """Check if a directory exists on the remote host.
        
        Args:
            host: Target host
            directory: Directory path to check
            
        Returns:
            True if directory exists, False otherwise
        """
        result = self.execute_command(host, f'test -d "{directory}"')
        return result['success']
    
    def create_remote_directory(self, host: str, directory: str) -> bool:
        """Create a directory on the remote host.
        
        Args:
            host: Target host
            directory: Directory path to create
            
        Returns:
            True if directory was created, False otherwise
        """
        result = self.execute_command(host, f'mkdir -p "{directory}"')
        if result['success']:
            self.logger.debug(f"Created remote directory: {directory}")
            return True
        else:
            self.logger.error(f"Failed to create remote directory {directory}: {result['stderr']}")
            return False
    
    def get_remote_disk_usage(self, host: str, directory: str) -> Optional[Dict[str, str]]:
        """Get disk usage information for a remote directory.
        
        Args:
            host: Target host
            directory: Directory path
            
        Returns:
            Dictionary with size information or None if failed
        """
        result = self.execute_command(host, f'du -sh "{directory}" 2>/dev/null || echo "0\t{directory}"')
        
        if result['success'] and result['stdout'].strip():
            parts = result['stdout'].strip().split('\t')
            if len(parts) >= 2:
                return {
                    'size': parts[0],
                    'path': parts[1]
                }
        
        return None

    def get_remote_file_count(self, host: str, directory: str) -> Optional[int]:
        """Get the number of files in a remote directory.

        Args:
            host: Target host
            directory: Directory path

        Returns:
            Number of files or None if failed
        """
        result = self.execute_command(
            host,
            f'find "{directory}" -type f 2>/dev/null | wc -l'
        )

        if result['success'] and result['stdout'].strip().isdigit():
            return int(result['stdout'].strip())

        return None

    def check_remote_rsync(self, host: str) -> bool:
        """Check if rsync is available on the remote host.

        Args:
            host: Target host

        Returns:
            True if rsync is available, False otherwise
        """
        result = self.execute_command(host, 'which rsync')
        if result['success']:
            self.logger.debug("rsync is available on remote host")
            return True
        else:
            self.logger.warning("rsync not found on remote host")
            return False

    def get_remote_system_info(self, host: str) -> Dict[str, Any]:
        """Get system information from remote host.

        Args:
            host: Target host

        Returns:
            Dictionary with system information
        """
        info = {}

        # Get OS information
        result = self.execute_command(host, 'uname -a')
        if result['success']:
            info['uname'] = result['stdout'].strip()

        # Get distribution information
        result = self.execute_command(host, 'cat /etc/os-release 2>/dev/null || echo "Unknown"')
        if result['success']:
            info['os_release'] = result['stdout'].strip()

        # Get disk space
        result = self.execute_command(host, 'df -h /')
        if result['success']:
            info['disk_space'] = result['stdout'].strip()

        # Get memory information
        result = self.execute_command(host, 'free -h')
        if result['success']:
            info['memory'] = result['stdout'].strip()

        # Get uptime
        result = self.execute_command(host, 'uptime')
        if result['success']:
            info['uptime'] = result['stdout'].strip()

        return info

    def get_ssh_options_string(self) -> str:
        """Get SSH options as a string for use with rsync -e option.

        Returns:
            SSH options string
        """
        options = [
            f'-i {self.key_file}',
            f'-p {self.config.port}',
            f'-o ConnectTimeout={self.config.connect_timeout}',
            '-o BatchMode=yes',
            '-o PasswordAuthentication=no',
            '-o PubkeyAuthentication=yes',
            '-o PreferredAuthentications=publickey',
            '-o Compression=yes',
        ]

        if self.config.strict_host_checking:
            options.append('-o StrictHostKeyChecking=yes')
        else:
            options.append('-o StrictHostKeyChecking=no')
            options.append('-o UserKnownHostsFile=/dev/null')
            options.append('-o LogLevel=ERROR')

        return ' '.join(options)

    def build_rsync_ssh_command(self) -> str:
        """Build SSH command string for rsync -e option.

        Returns:
            SSH command string for rsync
        """
        return f'ssh {self.get_ssh_options_string()}'

    def test_rsync_connection(self, host: str) -> bool:
        """Test rsync connectivity to remote host.

        Args:
            host: Target host

        Returns:
            True if rsync connection works, False otherwise
        """
        try:
            # Test basic rsync connectivity with dry-run
            cmd = [
                'rsync',
                '--dry-run',
                '-e', self.build_rsync_ssh_command(),
                '/dev/null',
                f'{self.config.user}@{host}:/tmp/'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            return result.returncode == 0

        except Exception as e:
            self.logger.debug(f"Rsync connection test failed: {e}")
            return False

    def get_connection_diagnostics(self, host: str) -> Dict[str, Any]:
        """Get comprehensive connection diagnostics.

        Args:
            host: Target host

        Returns:
            Dictionary with diagnostic information
        """
        diagnostics = {
            'host': host,
            'ssh_config': {
                'user': self.config.user,
                'port': self.config.port,
                'key_file': self.key_file,
                'strict_host_checking': self.config.strict_host_checking,
            },
            'tests': {}
        }

        # Test basic SSH connectivity
        diagnostics['tests']['ssh_connection'] = self.test_connection(host)

        # Test rsync availability
        if diagnostics['tests']['ssh_connection']:
            diagnostics['tests']['rsync_available'] = self.check_remote_rsync(host)
            diagnostics['tests']['rsync_connection'] = self.test_rsync_connection(host)

            # Get system information
            try:
                diagnostics['remote_system'] = self.get_remote_system_info(host)
            except Exception as e:
                diagnostics['remote_system'] = {'error': str(e)}
        else:
            diagnostics['tests']['rsync_available'] = False
            diagnostics['tests']['rsync_connection'] = False
            diagnostics['remote_system'] = {'error': 'SSH connection failed'}

        # Check local SSH client
        try:
            result = subprocess.run(['ssh', '-V'], capture_output=True, text=True)
            diagnostics['local_ssh_version'] = result.stderr.strip() if result.stderr else result.stdout.strip()
        except FileNotFoundError:
            diagnostics['local_ssh_version'] = 'SSH client not found'

        # Check local rsync
        try:
            result = subprocess.run(['rsync', '--version'], capture_output=True, text=True)
            diagnostics['local_rsync_version'] = result.stdout.split('\n')[0] if result.stdout else 'Unknown'
        except FileNotFoundError:
            diagnostics['local_rsync_version'] = 'rsync not found'

        return diagnostics
