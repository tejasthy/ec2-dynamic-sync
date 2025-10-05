#!/usr/bin/env python3
"""
Live monitoring script to debug file event detection in real-time.
"""

import os
import sys
import time
import signal
from datetime import datetime

# Add the src directory to Python path
sys.path.insert(0, 'src')

from ec2_dynamic_sync.core.config_manager import ConfigManager
from ec2_dynamic_sync.core.sync_orchestrator import SyncOrchestrator
from ec2_dynamic_sync.cli.watch import SyncEventHandler
from watchdog.observers import Observer
from watchdog.events import FileSystemEvent


class VerboseEventHandler(SyncEventHandler):
    """Extended event handler with verbose logging."""
    
    def on_any_event(self, event: FileSystemEvent):
        """Handle any file system event with detailed logging."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        print(f"\n[{timestamp}] 🔔 FILE SYSTEM EVENT:")
        print(f"  Event type: {event.event_type}")
        print(f"  Path: {event.src_path}")
        print(f"  Is directory: {event.is_directory}")
        
        if hasattr(event, 'dest_path'):
            print(f"  Destination: {event.dest_path}")
        
        # Check if should be ignored
        if not event.is_directory:
            ignored = self.should_ignore(event.src_path)
            print(f"  Should ignore: {ignored}")
            
            if ignored:
                print(f"  ❌ Event ignored - matches ignore pattern")
                return
            else:
                print(f"  ✅ Event allowed - processing...")
        else:
            print(f"  ❌ Event ignored - is directory")
            return
        
        # Check directory mapping
        matched_mapping = None
        for mapping in self.orchestrator.config.directory_mappings:
            if not mapping.enabled:
                continue
                
            local_path = os.path.expanduser(mapping.local_path)
            if event.src_path.startswith(local_path):
                matched_mapping = mapping
                break
        
        if matched_mapping:
            print(f"  ✅ Matches mapping: {matched_mapping.name}")
            print(f"  📁 Local path: {local_path}")
        else:
            print(f"  ❌ No matching directory mapping")
            return
        
        # Call parent method to handle the event
        super().on_any_event(event)
        
        print(f"  📊 Total events detected: {self.stats['events_detected']}")
        print(f"  📊 Pending changes: {sum(len(changes) for changes in self.pending_changes.values())}")


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print('\n\n🛑 Monitoring stopped by user')
    sys.exit(0)


def main():
    """Main monitoring function."""
    print("🔍 EC2 Dynamic Sync - Live File Event Monitor")
    print("=" * 60)
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    config_path = "/Users/tejas/.ec2-sync.yaml"
    
    try:
        # Load configuration
        print(f"📋 Loading configuration: {config_path}")
        config_manager = ConfigManager()
        config = config_manager.load_config(config_path)
        
        print(f"✅ Configuration loaded")
        print(f"   Project: {config.project_name}")
        
        # Show watched directories
        print(f"\n👁️  Watching directories:")
        for mapping in config.directory_mappings:
            if mapping.enabled and os.path.exists(mapping.local_path):
                print(f"   📁 {mapping.name}: {mapping.local_path}")
        
        # Create orchestrator and handler
        orchestrator = SyncOrchestrator(config)
        handler = VerboseEventHandler(orchestrator)
        
        # Create observer
        observer = Observer()
        
        # Set up watching
        watched_paths = []
        for mapping in config.directory_mappings:
            if not mapping.enabled:
                continue
                
            if os.path.exists(mapping.local_path):
                observer.schedule(handler, mapping.local_path, recursive=True)
                watched_paths.append(mapping.local_path)
                print(f"   ✅ Watching: {mapping.local_path}")
            else:
                print(f"   ❌ Directory not found: {mapping.local_path}")
        
        if not watched_paths:
            print("❌ No directories to watch!")
            return
        
        # Start monitoring
        observer.start()
        
        print(f"\n🚀 Live monitoring started!")
        print(f"📝 Add, modify, or delete files in the watched directories")
        print(f"🔍 All file system events will be shown below")
        print(f"⏹️  Press Ctrl+C to stop monitoring")
        print(f"\n" + "=" * 60)
        print(f"📊 LIVE EVENT LOG:")
        
        # Keep monitoring
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if 'observer' in locals():
            print(f"\n🛑 Stopping observer...")
            observer.stop()
            observer.join()
            print(f"✅ Observer stopped")
        
        if 'handler' in locals():
            print(f"\n📊 Final Statistics:")
            print(f"   Events detected: {handler.stats['events_detected']}")
            print(f"   Syncs triggered: {handler.stats['syncs_triggered']}")
            print(f"   Errors: {handler.stats['errors']}")


if __name__ == "__main__":
    main()
