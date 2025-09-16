"""
Sync Orchestrator for EC2 Dynamic Sync.

This module coordinates all sync operations by managing AWS, SSH, and rsync
components to provide a unified interface for file synchronization.
"""

import logging
import time
from typing import Dict, Any, Optional, List

from .models import SyncConfig
from .aws_manager import AWSManager
from .ssh_manager import SSHManager
from .rsync_manager import RsyncManager
from .config_manager import ConfigManager
from .exceptions import EC2SyncError, AWSConnectionError, SSHConnectionError, SyncError


class SyncOrchestrator:
    """Orchestrates EC2 file synchronization operations."""
    
    def __init__(self, config_path: Optional[str] = None, profile: Optional[str] = None):
        """Initialize sync orchestrator.
        
        Args:
            config_path: Path to configuration file
            profile: Configuration profile to use
        """
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config(config_path, profile)
        
        # Initialize managers
        self.aws_manager = AWSManager(self.config.aws)
        self.ssh_manager = SSHManager(self.config.ssh)
        self.rsync_manager = RsyncManager(self.config, self.ssh_manager)
        
        # Cache for instance information
        self._instance_id = None
        self._current_host = None
    
    def get_instance_id(self) -> str:
        """Get EC2 instance ID, caching the result."""
        if self._instance_id is None:
            self._instance_id = self.aws_manager.get_instance_id()
        return self._instance_id
    
    def get_current_host(self) -> Optional[str]:
        """Get current host IP, ensuring instance is running."""
        instance_id = self.get_instance_id()
        
        # Try to get current IP
        host = self.aws_manager.ensure_instance_running(instance_id)
        
        if host:
            # Test SSH connectivity
            if self.ssh_manager.wait_for_ssh(host, max_wait=120):
                self._current_host = host
                return host
            else:
                self.logger.error(f"SSH connection failed to {host}")
                return None
        else:
            self.logger.error("Failed to get instance IP or start instance")
            return None
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get comprehensive sync status information."""
        status = {
            'timestamp': time.time(),
            'instance_id': None,
            'instance_state': None,
            'host': None,
            'ssh_connected': False,
            'directory_mappings': {}
        }
        
        try:
            # Get instance information
            instance_id = self.get_instance_id()
            status['instance_id'] = instance_id
            
            instance_info = self.aws_manager.get_instance_info(instance_id)
            if instance_info:
                status['instance_state'] = instance_info['state']
                status['host'] = instance_info.get('public_ip')
            
            # Test SSH connectivity if instance is running
            if status['instance_state'] == 'running' and status['host']:
                status['ssh_connected'] = self.ssh_manager.test_connection(status['host'])
            
            # Get directory mapping status
            for mapping in self.config.directory_mappings:
                mapping_status = {
                    'enabled': mapping.enabled,
                    'local': self._get_local_directory_info(mapping.local_path),
                    'remote': {}
                }
                
                # Get remote directory info if SSH is connected
                if status['ssh_connected']:
                    mapping_status['remote'] = self._get_remote_directory_info(
                        status['host'], mapping.remote_path
                    )
                else:
                    mapping_status['remote'] = {'error': 'SSH not connected'}
                
                status['directory_mappings'][mapping.name] = mapping_status
        
        except Exception as e:
            self.logger.error(f"Failed to get sync status: {e}")
            status['error'] = str(e)
        
        return status
    
    def _get_local_directory_info(self, path: str) -> Dict[str, Any]:
        """Get information about a local directory."""
        import os
        from pathlib import Path
        
        expanded_path = os.path.expanduser(path)
        
        info = {
            'path': expanded_path,
            'exists': os.path.exists(expanded_path),
            'file_count': 0,
            'size': 'Unknown'
        }
        
        if info['exists']:
            try:
                # Count files
                path_obj = Path(expanded_path)
                if path_obj.is_dir():
                    info['file_count'] = len(list(path_obj.rglob('*')))
                
                # Get size (simplified)
                import subprocess
                result = subprocess.run(
                    ['du', '-sh', expanded_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    info['size'] = result.stdout.split('\t')[0]
            except Exception as e:
                self.logger.debug(f"Failed to get local directory info: {e}")
        
        return info
    
    def _get_remote_directory_info(self, host: str, path: str) -> Dict[str, Any]:
        """Get information about a remote directory."""
        info = {
            'path': path,
            'exists': False,
            'file_count': 0,
            'size': 'Unknown'
        }
        
        try:
            # Check if directory exists
            info['exists'] = self.ssh_manager.check_remote_directory(host, path)
            
            if info['exists']:
                # Get file count
                file_count = self.ssh_manager.get_remote_file_count(host, path)
                if file_count is not None:
                    info['file_count'] = file_count
                
                # Get size
                size_info = self.ssh_manager.get_remote_disk_usage(host, path)
                if size_info:
                    info['size'] = size_info['size']
        
        except Exception as e:
            self.logger.debug(f"Failed to get remote directory info: {e}")
            info['error'] = str(e)
        
        return info
    
    def sync_all_directories(self, mode: str = 'bidirectional', dry_run: bool = False) -> Dict[str, Any]:
        """Sync all configured directory mappings.
        
        Args:
            mode: Sync mode ('bidirectional', 'local_to_remote', 'remote_to_local')
            dry_run: If True, show what would be synced without making changes
            
        Returns:
            Dictionary with sync results
        """
        start_time = time.time()
        
        results = {
            'mode': mode,
            'dry_run': dry_run,
            'start_time': start_time,
            'directories': {},
            'summary': {
                'total_dirs': len(self.config.directory_mappings),
                'successful_dirs': 0,
                'failed_dirs': 0,
                'skipped_dirs': 0
            },
            'overall_success': False
        }
        
        try:
            # Ensure we have a valid host connection
            host = self.get_current_host()
            if not host:
                raise SyncError("Failed to establish connection to EC2 instance")
            
            self.logger.info(f"Starting {mode} sync to {host} (dry_run={dry_run})")
            
            # Sync each directory mapping
            for mapping in self.config.directory_mappings:
                if not mapping.enabled:
                    results['directories'][mapping.name] = {
                        'success': True,
                        'skipped': True,
                        'reason': 'Directory mapping is disabled'
                    }
                    results['summary']['skipped_dirs'] += 1
                    continue
                
                try:
                    self.logger.info(f"Syncing directory: {mapping.name}")
                    
                    sync_result = self.rsync_manager.sync_directory(
                        mapping, host, mode, dry_run
                    )
                    
                    results['directories'][mapping.name] = sync_result
                    
                    if sync_result.get('success', False):
                        results['summary']['successful_dirs'] += 1
                    else:
                        results['summary']['failed_dirs'] += 1
                        
                except Exception as e:
                    self.logger.error(f"Failed to sync {mapping.name}: {e}")
                    results['directories'][mapping.name] = {
                        'success': False,
                        'error': str(e)
                    }
                    results['summary']['failed_dirs'] += 1
            
            # Calculate overall success
            results['overall_success'] = (
                results['summary']['failed_dirs'] == 0 and
                results['summary']['successful_dirs'] > 0
            )
            
        except Exception as e:
            self.logger.error(f"Sync operation failed: {e}")
            results['error'] = str(e)
            results['overall_success'] = False
        
        finally:
            end_time = time.time()
            results['end_time'] = end_time
            results['summary']['total_duration'] = end_time - start_time
        
        return results
    
    def test_connectivity(self) -> Dict[str, Any]:
        """Test all connectivity components."""
        results = {
            'aws_connection': False,
            'instance_found': False,
            'instance_running': False,
            'ssh_connection': False,
            'rsync_available': False,
            'overall_success': False
        }
        
        try:
            # Test AWS connection
            instance_id = self.get_instance_id()
            results['aws_connection'] = True
            results['instance_found'] = True
            
            # Check instance state
            instance_info = self.aws_manager.get_instance_info(instance_id)
            if instance_info and instance_info['state'] == 'running':
                results['instance_running'] = True
                host = instance_info.get('public_ip')
                
                if host:
                    # Test SSH connection
                    if self.ssh_manager.test_connection(host):
                        results['ssh_connection'] = True
                        
                        # Test rsync availability
                        if self.ssh_manager.check_remote_rsync(host):
                            results['rsync_available'] = True
            
            results['overall_success'] = all([
                results['aws_connection'],
                results['instance_found'],
                results['instance_running'],
                results['ssh_connection'],
                results['rsync_available']
            ])
            
        except Exception as e:
            self.logger.error(f"Connectivity test failed: {e}")
            results['error'] = str(e)
        
        return results
