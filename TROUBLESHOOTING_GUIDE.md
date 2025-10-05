# EC2 Dynamic Sync Watch Mode Troubleshooting Guide

## 🔍 Issue: No Events Triggered When Files Are Uploaded

Based on comprehensive diagnostic testing, here are the potential causes and solutions for file events not being detected in watch mode.

## ✅ Verified Working Components

The diagnostic tests confirm that the following components are working correctly:

1. **Configuration Loading**: ✅ Working
2. **Directory Watching Setup**: ✅ Working  
3. **File System Event Detection**: ✅ Working
4. **Path Matching Logic**: ✅ Working
5. **Ignore Pattern Logic**: ✅ Working (with bug fix applied)

## 🔧 Bug Fix Applied

**Fixed Issue**: `AttributeError: 'str' object has no attribute 'name'` in `should_ignore()` method.

**Location**: `src/ec2_dynamic_sync/cli/watch.py`, line 107

**Fix**: Changed `part.name.startswith(".")` to `part.startswith(".")` because `path_obj.parts` returns strings, not Path objects.

## 🧪 Diagnostic Results

### Configuration Analysis
- **Config File**: `/Users/tejas/.ec2-sync.yaml` ✅ Valid
- **Project**: `lightsheet` 
- **Directory Mapping**: `/Users/tejas/LightSheetFiles` ✅ Exists and readable
- **Files Present**: 8 items including `.czi` files (✅ Allowed by ignore patterns)

### Event Detection Test
- **Test File Creation**: ✅ 2 events detected
- **File Types**: `.czi` files are ✅ ALLOWED (not ignored)
- **Hidden Files**: `.DS_Store` is ❌ IGNORED (expected)

## 🔍 Potential Root Causes

### 1. **File Upload Method Issues**

Some file upload methods may not trigger filesystem events:

**Problematic Methods:**
- Network file transfers (SMB, NFS mounts)
- Some cloud sync services (Dropbox, OneDrive)
- `rsync` with certain flags
- `scp` or `sftp` transfers
- Atomic file moves from temp locations

**Working Methods:**
- Direct file creation (`touch`, `echo >`)
- Copy/paste in Finder
- Drag and drop to Finder
- Most text editors saving files
- `cp` command

### 2. **Timing Issues**

**Min Interval Enforcement**: Watch mode has a minimum interval of 30 seconds between syncs by default.

**Solution**: Check if files are being added faster than the min interval allows.

### 3. **File Size or Type Issues**

**Large Files**: Very large files (like the `.czi` files in your directory) might:
- Take time to fully write to disk
- Be detected but fail during sync due to size
- Trigger events but get filtered out during processing

### 4. **Path Resolution Issues**

**Symlinks**: If the watched directory contains symlinks, events might not be detected properly.

**Case Sensitivity**: macOS is case-insensitive but case-preserving, which might cause issues.

## 🛠️ Troubleshooting Steps

### Step 1: Use Live Monitor
Run the live monitoring script to see real-time events:

```bash
cd /Users/tejas/GitProjects/ec2-dynamic-sync
python live_monitor.py
```

Then add files to `/Users/tejas/LightSheetFiles/` and observe the output.

### Step 2: Test Different File Upload Methods

Try these methods and see which ones trigger events:

```bash
# Method 1: Direct creation
echo "test content" > /Users/tejas/LightSheetFiles/test1.txt

# Method 2: Copy existing file
cp /Users/tejas/LightSheetFiles/B06.czi /Users/tejas/LightSheetFiles/test_copy.czi

# Method 3: Touch command
touch /Users/tejas/LightSheetFiles/test2.txt

# Method 4: Create and move
echo "test" > /tmp/test3.txt && mv /tmp/test3.txt /Users/tejas/LightSheetFiles/
```

### Step 3: Check Watch Mode Settings

Verify your watch mode parameters:

```bash
# Default settings
ec2-sync-watch

# Reduced delays for testing
ec2-sync-watch --delay 2 --min-interval 5 --batch-size 1

# No UI mode for better debugging
ec2-sync-watch --no-ui
```

### Step 4: Manual Sync Test

Test if sync works manually:

```bash
# Test dry run
ec2-sync sync --dry-run

# Test actual sync
ec2-sync sync
```

### Step 5: Check System Resources

```bash
# Check if the process is running
ps aux | grep ec2-sync

# Check system file descriptor limits
ulimit -n

# Check disk space
df -h /Users/tejas/LightSheetFiles/
```

## 🎯 Specific Recommendations

### For Large .czi Files

1. **Test with small files first** to isolate the issue
2. **Check if events are detected but sync fails** due to file size
3. **Monitor network bandwidth** during sync operations
4. **Consider using rsync options** for large files (resume, compression)

### For File Upload Workflows

1. **Avoid network mounts** for the watched directory
2. **Use local file operations** when possible
3. **Test the specific upload method** you're using
4. **Check if files are being moved atomically** from temp locations

### For Performance

1. **Reduce min-interval** for testing: `--min-interval 5`
2. **Reduce delay** for faster response: `--delay 1`
3. **Set batch-size to 1** for immediate sync: `--batch-size 1`

## 📋 Quick Diagnostic Commands

```bash
# 1. Run live monitor
python live_monitor.py

# 2. Test with simple file
echo "test" > /Users/tejas/LightSheetFiles/simple_test.txt

# 3. Check watch mode with verbose output
ec2-sync-watch --no-ui --delay 1 --min-interval 5

# 4. Manual sync test
ec2-sync sync --dry-run

# 5. Check configuration
ec2-sync status
```

## 🚨 Known Issues

1. **Fixed**: `should_ignore()` method bug causing crashes
2. **Limitation**: Directory events are ignored (only file events trigger sync)
3. **Limitation**: Hidden files (starting with `.`) are automatically ignored
4. **Limitation**: Minimum 30-second interval between syncs by default

## 💡 Next Steps

If events are still not detected after following this guide:

1. **Run the live monitor** and share the output
2. **Describe the exact file upload method** you're using
3. **Check if the issue is with event detection or sync execution**
4. **Test with different file types and sizes**
5. **Verify network connectivity to EC2 instance**
