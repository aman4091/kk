# GitHub Actions Secrets Setup

## Automatic Setup via GitHub CLI

```bash
# Install GitHub CLI if not installed
# Windows: winget install GitHub.cli
# Mac: brew install gh
# Linux: sudo apt install gh

# Login to GitHub
gh auth login

# Set secrets (run from project directory)
gh secret set MONITOR_BOT_TOKEN --body "8406974132:AAFE1FBfu27ds6hXGb0jNxWLtl5a04UqvHI"
gh secret set MONITOR_CHAT_ID --body "447705580"
gh secret set SUPABASE_URL --body "https://zrczbdkighpnzenjdsbi.supabase.co"
gh secret set SUPABASE_ANON_KEY --body "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpyY3piZGtpZ2hwbnplbmpkc2JpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1OTA0NTgsImV4cCI6MjA3NzE2NjQ1OH0.mA34gm1gqu2EP1TAE8La7sQpZmOOuVqWXSE0dAvtWdo"
gh secret set DAILY_VIDEO_PARENT_FOLDER --body "1ZKnCa-7ieNt3bLhI6f6mCZBmyAP0-dnF"

echo "✅ All secrets set!"
```

## Manual Setup (via Web UI)

1. Go to: https://github.com/aman4091/kk/settings/secrets/actions
2. Click "New repository secret"
3. Add these secrets:

### MONITOR_BOT_TOKEN
```
8406974132:AAFE1FBfu27ds6hXGb0jNxWLtl5a04UqvHI
```

### MONITOR_CHAT_ID
```
447705580
```

### SUPABASE_URL
```
https://zrczbdkighpnzenjdsbi.supabase.co
```

### SUPABASE_ANON_KEY
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpyY3piZGtpZ2hwbnplbmpkc2JpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1OTA0NTgsImV4cCI6MjA3NzE2NjQ1OH0.mA34gm1gqu2EP1TAE8La7sQpZmOOuVqWXSE0dAvtWdo
```

### DAILY_VIDEO_PARENT_FOLDER
```
1ZKnCa-7ieNt3bLhI6f6mCZBmyAP0-dnF
```

## Verify Secrets

```bash
gh secret list
```

Should show:
```
MONITOR_BOT_TOKEN
MONITOR_CHAT_ID
SUPABASE_URL
SUPABASE_ANON_KEY
DAILY_VIDEO_PARENT_FOLDER
```

## Test Workflow

```bash
# Trigger manual run
gh workflow run monitor.yml

# Check status
gh run list --workflow=monitor.yml
```

Done! 🎉
