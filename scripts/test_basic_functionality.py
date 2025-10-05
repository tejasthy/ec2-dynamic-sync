#!/usr/bin/env python3
"""
Basic functionality test for EC2 Dynamic Sync.

This script tests the core functionality without requiring AWS credentials
or actual EC2 instances.
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        from ec2_dynamic_sync.core import (
            ConfigManager, SyncOrchestrator, BidirectionalSyncDaemon,
            EnhancedRsyncManager, ExcludePatternManager
        )
        from ec2_dynamic_sync.cli import setup, doctor, watch, daemon
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_cli_help():
    """Test that CLI commands show help."""
    print("Testing CLI help commands...")
    
    commands = [
        'ec2-sync --help',
        'ec2-sync-setup --help', 
        'ec2-sync-doctor --help',
        'ec2-sync-watch --help',
        'ec2-sync-daemon --help'
    ]
    
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd.split(), 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0:
                print(f"✅ {cmd}")
            else:
                print(f"❌ {cmd} failed with code {result.returncode}")
                return False
        except Exception as e:
            print(f"❌ {cmd} failed: {e}")
            return False
    
    return True

def test_config_creation():
    """Test configuration creation and validation."""
    print("Testing configuration creation...")
    
    try:
        from ec2_dynamic_sync.core.models import SyncConfig, DirectoryMapping
        
        # Create temporary SSH key file
        temp_dir = tempfile.mkdtemp()
        key_file = os.path.join(temp_dir, 'test-key.pem')
        with open(key_file, 'w') as f:
            f.write('-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n')
        os.chmod(key_file, 0o600)
        
        # Create test configuration
        config = SyncConfig(
            project_name='test-project',
            project_description='Test project',
            aws={
                'instance_name': 'test-instance',
                'region': 'us-east-1',
                'profile': 'default',
                'auto_start_instance': True
            },
            ssh={
                'user': 'ubuntu',
                'key_file': key_file,
                'port': 22,
                'connect_timeout': 10
            },
            directory_mappings=[
                DirectoryMapping(
                    name='test-mapping',
                    local_path=temp_dir,
                    remote_path='~/remote',
                    enabled=True
                )
            ],
            sync_options={
                'archive': True,
                'verbose': False,
                'compress': True,
                'delete': False,
                'progress': True,
                'bandwidth_limit': '0'
            },
            conflict_resolution='newer'
        )
        
        print("✅ Configuration creation successful")
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration creation failed: {e}")
        return False

def test_exclude_patterns():
    """Test exclude pattern functionality."""
    print("Testing exclude patterns...")
    
    try:
        from ec2_dynamic_sync.core.enhanced_rsync import ExcludePatternManager
        
        temp_dir = tempfile.mkdtemp()
        
        # Create .ec2syncignore file
        ignore_file = os.path.join(temp_dir, '.ec2syncignore')
        with open(ignore_file, 'w') as f:
            f.write('*.log\ntemp/\n')
        
        manager = ExcludePatternManager(temp_dir)
        
        # Test exclusions
        assert manager.should_exclude('test.log') is True
        assert manager.should_exclude('temp/file.txt') is True
        assert manager.should_exclude('normal.txt') is False
        
        print("✅ Exclude patterns working correctly")
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
        
        return True
        
    except Exception as e:
        print(f"❌ Exclude patterns test failed: {e}")
        return False

def test_doctor_functionality():
    """Test doctor diagnostic functionality."""
    print("Testing doctor functionality...")
    
    try:
        from ec2_dynamic_sync.cli.doctor import (
            get_system_info, check_python_dependencies, 
            check_system_commands
        )
        
        # Test system info
        system_info = get_system_info()
        assert 'platform' in system_info
        assert 'python_version' in system_info
        
        # Test dependency checking
        deps = check_python_dependencies()
        assert isinstance(deps, dict)
        
        # Test command checking
        commands = check_system_commands()
        assert isinstance(commands, dict)
        
        print("✅ Doctor functionality working")
        return True
        
    except Exception as e:
        print(f"❌ Doctor functionality test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 50)
    print("EC2 Dynamic Sync - Basic Functionality Test")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_cli_help,
        test_config_creation,
        test_exclude_patterns,
        test_doctor_functionality
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            print()
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            print()
    
    print("=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All basic functionality tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
