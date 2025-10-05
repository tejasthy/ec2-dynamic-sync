#!/usr/bin/env python3
"""
Comprehensive diagnostic script for ec2-dynamic-sync watch mode file event detection issues.
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any

# Add the src directory to Python path
sys.path.insert(0, 'src')

from ec2_dynamic_sync.core.config_manager import ConfigManager
from ec2_dynamic_sync.core.sync_orchestrator import SyncOrchestrator
from ec2_dynamic_sync.cli.watch import SyncEventHandler
from watchdog.observers import Observer
from watchdog.events import FileSystemEvent


class WatchModeDiagnostic:
    """Diagnostic tool for watch mode issues."""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or "test_config.yaml"
        self.test_dir = None
        self.orchestrator = None
        self.handler = None
        self.observer = None
        
    def run_full_diagnostic(self):
        """Run complete diagnostic suite."""
        print("🔍 EC2 Dynamic Sync Watch Mode Diagnostic")
        print("=" * 50)
        
        # 1. Configuration Issues
        print("\n1️⃣ CHECKING CONFIGURATION ISSUES")
        self.check_configuration()
        
        # 2. File Ignore Patterns
        print("\n2️⃣ CHECKING FILE IGNORE PATTERNS")
        self.check_ignore_patterns()
        
        # 3. Directory Watching Setup
        print("\n3️⃣ CHECKING DIRECTORY WATCHING SETUP")
        self.check_directory_watching()
        
        # 4. File System Event Detection
        print("\n4️⃣ TESTING FILE SYSTEM EVENT DETECTION")
        self.test_event_detection()
        
        # 5. Path Matching Logic
        print("\n5️⃣ TESTING PATH MATCHING LOGIC")
        self.test_path_matching()
        
        print("\n" + "=" * 50)
        print("🎯 DIAGNOSTIC COMPLETE")
        
    def check_configuration(self):
        """Check configuration issues."""
        try:
            # Load configuration
            if not os.path.exists(self.config_path):
                print(f"❌ Configuration file not found: {self.config_path}")
                return False

            print(f"✅ Configuration file found: {self.config_path}")

            # Try to parse configuration with mocked validation
            try:
                config_manager = ConfigManager()
                config = config_manager.load_config(self.config_path)
                print(f"✅ Configuration loaded successfully")
            except Exception as config_error:
                print(f"⚠️  Configuration validation failed: {config_error}")
                print("   Attempting to load with minimal validation...")

                # Load raw YAML for analysis
                import yaml
                with open(self.config_path, 'r') as f:
                    raw_config = yaml.safe_load(f)

                # Create a mock config for testing
                from ec2_dynamic_sync.core.models import SyncConfig, AWSConfig, SSHConfig, DirectoryMapping
                from unittest.mock import patch

                # Mock file validation to bypass SSH key checks
                with patch('os.path.exists', return_value=True), \
                     patch('os.path.isfile', return_value=True), \
                     patch('os.access', return_value=True):

                    config = config_manager.load_config(self.config_path)
                    print(f"✅ Configuration loaded with mocked validation")

            print(f"   Project: {config.project_name}")
            print(f"   Directory mappings: {len(config.directory_mappings)}")

            # Check directory mappings
            for i, mapping in enumerate(config.directory_mappings):
                print(f"\n   Mapping {i+1}: {mapping.name}")
                print(f"     Local path: {mapping.local_path}")
                print(f"     Remote path: {mapping.remote_path}")
                print(f"     Enabled: {mapping.enabled}")

                # Test path expansion
                expanded_path = os.path.expanduser(mapping.local_path)
                print(f"     Expanded path: {expanded_path}")

                # Check if directory exists
                if os.path.exists(expanded_path):
                    print(f"     ✅ Directory exists")
                    # Check permissions
                    if os.access(expanded_path, os.R_OK):
                        print(f"     ✅ Directory readable")
                    else:
                        print(f"     ❌ Directory not readable")
                else:
                    print(f"     ❌ Directory does not exist")
                    print(f"     💡 Creating directory for testing...")
                    os.makedirs(expanded_path, exist_ok=True)

                if not mapping.enabled:
                    print(f"     ⚠️  Mapping is disabled")

            self.orchestrator = SyncOrchestrator(config)
            return True

        except Exception as e:
            print(f"❌ Configuration error: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def check_ignore_patterns(self):
        """Check file ignore patterns."""
        if not self.orchestrator:
            print("❌ Cannot check ignore patterns - orchestrator not initialized")
            return
            
        # Create handler to access ignore patterns
        handler = SyncEventHandler(self.orchestrator)
        
        print("📋 Ignore patterns:")
        for pattern in sorted(handler.ignore_patterns):
            print(f"   - {pattern}")
            
        # Test common file types
        test_files = [
            "test.txt",
            "test.py", 
            "test.js",
            "test.tmp",
            ".hidden_file",
            ".DS_Store",
            "test.pyc",
            "node_modules/package.json",
            ".git/config",
            "dist/bundle.js",
            "__pycache__/test.pyc"
        ]
        
        print("\n🧪 Testing file ignore logic:")
        for test_file in test_files:
            ignored = handler.should_ignore(test_file)
            status = "❌ IGNORED" if ignored else "✅ ALLOWED"
            print(f"   {test_file:<25} {status}")
            
    def check_directory_watching(self):
        """Check directory watching setup."""
        if not self.orchestrator:
            print("❌ Cannot check directory watching - orchestrator not initialized")
            return
            
        # Create test directory
        self.test_dir = tempfile.mkdtemp(prefix="ec2_sync_test_")
        print(f"📁 Created test directory: {self.test_dir}")
        
        # Update config to use test directory
        for mapping in self.orchestrator.config.directory_mappings:
            if mapping.enabled:
                mapping.local_path = self.test_dir
                break
                
        # Set up observer
        handler = SyncEventHandler(self.orchestrator)
        observer = Observer()
        
        try:
            # Watch test directory
            observer.schedule(handler, self.test_dir, recursive=True)
            observer.start()
            print(f"✅ Successfully started watching: {self.test_dir}")
            
            # Test directory permissions
            if os.access(self.test_dir, os.R_OK | os.W_OK):
                print(f"✅ Directory has read/write permissions")
            else:
                print(f"❌ Directory lacks proper permissions")
                
            self.handler = handler
            self.observer = observer
            return True
            
        except Exception as e:
            print(f"❌ Failed to start watching: {e}")
            return False
            
    def test_event_detection(self):
        """Test file system event detection."""
        if not self.test_dir or not self.handler:
            print("❌ Cannot test event detection - test setup incomplete")
            return
            
        print(f"🧪 Testing event detection in: {self.test_dir}")
        
        # Reset stats
        self.handler.stats["events_detected"] = 0
        
        test_cases = [
            ("simple_file.txt", "Simple text file"),
            ("test.py", "Python file"),
            ("data.json", "JSON file"),
            ("image.jpg", "Image file"),
            ("subdir/nested.txt", "File in subdirectory"),
            (".hidden.txt", "Hidden file (should be ignored)"),
            ("temp.tmp", "Temporary file (should be ignored)"),
        ]
        
        for filename, description in test_cases:
            print(f"\n   Testing: {description}")
            
            # Create file path
            file_path = os.path.join(self.test_dir, filename)
            
            # Create subdirectory if needed
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Record initial event count
            initial_events = self.handler.stats["events_detected"]
            
            # Create file
            with open(file_path, 'w') as f:
                f.write(f"Test content for {filename}")
                
            # Wait for event processing
            time.sleep(0.5)
            
            # Check if event was detected
            new_events = self.handler.stats["events_detected"]
            if new_events > initial_events:
                print(f"     ✅ Event detected ({new_events - initial_events} events)")
            else:
                print(f"     ❌ No event detected")
                
            # Check if file should be ignored
            if self.handler.should_ignore(file_path):
                print(f"     ℹ️  File matches ignore pattern (expected)")
                
        print(f"\n📊 Total events detected: {self.handler.stats['events_detected']}")
        
    def test_path_matching(self):
        """Test path matching logic."""
        if not self.test_dir or not self.handler:
            print("❌ Cannot test path matching - test setup incomplete")
            return
            
        print(f"🧪 Testing path matching logic")
        
        # Test files in different locations
        test_paths = [
            os.path.join(self.test_dir, "direct_file.txt"),
            os.path.join(self.test_dir, "subdir", "nested_file.txt"),
            "/tmp/outside_file.txt",  # Outside watched directory
        ]
        
        for test_path in test_paths:
            print(f"\n   Testing path: {test_path}")
            
            # Check if path matches any directory mapping
            matched = False
            for mapping in self.orchestrator.config.directory_mappings:
                if not mapping.enabled:
                    continue
                    
                local_path = os.path.expanduser(mapping.local_path)
                if test_path.startswith(local_path):
                    matched = True
                    print(f"     ✅ Matches mapping: {mapping.name}")
                    print(f"     Local path: {local_path}")
                    break
                    
            if not matched:
                print(f"     ❌ No matching directory mapping")
                
    def cleanup(self):
        """Clean up test resources."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            print(f"🧹 Cleaned up test directory: {self.test_dir}")


def main():
    """Main diagnostic function."""
    diagnostic = WatchModeDiagnostic()
    
    try:
        diagnostic.run_full_diagnostic()
    except KeyboardInterrupt:
        print("\n⚠️  Diagnostic interrupted by user")
    except Exception as e:
        print(f"\n❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        diagnostic.cleanup()


if __name__ == "__main__":
    main()
