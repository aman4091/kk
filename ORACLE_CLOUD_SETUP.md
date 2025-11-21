# Oracle Cloud Video Worker Setup Guide

## Prerequisites
- Oracle Cloud account (free tier works)
- SSH key pair generated
- Local video worker code ready

## Step 1: Create Oracle Cloud Instance

### 1.1 Login to Oracle Cloud
1. Go to https://cloud.oracle.com/
2. Login with your credentials
3. Navigate to **Compute > Instances**

### 1.2 Create VM Instance
1. Click **Create Instance**
2. **Name**: `video-worker-1`
3. **Compartment**: Select your compartment
4. **Image**:
   - Click "Change Image"
   - Select **Ubuntu 22.04** (recommended)
   - Click "Select Image"
5. **Shape**:
   - Click "Change Shape"
   - Select **VM.Standard.E2.1.Micro** (free tier)
   - OR **VM.Standard.A1.Flex** (ARM, 4 OCPUs + 24GB RAM free)
   - Click "Select Shape"
6. **Add SSH Keys**:
   - Upload your public key OR paste key text
   - Download private key if auto-generated
7. **Boot Volume**: Default (50GB)
8. Click **Create**

### 1.3 Note Public IP
- Once instance is running, note the **Public IP Address**
- Example: `140.238.xxx.xxx`

## Step 2: Configure Firewall (Security List)

### 2.1 Open Required Ports
1. Go to instance details
2. Click on **Subnet** name
3. Click on **Default Security List**
4. Click **Add Ingress Rules**
5. Add these rules:

**Rule 1: SSH**
- Source CIDR: `0.0.0.0/0`
- IP Protocol: `TCP`
- Destination Port: `22`
- Description: `SSH Access`

**Rule 2: Custom Port (if needed for monitoring)**
- Source CIDR: `0.0.0.0/0`
- IP Protocol: `TCP`
- Destination Port: `8080`
- Description: `Worker Monitoring`

6. Click **Add Ingress Rules**

## Step 3: Connect to Instance

### 3.1 SSH Connection
```bash
# From your local machine
ssh -i /path/to/private-key.pem ubuntu@YOUR_PUBLIC_IP

# Example
ssh -i oracle-key.pem ubuntu@140.238.123.45
```

### 3.2 First Login Setup
```bash
# Update system
sudo apt update
sudo apt upgrade -y

# Install basic tools
sudo apt install -y git curl wget htop
```

## Step 4: Install FFmpeg with Hardware Encoding Support

### 4.1 Check CPU Architecture
```bash
lscpu | grep Architecture
# x86_64 = Intel/AMD
# aarch64 = ARM (if using A1.Flex)
```

### 4.2 Install FFmpeg (x86_64)
```bash
# Add PPA for latest FFmpeg
sudo add-apt-repository ppa:savoury1/ffmpeg4 -y
sudo apt update

# Install FFmpeg with all codecs
sudo apt install -y ffmpeg

# Verify installation
ffmpeg -version
ffmpeg -encoders | grep h264
```

### 4.3 Install FFmpeg (ARM - aarch64)
```bash
# Install from Ubuntu repos (already optimized for ARM)
sudo apt install -y ffmpeg

# Verify
ffmpeg -version
```

### 4.4 Test Hardware Encoding
```bash
# Check available encoders
ffmpeg -encoders | grep h264

# You should see:
# - libx264 (software, always available)
# - h264_v4l2m2m (hardware on ARM)
# - h264_vaapi (Intel/AMD hardware)

# Test encode
ffmpeg -f lavfi -i testsrc=duration=10:size=1920x1080:rate=30 \
  -c:v libx264 -preset ultrafast test.mp4
```

## Step 5: Install Python and Dependencies

### 5.1 Install Python 3.11
```bash
# Install Python
sudo apt install -y python3 python3-pip python3-venv

# Check version
python3 --version
```

### 5.2 Clone Repository
```bash
# Create working directory
mkdir -p ~/video-worker
cd ~/video-worker

# Clone your repo (replace with your GitHub URL)
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git .

# OR upload files via SCP
# From local machine:
# scp -i oracle-key.pem local_video_worker.py ubuntu@IP:~/video-worker/
```

### 5.3 Install Python Dependencies
```bash
cd ~/video-worker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install supabase-py google-api-python-client google-auth-httplib2 \
            google-auth-oauthlib requests aiohttp python-telegram-bot pillow
```

## Step 6: Setup Google Drive Credentials

### 6.1 Upload token.pickle
```bash
# From local machine, upload token.pickle
scp -i oracle-key.pem /path/to/token.pickle ubuntu@IP:~/video-worker/
```

### 6.2 Verify Credentials
```bash
cd ~/video-worker
ls -la token.pickle
# Should show file with proper permissions
```

## Step 7: Configure Environment Variables

### 7.1 Create .env file
```bash
cd ~/video-worker
nano .env
```

### 7.2 Add Configuration
```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key

# Telegram Bot
TELEGRAM_BOT_TOKEN=your-bot-token

# Google Drive
GDRIVE_VIDEO_QUEUE_FOLDER=folder-id-here
GDRIVE_VIDEO_OUTPUT_FOLDER=folder-id-here

# Daily Video Organization
DAILY_VIDEO_PARENT_FOLDER=1ZKnCa-7ieNt3bLhI6f6mCZBmyAP0-dnF

# Worker Config
WORKER_ID=oracle-worker-1
MAX_CONCURRENT_JOBS=1

# FFmpeg Path (auto-detected, but can override)
FFMPEG_PATH=/usr/bin/ffmpeg
```

Save: `Ctrl+X`, then `Y`, then `Enter`

### 7.3 Load Environment
```bash
source .env
```

## Step 8: Setup Systemd Service (Auto-Start on Boot)

### 8.1 Create Service File
```bash
sudo nano /etc/systemd/system/video-worker.service
```

### 8.2 Add Service Configuration
```ini
[Unit]
Description=Video Worker Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/video-worker
Environment="PATH=/home/ubuntu/video-worker/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/ubuntu/video-worker/venv/bin/python local_video_worker.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Save: `Ctrl+X`, then `Y`, then `Enter`

### 8.3 Enable and Start Service
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (auto-start on boot)
sudo systemctl enable video-worker

# Start service
sudo systemctl start video-worker

# Check status
sudo systemctl status video-worker
```

### 8.4 View Logs
```bash
# Real-time logs
sudo journalctl -u video-worker -f

# Last 100 lines
sudo journalctl -u video-worker -n 100

# Today's logs
sudo journalctl -u video-worker --since today
```

## Step 9: Test Video Worker

### 9.1 Manual Test Run
```bash
cd ~/video-worker
source venv/bin/activate
python local_video_worker.py
```

### 9.2 Submit Test Job
- From Telegram bot, submit a script
- Worker should pick up the job
- Check logs for encoding process

### 9.3 Monitor Resources
```bash
# CPU/Memory usage
htop

# Disk usage
df -h

# Network usage
iftop
```

## Step 10: Optimization for Oracle Cloud

### 10.1 Increase Swap (if needed)
```bash
# Create 4GB swap file
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 10.2 FFmpeg Optimization for ARM (A1.Flex)
```bash
# Edit local_video_worker.py to use ARM-optimized settings
# Replace h264_nvenc with libx264 or h264_v4l2m2m
```

For ARM instances, modify encoding command:
```python
# In local_video_worker.py, around line with ffmpeg command
# Change from:
'-c:v', 'h264_nvenc',

# To (for ARM):
'-c:v', 'libx264',
'-preset', 'medium',
'-crf', '23',
```

### 10.3 Setup Monitoring
```bash
# Install monitoring tools
sudo apt install -y prometheus-node-exporter

# Check worker health endpoint (if implemented)
curl http://localhost:8080/health
```

## Step 11: Firewall Configuration (OS Level)

### 11.1 Configure UFW
```bash
# Enable firewall
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow monitoring (if needed)
sudo ufw allow 8080/tcp

# Check status
sudo ufw status
```

## Step 12: Auto-Update Script

### 12.1 Create Update Script
```bash
nano ~/video-worker/update.sh
```

```bash
#!/bin/bash
cd ~/video-worker
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart video-worker
```

```bash
chmod +x ~/video-worker/update.sh
```

### 12.2 Run Updates
```bash
cd ~/video-worker
./update.sh
```

## Troubleshooting

### Issue: Service won't start
```bash
# Check service status
sudo systemctl status video-worker

# Check logs
sudo journalctl -u video-worker -n 50

# Check permissions
ls -la ~/video-worker/
```

### Issue: FFmpeg not found
```bash
# Verify FFmpeg
which ffmpeg
ffmpeg -version

# Reinstall if needed
sudo apt install --reinstall ffmpeg
```

### Issue: Out of memory
```bash
# Check memory
free -h

# Add swap (see Step 10.1)

# Reduce concurrent jobs in .env
MAX_CONCURRENT_JOBS=1
```

### Issue: Can't connect to Supabase
```bash
# Test connection
curl https://your-project.supabase.co/rest/v1/

# Check .env file
cat .env | grep SUPABASE
```

### Issue: Google Drive authentication fails
```bash
# Check token.pickle
ls -la ~/video-worker/token.pickle

# Re-upload token.pickle
# From local machine:
scp -i oracle-key.pem token.pickle ubuntu@IP:~/video-worker/
```

## Monitoring & Maintenance

### Daily Checks
```bash
# Check service status
sudo systemctl status video-worker

# Check disk space
df -h

# Check recent logs
sudo journalctl -u video-worker --since "1 hour ago"
```

### Weekly Maintenance
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Update worker code
cd ~/video-worker && ./update.sh

# Clean old logs
sudo journalctl --vacuum-time=7d
```

### Performance Monitoring
```bash
# CPU usage by worker
top -p $(pgrep -f local_video_worker)

# Disk I/O
iostat -x 5

# Network bandwidth
iftop -i eth0
```

## Cost Optimization (Free Tier Limits)

**Oracle Cloud Free Tier:**
- 2 x AMD-based VMs (1/8 OCPU, 1GB RAM)
- 4 x ARM-based VMs (1 OCPU, 6GB RAM each)
- 200GB block storage total
- 10TB egress per month

**Recommended Setup:**
- Use **VM.Standard.A1.Flex** (ARM)
- 4 OCPUs + 24GB RAM (free forever)
- Best performance for video encoding
- Set max 4 OCPUs, 24GB RAM in shape config

## Security Best Practices

1. **Change SSH port** (optional):
```bash
sudo nano /etc/ssh/sshd_config
# Change Port 22 to Port 2222
sudo systemctl restart ssh
```

2. **Disable password authentication**:
```bash
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart ssh
```

3. **Setup fail2ban**:
```bash
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
```

4. **Regular backups**:
```bash
# Backup worker config
tar -czf worker-backup-$(date +%Y%m%d).tar.gz ~/video-worker/.env ~/video-worker/token.pickle
```

## Next Steps

1. ✅ Create Oracle Cloud instance
2. ✅ Install FFmpeg and Python
3. ✅ Upload worker code and credentials
4. ✅ Configure systemd service
5. ✅ Test video encoding
6. ✅ Monitor performance
7. 🔄 Setup auto-updates
8. 🔄 Configure monitoring alerts

---

**Support:**
- Oracle Cloud Docs: https://docs.oracle.com/en-us/iaas/
- FFmpeg Docs: https://ffmpeg.org/documentation.html
- Python Telegram Bot: https://python-telegram-bot.org/
