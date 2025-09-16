#!/usr/bin/env python3
"""
Rsync Operations Manager for LightSheetV2 Sync System

This module handles all rsync operations including:
- Bidirectional synchronization
- Conflict resolution
- Progress monitoring
- Error handling and retries
"""

import subprocess
import time
import logging
import os
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import re


class RsyncManager:
    """Manages rsync operations for file synchronization."""
    
    def __init__(self, config: Dict[str, Any], ssh_manager):
        """Initialize rsync manager with configuration."""
        self.config = config
        self.sync_config = config['sync']
        self.ssh_manager = ssh_manager
        self.logger = logging.getLogger(__name__)
        
        # Build base rsync command options
        self.base_rsync_options = self._build_base_options()
    
    def _build_base_options(self) -> List[str]:
        """Build base rsync options from configuration."""
        options = ['rsync']
        
        # Basic flags
        if self.sync_config['options'].get('archive', True):
            options.append('-a')
        if self.sync_config['options'].get('verbose', True):
            options.append('-v')
        if self.sync_config['options'].get('compress', True):
            options.append('-z')
        if self.sync_config['options'].get('progress', True):
            options.append('--progress')
        if self.sync_config['options'].get('partial', True):
            options.append('--partial')
        if self.sync_config['options'].get('delete', False):
            options.append('--delete')
        if self.sync_config['options'].get('dry_run', False):
            options.append('--dry-run')
        if self.sync_config['options'].get('backup', False):
            options.append('--backup')
        
        # Bandwidth limit
        bw_limit = self.sync_config['options'].get('bandwidth_limit')
        if bw_limit:
            options.extend(['--bwlimit', str(bw_limit)])
        
        # Exclude patterns
        exclude_patterns = self.sync_config['options'].get('exclude_patterns', [])
        for pattern in exclude_patterns:
            options.extend(['--exclude', pattern])
        
        # SSH command
        ssh_cmd = self.ssh_manager.build_rsync_ssh_command()
        options.extend(['-e', ssh_cmd])
        
        return options
    
    def _expand_path(self, path: str) -> str:
        """Expand user home directory in path."""
        return os.path.expanduser(path)
    
    def _build_local_path(self, sync_dir: str) -> str:
        """Build full local path for sync directory."""
        base_dir = self._expand_path(self.sync_config['local']['base_dir'])
        return os.path.join(base_dir, sync_dir)
    
    def _build_remote_path(self, host: str, sync_dir: str) -> str:
        """Build full remote path for sync directory."""
        user = self.ssh_manager.ssh_config['user']
        base_dir = self.sync_config['remote']['base_dir']
        remote_path = f"{base_dir}/{sync_dir}"
        return f"{user}@{host}:{remote_path}"
    
    def check_local_directory(self, sync_dir: str) -> bool:
        """Check if local sync directory exists."""
        local_path = self._build_local_path(sync_dir)
        exists = os.path.exists(local_path)
        
        if not exists:
            self.logger.info(f"Creating local directory: {local_path}")
            try:
                os.makedirs(local_path, exist_ok=True)
                return True
            except Exception as e:
                self.logger.error(f"Failed to create local directory {local_path}: {e}")
                return False
        
        return True
    
    def check_remote_directory(self, host: str, sync_dir: str) -> bool:
        """Check if remote sync directory exists."""
        base_dir = self.sync_config['remote']['base_dir']
        remote_dir = f"{base_dir}/{sync_dir}"
        
        if not self.ssh_manager.check_remote_directory(host, remote_dir):
            self.logger.info(f"Creating remote directory: {remote_dir}")
            return self.ssh_manager.create_remote_directory(host, remote_dir)
        
        return True
    
    def get_directory_info(self, host: str, sync_dir: str) -> Dict[str, Any]:
        """Get information about local and remote directories."""
        local_path = self._build_local_path(sync_dir)
        base_dir = self.sync_config['remote']['base_dir']
        remote_dir = f"{base_dir}/{sync_dir}"
        
        info = {
            'sync_dir': sync_dir,
            'local': {
                'path': local_path,
                'exists': os.path.exists(local_path),
                'size': None,
                'file_count': None
            },
            'remote': {
                'path': remote_dir,
                'exists': False,
                'size': None,
                'file_count': None
            }
        }
        
        # Get local info
        if info['local']['exists']:
            try:
                # Get local file count
                result = subprocess.run(
                    ['find', local_path, '-type', 'f'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    info['local']['file_count'] = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
                
                # Get local size
                result = subprocess.run(
                    ['du', '-sh', local_path],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    info['local']['size'] = result.stdout.split('\t')[0]
            except Exception as e:
                self.logger.debug(f"Could not get local directory info: {e}")
        
        # Get remote info
        info['remote']['exists'] = self.ssh_manager.check_remote_directory(host, remote_dir)
        if info['remote']['exists']:
            size_info = self.ssh_manager.get_remote_disk_usage(host, remote_dir)
            if size_info:
                info['remote']['size'] = size_info['size']
            
            file_count = self.ssh_manager.get_remote_file_count(host, remote_dir)
            if file_count is not None:
                info['remote']['file_count'] = file_count
        
        return info

    def sync_local_to_remote(self, host: str, sync_dir: str, dry_run: bool = False) -> Dict[str, Any]:
        """Sync local directory to remote."""
        local_path = self._build_local_path(sync_dir)
        remote_path = self._build_remote_path(host, sync_dir)

        # Ensure directories exist
        if not self.check_local_directory(sync_dir):
            return {'success': False, 'error': 'Local directory check failed'}

        if not self.check_remote_directory(host, sync_dir):
            return {'success': False, 'error': 'Remote directory check failed'}

        # Build rsync command
        cmd = self.base_rsync_options.copy()

        if dry_run:
            cmd.append('--dry-run')

        # Add trailing slash to source for directory contents sync
        if not local_path.endswith('/'):
            local_path += '/'

        cmd.extend([local_path, remote_path])

        return self._execute_rsync(cmd, f"local-to-remote sync of {sync_dir}")

    def sync_remote_to_local(self, host: str, sync_dir: str, dry_run: bool = False) -> Dict[str, Any]:
        """Sync remote directory to local."""
        local_path = self._build_local_path(sync_dir)
        remote_path = self._build_remote_path(host, sync_dir)

        # Ensure directories exist
        if not self.check_local_directory(sync_dir):
            return {'success': False, 'error': 'Local directory check failed'}

        if not self.check_remote_directory(host, sync_dir):
            return {'success': False, 'error': 'Remote directory check failed'}

        # Build rsync command
        cmd = self.base_rsync_options.copy()

        if dry_run:
            cmd.append('--dry-run')

        # Add trailing slash to source for directory contents sync
        if not remote_path.endswith('/'):
            remote_path += '/'

        cmd.extend([remote_path, local_path])

        return self._execute_rsync(cmd, f"remote-to-local sync of {sync_dir}")

    def sync_bidirectional(self, host: str, sync_dir: str, dry_run: bool = False) -> Dict[str, Any]:
        """Perform bidirectional sync with conflict resolution."""
        conflict_resolution = self.config['modes']['bidirectional'].get('conflict_resolution', 'newer')

        self.logger.info(f"Starting bidirectional sync of {sync_dir} (conflict resolution: {conflict_resolution})")

        results = {
            'sync_dir': sync_dir,
            'local_to_remote': None,
            'remote_to_local': None,
            'conflicts_detected': False,
            'overall_success': False
        }

        if conflict_resolution == 'newer':
            # Use rsync's --update flag to only transfer newer files
            cmd_base = self.base_rsync_options.copy()
            cmd_base.append('--update')  # Only transfer files that are newer

            if dry_run:
                cmd_base.append('--dry-run')

            # Sync local to remote (newer files only)
            local_path = self._build_local_path(sync_dir)
            remote_path = self._build_remote_path(host, sync_dir)

            if not local_path.endswith('/'):
                local_path += '/'

            cmd_l2r = cmd_base.copy()
            cmd_l2r.extend([local_path, remote_path])
            results['local_to_remote'] = self._execute_rsync(cmd_l2r, f"bidirectional L2R sync of {sync_dir}")

            # Sync remote to local (newer files only)
            if not remote_path.endswith('/'):
                remote_path += '/'

            cmd_r2l = cmd_base.copy()
            cmd_r2l.extend([remote_path, local_path.rstrip('/')])
            results['remote_to_local'] = self._execute_rsync(cmd_r2l, f"bidirectional R2L sync of {sync_dir}")

        elif conflict_resolution == 'local':
            # Local takes precedence
            results['local_to_remote'] = self.sync_local_to_remote(host, sync_dir, dry_run)

        elif conflict_resolution == 'remote':
            # Remote takes precedence
            results['remote_to_local'] = self.sync_remote_to_local(host, sync_dir, dry_run)

        else:
            return {'success': False, 'error': f'Unknown conflict resolution: {conflict_resolution}'}

        # Determine overall success
        if results['local_to_remote'] and results['remote_to_local']:
            results['overall_success'] = (
                results['local_to_remote']['success'] and
                results['remote_to_local']['success']
            )
        elif results['local_to_remote']:
            results['overall_success'] = results['local_to_remote']['success']
        elif results['remote_to_local']:
            results['overall_success'] = results['remote_to_local']['success']

        return results

    def _execute_rsync(self, cmd: List[str], operation_name: str) -> Dict[str, Any]:
        """Execute rsync command with error handling and progress monitoring."""
        self.logger.info(f"Starting {operation_name}")
        self.logger.debug(f"Rsync command: {' '.join(cmd)}")

        start_time = time.time()

        try:
            # Execute rsync command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            stdout_lines = []
            stderr_lines = []

            # Read output in real-time
            while True:
                stdout_line = process.stdout.readline()
                stderr_line = process.stderr.readline()

                if stdout_line:
                    stdout_lines.append(stdout_line.rstrip())
                    # Log progress information
                    if 'to-chk=' in stdout_line or '%' in stdout_line:
                        self.logger.debug(f"Progress: {stdout_line.rstrip()}")

                if stderr_line:
                    stderr_lines.append(stderr_line.rstrip())
                    self.logger.warning(f"Rsync stderr: {stderr_line.rstrip()}")

                if process.poll() is not None:
                    break

            # Get remaining output
            remaining_stdout, remaining_stderr = process.communicate()
            if remaining_stdout:
                stdout_lines.extend(remaining_stdout.strip().split('\n'))
            if remaining_stderr:
                stderr_lines.extend(remaining_stderr.strip().split('\n'))

            duration = time.time() - start_time

            # Parse rsync output for statistics
            stats = self._parse_rsync_output(stdout_lines)

            result = {
                'success': process.returncode == 0,
                'returncode': process.returncode,
                'duration': duration,
                'operation': operation_name,
                'stats': stats,
                'stdout': '\n'.join(stdout_lines),
                'stderr': '\n'.join(stderr_lines)
            }

            if result['success']:
                self.logger.info(f"Completed {operation_name} in {duration:.1f}s")
                if stats.get('files_transferred', 0) > 0:
                    self.logger.info(f"Transferred {stats['files_transferred']} files, {stats.get('total_size', 'unknown')} bytes")
            else:
                self.logger.error(f"Failed {operation_name} (exit code {process.returncode})")
                if stderr_lines:
                    self.logger.error(f"Error output: {stderr_lines[-1]}")

            return result

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Exception during {operation_name}: {e}")
            return {
                'success': False,
                'returncode': -1,
                'duration': duration,
                'operation': operation_name,
                'stats': {},
                'stdout': '',
                'stderr': str(e)
            }

    def _parse_rsync_output(self, output_lines: List[str]) -> Dict[str, Any]:
        """Parse rsync output to extract statistics."""
        stats = {
            'files_transferred': 0,
            'files_skipped': 0,
            'total_size': 0,
            'speedup': 0.0
        }

        for line in output_lines:
            # Look for summary line like: "sent 1,234 bytes  received 5,678 bytes  2,345.67 bytes/sec"
            if 'sent' in line and 'received' in line and 'bytes/sec' in line:
                # Extract numbers from the line
                numbers = re.findall(r'[\d,]+', line)
                if len(numbers) >= 2:
                    try:
                        sent = int(numbers[0].replace(',', ''))
                        received = int(numbers[1].replace(',', ''))
                        stats['total_size'] = sent + received
                    except ValueError:
                        pass

            # Look for speedup line
            elif 'speedup is' in line:
                match = re.search(r'speedup is ([\d.]+)', line)
                if match:
                    try:
                        stats['speedup'] = float(match.group(1))
                    except ValueError:
                        pass

            # Count file operations
            elif line.startswith('>f') or line.startswith('<f'):
                stats['files_transferred'] += 1
            elif 'skipping' in line.lower():
                stats['files_skipped'] += 1

        return stats
