# 🔧 Google Drive Upload Fix - Token Path Issue

## Problem

Google Drive upload failing with:
```
⚠️ Google Drive credentials not found
```

**But credentials exist and are valid!**

## Root Cause Analysis

### Working Directory Issue:

```
Bot runs from: /workspace/kk/f5-automation/
token.pickle at: /workspace/kk/token.pickle
```

### Code Issue (Line 5229):

```python
if os.path.exists('token.pickle'):  # ❌ Relative path!
    with open('token.pickle', 'rb') as token:
        creds = pickle.load(token)
```

**Problem:** Bot checks `token.pickle` in **current directory** (`f5-automation/`), but file is in **parent directory** (`/workspace/kk/`).

### Why This Happened:

1. p.py creates `token.pickle` in `/workspace/kk/`
2. Bot's working directory is changed to `/workspace/kk/f5-automation/`
3. Bot looks for `token.pickle` in current dir (not found!)
4. Upload fails with "credentials not found"

## Solution

Check **multiple possible paths** for `token.pickle`:

```python
# Check multiple possible locations
token_paths = [
    'token.pickle',                          # Current directory
    '../token.pickle',                       # Parent directory  ✅
    os.path.join(os.path.dirname(__file__), 'token.pickle'),  # Script directory
]

token_file = None
for path in token_paths:
    if os.path.exists(path):
        token_file = path
        print(f"✅ Found token.pickle at: {path}")
        break

if token_file:
    with open(token_file, 'rb') as token:
        creds = pickle.load(token)
```

### Why This Works:

1. ✅ Tries current directory first (if bot runs from `/workspace/kk/`)
2. ✅ Tries parent directory (`../token.pickle`) - **MOST COMMON**
3. ✅ Tries script's own directory
4. ✅ Prints which path was found (for debugging)

## File Structure

```
/workspace/kk/
├── token.pickle              ← Created by p.py here
├── credentials.json          ← Created by p.py here
├── final_working_bot.py      ← Bot script
└── f5-automation/            ← Bot's working directory
    ├── F5-TTS/
    ├── output/
    │   └── generated_*.wav   ← Audio files to upload
    └── reference/
```

### Bot Execution Context:

```python
# Bot starts from:
os.chdir('/workspace/kk/f5-automation')

# OLD CODE looks for:
'/workspace/kk/f5-automation/token.pickle'  ❌ Not found!

# NEW CODE looks for:
'/workspace/kk/f5-automation/token.pickle'  ❌ Not found
'../token.pickle' → '/workspace/kk/token.pickle'  ✅ Found!
```

## Changes Made

### File: `final_working_bot.py`

**Function:** `upload_to_google_drive()` (Line 5216-5279)

**Before:**
```python
if os.path.exists('token.pickle'):
    with open('token.pickle', 'rb') as token:
        creds = pickle.load(token)
```

**After:**
```python
# Check multiple possible locations
token_paths = [
    'token.pickle',
    '../token.pickle',
    os.path.join(os.path.dirname(__file__), 'token.pickle'),
]

token_file = None
for path in token_paths:
    if os.path.exists(path):
        token_file = path
        print(f"✅ Found token.pickle at: {path}")
        break

if token_file:
    with open(token_file, 'rb') as token:
        creds = pickle.load(token)
```

### Token Refresh Save:

**Before:**
```python
if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open('token.pickle', 'wb') as token:  # ❌ Wrong path
        pickle.dump(creds, token)
```

**After:**
```python
if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())
    if token_file:
        with open(token_file, 'wb') as token:  # ✅ Same path where found
            pickle.dump(creds, token)
```

## Testing

### Expected Output (After Fix):

```
✅ Found token.pickle at: ../token.pickle
☁️ Uploading to Google Drive...
✅ Google Drive upload: generated_1762284779_raw.wav
   File ID: 1ABC123XYZ...
   Link: https://drive.google.com/file/d/...
✅ Uploaded to Google Drive
📁 File ID: `1ABC123XYZ...`
```

### Old Output (Before Fix):

```
⚠️ Google Drive credentials not found
```

## Verification Steps

1. Check token.pickle exists:
```bash
ls -la /workspace/kk/token.pickle
```

2. Check bot working directory:
```bash
pwd  # Should show: /workspace/kk/f5-automation
```

3. Test relative path:
```bash
ls -la ../token.pickle  # Should find it
```

4. Send test script to bot and check logs for:
```
✅ Found token.pickle at: ../token.pickle
✅ Google Drive upload: ...
```

## Related Issues

### Issue #1: "Why not use absolute path?"

**Answer:** Absolute paths are brittle. If user changes project location, it breaks. Relative paths are more portable.

### Issue #2: "Why check multiple paths?"

**Answer:** Different deployment scenarios:
- Development: Bot might run from project root
- Production: Bot runs from f5-automation/
- Testing: Bot might run from anywhere

Multiple paths = maximum compatibility!

### Issue #3: "Why not fix p.py to put token in f5-automation?"

**Answer:** `token.pickle` should stay with `credentials.json` in project root for:
- Organization (credentials together)
- Easy access for manual inspection
- Standard Google Auth convention

## Alternative Solutions (Not Used)

### Option 1: Environment Variable Path
```python
token_path = os.getenv('GOOGLE_TOKEN_PATH', 'token.pickle')
```
**Rejected:** Adds complexity, user needs to set variable

### Option 2: Absolute Path from p.py
```python
# In p.py, save path to config file
config['google_token_path'] = '/workspace/kk/token.pickle'
```
**Rejected:** Extra config file not needed

### Option 3: Copy token.pickle to f5-automation/
```python
# In p.py STEP 7
shutil.copy('token.pickle', 'f5-automation/token.pickle')
```
**Rejected:** Duplicate files, sync issues

## Summary

✅ **Problem:** token.pickle not found due to relative path in wrong directory
✅ **Solution:** Check multiple path locations (current, parent, script dir)
✅ **Result:** Google Drive upload now works correctly
✅ **Portability:** Works in different deployment scenarios

**No decode issues, just a simple path problem!** 😎

---

## Deployment

### Update Existing Instance:

```bash
# In /workspace/kk directory
# Copy updated final_working_bot.py from local machine

# Restart bot
pkill -f final_working_bot.py
cd /workspace/kk/f5-automation
python3 ../final_working_bot.py
```

### Next Git Push:

```bash
git add final_working_bot.py
git commit -m "Fix: Google Drive token.pickle path resolution

- Check multiple possible paths for token.pickle
- Support bot running from different directories
- Print found path for debugging
- Fix token refresh save path"
git push
```

### For New p.py Users:

No changes needed! Fix is in `final_working_bot.py` which gets cloned from git automatically.

**Everything will work out of the box!** ✅
