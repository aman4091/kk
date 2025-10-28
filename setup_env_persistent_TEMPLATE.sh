#!/bin/bash

# Persistent Environment Variables Setup for Vast.ai - TEMPLATE
#
# INSTRUCTIONS:
# 1. Copy this file: cp setup_env_persistent_TEMPLATE.sh setup_env_persistent.sh
# 2. Edit setup_env_persistent.sh and replace YOUR_*_HERE with actual values
# 3. Run: bash setup_env_persistent.sh
# 4. After running, environment variables will be available in all future sessions

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
export BOT_TOKEN='YOUR_BOT_TOKEN_HERE'
export DEEPSEEK_API_KEY='YOUR_DEEPSEEK_KEY_HERE'
export SUPADATA_API_KEY='YOUR_SUPADATA_KEY_HERE'
export SUPABASE_URL='YOUR_SUPABASE_URL_HERE'
export SUPABASE_ANON_KEY='YOUR_SUPABASE_ANON_KEY_HERE'
export YOUTUBE_API_KEY='YOUR_YOUTUBE_API_KEY_HERE'
export CHAT_ID='YOUR_CHAT_ID_HERE'
export IMAGE_SHORTS_CHAT_ID='YOUR_SHORTS_CHAT_ID_HERE'
export IMAGE_LONG_CHAT_ID='YOUR_LONG_CHAT_ID_HERE'
export GDRIVE_FOLDER_LONG='YOUR_GDRIVE_FOLDER_LONG_ID_HERE'
export GDRIVE_FOLDER_SHORT='YOUR_GDRIVE_FOLDER_SHORT_ID_HERE'
export CHANNEL_IDS='YOUR_CHANNEL_IDS_HERE'
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
