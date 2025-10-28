# Vast.ai One-Click Setup Instructions

## 🚀 Quick Start (Easiest Method)

### Step 1: Upload Script to Vast.ai

1. Open your local copy of `vastai_auto_setup.py`
2. Upload it to Vast.ai instance (via Jupyter, SCP, or file upload)
3. Place it anywhere (e.g., `/workspace/`)

### Step 2: Run Script

```bash
cd /workspace
python3 vastai_auto_setup.py
```

That's it! The script will:
- ✅ Clone/update Git repository from https://github.com/aman4091/kk.git
- ✅ Setup ALL environment variables permanently in `~/.bashrc`
- ✅ Check dependencies
- ✅ Start the bot automatically

---

## 📋 What the Script Does

### 1. Git Clone/Pull
```
If /workspace/kk exists:
  → git pull (update)
Else:
  → git clone (fresh install)
```

### 2. Environment Variables
```
Adds to ~/.bashrc:
  export BOT_TOKEN='...'
  export DEEPSEEK_API_KEY='...'
  export SUPADATA_API_KEY='...'
  ... (all 12 variables)
```

**Permanent:** Available in all future terminal sessions!

### 3. Run Bot
```
cd /workspace/kk
python3 k.py
```

---

## 🔧 Manual Method (If Script Fails)

If the automatic script has issues, run these commands manually:

```bash
# 1. Clone repo
cd /workspace
git clone https://github.com/aman4091/kk.git
cd kk

# 2. Setup environment
bash setup_env_persistent.sh  # You'll need to create this from template

# 3. Run bot
python3 k.py
```

---

## 🔄 Updating Bot

### If Using Auto Script:
```bash
python3 vastai_auto_setup.py
```
Script will automatically `git pull` latest changes!

### Manual Update:
```bash
cd /workspace/kk
git pull
python3 k.py
```

---

## 🛑 Stopping the Bot

```bash
# Method 1: Ctrl+C in terminal
Press Ctrl+C

# Method 2: Kill process
pkill -f "python3 k.py"

# Method 3: Find and kill
ps aux | grep python3
kill <PID>
```

---

## 🔐 Security Notes

### ⚠️ IMPORTANT:

1. **`vastai_auto_setup.py` contains API KEYS**
   - Never commit to Git
   - Already in `.gitignore`
   - Upload manually to Vast.ai only

2. **Keep this file safe:**
   - Backup locally
   - Don't share publicly
   - Rotate keys if exposed

3. **Files with credentials (DO NOT PUSH):**
   - `vastai_auto_setup.py` ← Main script with keys
   - `setup_env_persistent.sh` ← Bash version with keys
   - `vastai_export_commands.txt` ← Export commands

4. **Safe to push (templates):**
   - `setup_env_persistent_TEMPLATE.sh` ✅

---

## 🐛 Troubleshooting

### Script fails at git clone:
```bash
# Delete old directory and retry
rm -rf /workspace/kk
python3 vastai_auto_setup.py
```

### Environment variables not working:
```bash
# Check if they're set
echo $BOT_TOKEN

# If empty, source bashrc
source ~/.bashrc

# Verify again
echo $BOT_TOKEN
```

### Bot won't start:
```bash
# Check if k.py exists
ls -la /workspace/kk/k.py

# Run manually
cd /workspace/kk
python3 k.py
```

### Dependencies missing:
```bash
cd /workspace/kk
python3 auto_setup_and_run_bot.py  # Alternative launcher
```

---

## 📂 File Structure After Setup

```
/workspace/
├── vastai_auto_setup.py          ← Upload this manually
└── kk/                             ← Created by script
    ├── k.py                        ← Main bot script
    ├── final_working_bot.py        ← Bot implementation
    ├── supabase_client.py          ← Database client
    ├── youtube_processor.py        ← YouTube integration
    ├── transcribe_helper.py        ← Transcript fetcher
    └── ... (other files)

~/.bashrc                           ← Environment variables added here
```

---

## ⚡ Advanced: Auto-Start on Boot

To make bot start automatically when Vast.ai instance starts:

```bash
# Add to ~/.bashrc (end of file)
echo "cd /workspace/kk && python3 k.py &" >> ~/.bashrc
```

**Warning:** Bot will start in background on every terminal open!

---

## 💡 Tips

1. **First time setup:** Use auto script - easiest!
2. **Regular usage:** Just restart bot with `python3 k.py`
3. **Updates:** Run auto script again - it will git pull
4. **Clean install:** Delete `/workspace/kk` and run script

---

## 📞 Support

- Check logs in Vast.ai terminal
- GitHub Issues: https://github.com/aman4091/kk/issues
- Jupyter terminal for debugging

---

## ✅ Quick Checklist

Before running script:
- [ ] Vast.ai instance is running
- [ ] `vastai_auto_setup.py` uploaded to Vast.ai
- [ ] API keys in script are correct
- [ ] Network access available

After running script:
- [ ] Git clone successful (check `/workspace/kk/`)
- [ ] Environment variables set (`echo $BOT_TOKEN`)
- [ ] Bot started without errors
- [ ] Telegram bot responding
