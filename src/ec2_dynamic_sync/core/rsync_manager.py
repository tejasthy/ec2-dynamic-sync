"""
Rsync Operations Manager for EC2 Dynamic Sync.

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
import re
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from .models import SyncConfig, SyncOptions, SyncResult, SyncStats, DirectoryMapping, ConflictResolution
from .exceptions import SyncError, SSHConnectionError
from .ssh_manager import SSHManager


class RsyncManager:
    """Manages rsync operations for file synchronization."""
    
    def __init__(self, sync_config: SyncConfig, ssh_manager: SSHManager):
        """Initialize rsync manager with configuration.
        
        Args:
            sync_config: Sync configuration object
            ssh_manager: SSH manager instance
        """
        self.config = sync_config
        self.ssh_manager = ssh_manager
        self.logger = logging.getLogger(__name__)
        
        # Build base rsync command options
        self.base_rsync_options = self._build_base_options()
    
    def _build_base_options(self) -> List[str]:
        """Build base rsync options from configuration."""
        options = ['rsync']
        
        # Basic flags
        if self.config.sync_options.archive:
            options.append('-a')
        if self.config.sync_options.verbose:
            options.append('-v')
        if self.config.sync_options.compress:
            options.append('-z')
        if self.config.sync_options.progress:
            options.append('--progress')
        if self.config.sync_options.partial:
            options.append('--partial')
        if self.config.sync_options.delete:
            options.append('--delete')
        
        # Bandwidth limit
        if self.config.sync_options.bandwidth_limit:
            options.extend(['--bwlimit', str(self.config.sync_options.bandwidth_limit)])
        
        # Exclude patterns
        for pattern in self.config.sync_options.exclude_patterns:
            options.extend(['--exclude', pattern])
        
        # Include patterns
        for pattern in self.config.sync_options.include_patterns:
            options.extend(['--include', pattern])
        
        # Additional options
        if self.config.sync_options.checksum:
            options.append('--checksum')
        if self.config.sync_options.update:
            options.append('--update')
        if self.config.sync_options.ignore_existing:
            options.append('--ignore-existing')
        
        # SSH configuration
        ssh_cmd = self.ssh_manager.build_rsync_ssh_command()
        options.extend(['-e', ssh_cmd])
        
        return options
    
    def _expand_path(self, path: str) -> str:
        """Expand user home directory and environment variables in path."""
        return os.path.expanduser(os.path.expandvars(path))
    
    def _parse_rsync_output(self, output: str) -> SyncStats:
        """Parse rsync output to extract statistics."""
        stats = SyncStats()
        
        # Parse file transfer information
        file_pattern = r'(\d+) files transferred'
        match = re.search(file_pattern, output)
        if match:
            stats.files_transferred = int(match.group(1))
        
        # Parse bytes transferred
        bytes_pattern = r'sent (\d+) bytes\s+received (\d+) bytes'
        match = re.search(bytes_pattern, output)
        if match:
            stats.bytes_sent = int(match.group(1))
            stats.bytes_received = int(match.group(2))
            stats.total_bytes = stats.bytes_sent + stats.bytes_received
        
        # Parse transfer rate
        rate_pattern = r'(\d+(?:\.\d+)?)\s+bytes/sec'
        match = re.search(rate_pattern, output)
        if match:
            stats.transfer_rate = float(match.group(1))
        
        # Parse speedup
        speedup_pattern = r'total size is (\d+)\s+speedup is (\d+(?:\.\d+)?)'
        match = re.search(speedup_pattern, output)
        if match:
            stats.total_size = int(match.group(1))
            stats.speedup = float(match.group(2))
        
        return stats
    
    def _run_rsync_command(self, cmd: List[str], timeout: int = 3600) -> SyncResult:
        """Run rsync command and return results."""
        start_time = time.time()
        
        try:
            self.logger.debug(f"Running rsync command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            duration = time.time() - start_time
            
            # Parse output for statistics
            stats = self._parse_rsync_output(result.stdout + result.stderr)
            stats.duration = duration
            
            return SyncResult(
                success=result.returncode == 0,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                stats=stats,
                command=' '.join(cmd)
            )
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            self.logger.error(f"Rsync command timed out after {timeout}s")
            
            return SyncResult(
                success=False,
                returncode=-1,
                stdout='',
                stderr=f'Command timed out after {timeout}s',
                stats=SyncStats(duration=duration),
                command=' '.join(cmd)
            )
            
        except FileNotFoundError:
            self.logger.error("rsync command not found. Please install rsync.")
            
            return SyncResult(
                success=False,
                returncode=-1,
                stdout='',
                stderr='rsync command not found',
                stats=SyncStats(),
                command=' '.join(cmd)
            )
            
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Rsync command failed: {e}")
            
            return SyncResult(
                success=False,
                returncode=-1,
                stdout='',
                stderr=str(e),
                stats=SyncStats(duration=duration),
                command=' '.join(cmd)
            )
    
    def sync_directory(self, mapping: DirectoryMapping, host: str, 
                      direction: str = 'bidirectional', dry_run: bool = False) -> Dict[str, Any]:
        """Sync a single directory mapping."""
        if not mapping.enabled:
            return {
                'success': True,
                'skipped': True,
                'reason': 'Directory mapping is disabled'
            }
        
        local_path = self._expand_path(mapping.local_path)
        remote_path = mapping.remote_path
        user_host = f"{self.ssh_manager.config.user}@{host}"
        
        results = {
            'mapping_name': mapping.name,
            'local_path': local_path,
            'remote_path': remote_path,
            'direction': direction,
            'dry_run': dry_run,
            'success': True,
            'overall_success': True
        }
        
        try:
            # Ensure local directory exists
            if not os.path.exists(local_path):
                if direction in ['local_to_remote', 'bidirectional']:
                    self.logger.info(f"Creating local directory: {local_path}")
                    os.makedirs(local_path, exist_ok=True)
                else:
                    self.logger.warning(f"Local directory does not exist: {local_path}")
            
            # Ensure remote directory exists
            if not self.ssh_manager.check_remote_directory(host, remote_path):
                if direction in ['remote_to_local', 'bidirectional']:
                    self.logger.info(f"Creating remote directory: {remote_path}")
                    if not self.ssh_manager.create_remote_directory(host, remote_path):
                        raise SyncError(f"Failed to create remote directory: {remote_path}")
                else:
                    self.logger.warning(f"Remote directory does not exist: {remote_path}")
            
            # Perform sync based on direction
            if direction == 'local_to_remote':
                results['local_to_remote'] = self._sync_local_to_remote(
                    local_path, f"{user_host}:{remote_path}", dry_run
                )
                results['success'] = results['local_to_remote']['success']
                
            elif direction == 'remote_to_local':
                results['remote_to_local'] = self._sync_remote_to_local(
                    f"{user_host}:{remote_path}", local_path, dry_run
                )
                results['success'] = results['remote_to_local']['success']
                
            elif direction == 'bidirectional':
                # Handle bidirectional sync with conflict resolution
                results.update(self._sync_bidirectional(
                    local_path, f"{user_host}:{remote_path}", dry_run
                ))
                results['success'] = results.get('overall_success', False)
            
            else:
                raise SyncError(f"Invalid sync direction: {direction}")
            
            results['overall_success'] = results['success']
            
        except Exception as e:
            self.logger.error(f"Sync failed for {mapping.name}: {e}")
            results.update({
                'success': False,
                'overall_success': False,
                'error': str(e)
            })
        
        return results
    
    def _sync_local_to_remote(self, local_path: str, remote_path: str, dry_run: bool) -> Dict[str, Any]:
        """Sync from local to remote."""
        cmd = self.base_rsync_options.copy()
        
        if dry_run:
            cmd.append('--dry-run')
        
        # Ensure trailing slash for directory sync
        if not local_path.endswith('/'):
            local_path += '/'
        
        cmd.extend([local_path, remote_path])
        
        result = self._run_rsync_command(cmd)
        
        return {
            'success': result.success,
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'stats': result.stats.dict(),
            'command': result.command
        }
    
    def _sync_remote_to_local(self, remote_path: str, local_path: str, dry_run: bool) -> Dict[str, Any]:
        """Sync from remote to local."""
        cmd = self.base_rsync_options.copy()
        
        if dry_run:
            cmd.append('--dry-run')
        
        # Ensure trailing slash for directory sync
        if not remote_path.endswith('/'):
            remote_path += '/'
        
        cmd.extend([remote_path, local_path])
        
        result = self._run_rsync_command(cmd)
        
        return {
            'success': result.success,
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'stats': result.stats.dict(),
            'command': result.command
        }
    
    def _sync_bidirectional(self, local_path: str, remote_path: str, dry_run: bool) -> Dict[str, Any]:
        """Perform bidirectional sync with conflict resolution."""
        results = {
            'local_to_remote': None,
            'remote_to_local': None,
            'overall_success': False
        }
        
        # Determine sync order based on conflict resolution strategy
        if self.config.conflict_resolution == ConflictResolution.LOCAL:
            # Local takes precedence - sync local to remote only
            results['local_to_remote'] = self._sync_local_to_remote(local_path, remote_path, dry_run)
            results['overall_success'] = results['local_to_remote']['success']
            
        elif self.config.conflict_resolution == ConflictResolution.REMOTE:
            # Remote takes precedence - sync remote to local only
            results['remote_to_local'] = self._sync_remote_to_local(remote_path, local_path, dry_run)
            results['overall_success'] = results['remote_to_local']['success']
            
        elif self.config.conflict_resolution == ConflictResolution.NEWER:
            # Sync both directions, newer files win
            # First sync remote to local with --update flag
            cmd_r2l = self.base_rsync_options.copy()
            if dry_run:
                cmd_r2l.append('--dry-run')
            cmd_r2l.append('--update')
            
            remote_path_slash = remote_path if remote_path.endswith('/') else remote_path + '/'
            cmd_r2l.extend([remote_path_slash, local_path])
            
            result_r2l = self._run_rsync_command(cmd_r2l)
            results['remote_to_local'] = {
                'success': result_r2l.success,
                'returncode': result_r2l.returncode,
                'stdout': result_r2l.stdout,
                'stderr': result_r2l.stderr,
                'stats': result_r2l.stats.dict(),
                'command': result_r2l.command
            }
            
            # Then sync local to remote with --update flag
            cmd_l2r = self.base_rsync_options.copy()
            if dry_run:
                cmd_l2r.append('--dry-run')
            cmd_l2r.append('--update')
            
            local_path_slash = local_path if local_path.endswith('/') else local_path + '/'
            cmd_l2r.extend([local_path_slash, remote_path])
            
            result_l2r = self._run_rsync_command(cmd_l2r)
            results['local_to_remote'] = {
                'success': result_l2r.success,
                'returncode': result_l2r.returncode,
                'stdout': result_l2r.stdout,
                'stderr': result_l2r.stderr,
                'stats': result_l2r.stats.dict(),
                'command': result_l2r.command
            }
            
            results['overall_success'] = (
                results['remote_to_local']['success'] and 
                results['local_to_remote']['success']
            )
            
        else:
            # Manual conflict resolution - report conflicts but don't sync
            results['error'] = "Manual conflict resolution not implemented in dry-run mode"
            results['overall_success'] = False
        
        return results
