#!/bin/bash

# Persistent Environment Variables Setup for Vast.ai
# Run this ONCE: bash setup_env_persistent.sh
# After running, environment variables will be available in all future sessions

echo "=========================================="
echo "Setting up persistent environment variables..."
echo "=========================================="

# Check if ~/.bashrc exists
if [ ! -f ~/.bashrc ]; then
    touch ~/.bashrc
    echo "Created ~/.bashrc"
fi

# Backup existing bashrc
cp ~/.bashrc ~/.bashrc.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ Backed up existing ~/.bashrc"

# Remove old bot environment variables if they exist
sed -i '/# Bot Environment Variables - START/,/# Bot Environment Variables - END/d' ~/.bashrc

# Add new environment variables
cat >> ~/.bashrc << 'EOF'

# Bot Environment Variables - START (Auto-generated)
export BOT_TOKEN='8274226808:AAH0NQWBf9DF-nZpbOSbl4SkcCkcp8HMmDY'
export DEEPSEEK_API_KEY='sk-299e2e942ec14e35926666423990d968'
export SUPADATA_API_KEY='sd_a3a69115625b5507719678ab42a7dd71'
export SUPABASE_URL='https://zrczbdkighpnzenjdsbi.supabase.co'
export SUPABASE_ANON_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpyY3piZGtpZ2hwbnplbmpkc2JpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1OTA0NTgsImV4cCI6MjA3NzE2NjQ1OH0.mA34gm1gqu2EP1TAE8La7sQpZmOOuVqWXSE0dAvtWdo'
export YOUTUBE_API_KEY='AIzaSyCFEQBb2_98ods5B28bDAqLhWRXpUivCS8'
export CHAT_ID='447705580'
export IMAGE_SHORTS_CHAT_ID='-1002343932866'
export IMAGE_LONG_CHAT_ID='-1002498893774'
export GDRIVE_FOLDER_LONG='1y-Af4T5pAvgqV2gyvN9zhSPdvZzUcFyi'
export GDRIVE_FOLDER_SHORT='1JdJCYDXLWjAz1091zs_Pnev3FuK3Ftex'
export CHANNEL_IDS='-1002498893774'
# Bot Environment Variables - END

EOF

echo ""
echo "✅ Environment variables added to ~/.bashrc"
echo ""

# Source the bashrc to apply changes immediately
source ~/.bashrc

echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Environment variables are now persistent!"
echo ""
echo "Test by running:"
echo "  echo \$BOT_TOKEN"
echo ""
echo "To use in new terminal sessions:"
echo "  source ~/.bashrc"
echo ""
echo "Or simply close and reopen terminal"
echo "=========================================="
