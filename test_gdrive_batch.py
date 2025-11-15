#!/usr/bin/env python3
"""
Quick test script - sets env var and runs bot
"""
import os

# Set the Google Drive channels folder ID
os.environ['GDRIVE_FOLDER_LONG'] = '1WIw3oq6qQmmxHCGZdL4mg1ZKbPdvRVKf'

# Import and run the bot
import subprocess
subprocess.run(['python', 'final_working_bot.py'])
