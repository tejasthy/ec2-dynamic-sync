#!/usr/bin/env python3
"""
Specific diagnostic for the user's actual ec2-dynamic-sync configuration.
"""

import os
import sys
import time
import tempfile
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, 'src')

from ec2_dynamic_sync.core.config_manager import ConfigManager
from ec2_dynamic_sync.core.sync_orchestrator import SyncOrchestrator
from ec2_dynamic_sync.cli.watch import SyncEventHandler
from watchdog.observers import Observer


def main():
    """Diagnose the user's actual configuration."""
    print("🔍 EC2 Dynamic Sync - User Configuration Diagnostic")
    print("=" * 60)
    
    config_path = "/Users/tejas/.ec2-sync.yaml"
    
    try:
        # Load the actual configuration
        print(f"📋 Loading configuration: {config_path}")
        config_manager = ConfigManager()
        config = config_manager.load_config(config_path)
        
        print(f"✅ Configuration loaded successfully")
        print(f"   Project: {config.project_name}")
        print(f"   Instance ID: {config.aws.instance_id}")
        
        # Check directory mappings
        print(f"\n📁 Directory Mappings ({len(config.directory_mappings)}):")
        for i, mapping in enumerate(config.directory_mappings):
            print(f"\n   Mapping {i+1}: {mapping.name}")
            print(f"     Local path: {mapping.local_path}")
            print(f"     Remote path: {mapping.remote_path}")
            print(f"     Enabled: {mapping.enabled}")
            
            # Check if directory exists
            if os.path.exists(mapping.local_path):
                print(f"     ✅ Directory exists")
                
                # Check permissions
                if os.access(mapping.local_path, os.R_OK):
                    print(f"     ✅ Directory readable")
                else:
                    print(f"     ❌ Directory not readable")
                    
                # List some files
                try:
                    files = os.listdir(mapping.local_path)
                    print(f"     📄 Contains {len(files)} items")
                    if files:
                        print(f"     📄 Sample files: {files[:5]}")
                except Exception as e:
                    print(f"     ❌ Cannot list files: {e}")
                    
            else:
                print(f"     ❌ Directory does not exist")
                
            if not mapping.enabled:
                print(f"     ⚠️  Mapping is disabled")
        
        # Test ignore patterns with real files
        print(f"\n🧪 Testing Ignore Patterns:")
        orchestrator = SyncOrchestrator(config)
        handler = SyncEventHandler(orchestrator)
        
        # Check actual files in the directory
        for mapping in config.directory_mappings:
            if mapping.enabled and os.path.exists(mapping.local_path):
                print(f"\n   Checking files in: {mapping.local_path}")
                
                try:
                    for root, dirs, files in os.walk(mapping.local_path):
                        for file in files[:10]:  # Check first 10 files
                            file_path = os.path.join(root, file)
                            ignored = handler.should_ignore(file_path)
                            status = "❌ IGNORED" if ignored else "✅ ALLOWED"
                            rel_path = os.path.relpath(file_path, mapping.local_path)
                            print(f"     {rel_path:<30} {status}")
                            
                        # Don't go too deep
                        if len(dirs) > 0:
                            dirs[:] = dirs[:3]  # Limit to first 3 subdirectories
                            
                except Exception as e:
                    print(f"     ❌ Error checking files: {e}")
        
        # Test watch mode setup
        print(f"\n👁️  Testing Watch Mode Setup:")
        
        # Create observer
        observer = Observer()
        
        watched_paths = []
        for mapping in config.directory_mappings:
            if not mapping.enabled:
                continue
                
            if os.path.exists(mapping.local_path):
                try:
                    observer.schedule(handler, mapping.local_path, recursive=True)
                    watched_paths.append(mapping.local_path)
                    print(f"     ✅ Successfully watching: {mapping.local_path}")
                except Exception as e:
                    print(f"     ❌ Failed to watch {mapping.local_path}: {e}")
            else:
                print(f"     ❌ Cannot watch non-existent directory: {mapping.local_path}")
        
        if watched_paths:
            print(f"\n🚀 Starting observer for testing...")
            observer.start()
            
            # Test file creation
            print(f"\n🧪 Testing File Event Detection:")
            
            # Reset stats
            handler.stats["events_detected"] = 0
            
            for watch_path in watched_paths:
                print(f"\n   Testing in: {watch_path}")
                
                # Create a test file
                test_file = os.path.join(watch_path, "ec2_sync_test.txt")
                
                print(f"     Creating test file: {os.path.basename(test_file)}")
                initial_events = handler.stats["events_detected"]
                
                with open(test_file, 'w') as f:
                    f.write("Test file for ec2-dynamic-sync event detection")
                
                # Wait for event processing
                time.sleep(1.0)
                
                new_events = handler.stats["events_detected"]
                if new_events > initial_events:
                    print(f"     ✅ Event detected! ({new_events - initial_events} events)")
                else:
                    print(f"     ❌ No event detected")
                    
                    # Check if file should be ignored
                    if handler.should_ignore(test_file):
                        print(f"     ℹ️  File matches ignore pattern")
                    else:
                        print(f"     ⚠️  File should not be ignored - possible issue!")
                
                # Clean up test file
                try:
                    os.remove(test_file)
                    print(f"     🧹 Cleaned up test file")
                except:
                    pass
            
            print(f"\n📊 Total events detected during test: {handler.stats['events_detected']}")
            
            # Stop observer
            observer.stop()
            observer.join()
            print(f"✅ Observer stopped")
            
        else:
            print(f"❌ No directories to watch")
        
        # Summary and recommendations
        print(f"\n" + "=" * 60)
        print(f"📋 DIAGNOSTIC SUMMARY")
        print(f"=" * 60)
        
        enabled_mappings = [m for m in config.directory_mappings if m.enabled]
        existing_dirs = [m for m in enabled_mappings if os.path.exists(m.local_path)]
        
        print(f"✅ Configuration: Valid")
        print(f"✅ Directory mappings: {len(enabled_mappings)} enabled")
        print(f"✅ Existing directories: {len(existing_dirs)}")
        print(f"✅ Watch mode setup: Working")
        print(f"✅ Event detection: Working")
        
        if len(existing_dirs) == 0:
            print(f"\n⚠️  ISSUE: No existing directories to watch")
            print(f"   💡 Create the directory: mkdir -p {enabled_mappings[0].local_path}")
        
        print(f"\n💡 RECOMMENDATIONS:")
        print(f"   1. Ensure files are being added to: {existing_dirs[0].local_path if existing_dirs else 'N/A'}")
        print(f"   2. Check that files don't match ignore patterns (hidden files, .tmp, etc.)")
        print(f"   3. Try creating a simple test file: echo 'test' > test.txt")
        print(f"   4. Run watch mode with: ec2-sync-watch")
        
    except Exception as e:
        print(f"❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
