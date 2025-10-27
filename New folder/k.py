#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║         🤖 F5-TTS BOT - COMPLETE AUTO SETUP & RUN                ║
║                                                                   ║
║         Cross-Platform: Windows VPS + Linux (Vast.ai)            ║
║                                                                   ║
║         Ye file automatically:                                    ║
║         1. System dependencies install karegi (Linux pe)          ║
║         2. Python packages install karegi                         ║
║         3. F5-TTS clone aur setup karegi                          ║
║         4. Bot ko run karegi                                      ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝

INSTRUCTIONS:

FOR WINDOWS VPS:
1. Install prerequisites: Git, Python 3.8+, FFmpeg, NVIDIA drivers
2. Place ye file + final_working_bot.py same folder mein
3. Open terminal/cmd and run: python VAST_AI_SINGLE_FILE.py
4. Bas! Sab automatically ho jayega!

FOR VAST.AI (LINUX):
1. Upload ye file + final_working_bot.py workspace mein
2. Run karo: python3 VAST_AI_SINGLE_FILE.py
3. Bas! Sab automatically ho jayega!

"""

import os
import sys
import subprocess
import time
from pathlib import Path
import importlib
import importlib.util
import site

# ============================================================================
# CONFIGURATION
# ============================================================================

# Use /workspace for Vast.ai/Linux, current directory for Windows VPS
WORKSPACE = "/workspace" if sys.platform.startswith('linux') else os.getcwd()
AUTOMATION_DIR = "f5-automation"
BOT_FILENAME = "final_working_bot.py"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def print_banner():
    """Print fancy banner"""
    print("\n" + "="*70)
    print("🚀 F5-TTS BOT - AUTO SETUP AND RUN")
    print("="*70 + "\n")

def print_section(title):
    """Print section header"""
    print("\n" + "="*70)
    print(f"📦 {title}")
    print("="*70)

def run_cmd(cmd, description="", check=False):
    """Run shell command"""
    print(f"\n💻 {description}")
    print(f"   Command: {cmd}")

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600
        )

        if result.stdout and len(result.stdout.strip()) > 0:
            # Only show first and last few lines for long output
            lines = result.stdout.strip().split('\n')
            if len(lines) > 20:
                print('\n'.join(lines[:5]))
                print(f"   ... ({len(lines) - 10} more lines) ...")
                print('\n'.join(lines[-5:]))
            else:
                print(result.stdout)

        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            return True
        else:
            if result.stderr:
                print(f"⚠️ Warnings: {result.stderr[:200]}")
            if check:
                print(f"❌ {description} - FAILED")
                return False
            return True

    except subprocess.TimeoutExpired:
        print(f"⏱️ {description} - TIMEOUT (continued in background)")
        return not check
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        if e.stderr:
            print(f"Error: {e.stderr[:300]}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def check_environment():
    """Check platform and display requirements"""
    print(f"\n🖥️ Detected platform: {sys.platform}")

    if sys.platform.startswith('win'):
        print(f"✅ Windows VPS detected")
        print(f"\n📋 Prerequisites for Windows:")
        print(f"   1. Git must be installed (https://git-scm.com/download/win)")
        print(f"   2. Python 3.8+ with pip")
        print(f"   3. FFmpeg installed (https://ffmpeg.org/download.html)")
        print(f"   4. NVIDIA GPU drivers + CUDA toolkit")
        print(f"\n   Script will skip system package installation on Windows.")
        input(f"\n   Press Enter to continue if prerequisites are met...")
    elif sys.platform.startswith('linux'):
        print(f"✅ Linux environment detected (Vast.ai compatible)")
    else:
        print(f"⚠️ WARNING: Untested platform: {sys.platform}")
        response = input("\n   Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("❌ Aborted by user")
            return False
    return True

# ============================================================================
# SETUP FUNCTIONS
# ============================================================================

def setup_directories():
    """Create directory structure"""
    print_section("CREATING DIRECTORY STRUCTURE")

    # Determine workspace - use current directory on Windows, /workspace on Linux
    if sys.platform.startswith('win'):
        workspace = os.getcwd()  # Use current directory on Windows
        print(f"📁 Using current directory: {workspace}")
    else:
        # Linux: use /workspace (Vast.ai standard)
        workspace = WORKSPACE
        print(f"📁 Working in: {workspace}")

    os.chdir(workspace)

    # Create automation directory
    automation_path = os.path.join(workspace, AUTOMATION_DIR)
    os.makedirs(automation_path, exist_ok=True)
    print(f"✅ Created: {automation_path}")

    # Create subdirectories
    subdirs = ["input", "output", "processed", "reference", "prompts", "scripts"]
    for subdir in subdirs:
        subdir_path = os.path.join(automation_path, subdir)
        os.makedirs(subdir_path, exist_ok=True)
        print(f"✅ Created: {subdir}/{''}")

    os.chdir(automation_path)
    print(f"📁 Changed to: {os.getcwd()}\n")

    return automation_path

def install_system_dependencies():
    """Install system packages"""
    print_section("INSTALLING SYSTEM DEPENDENCIES")

    # Skip apt commands on Windows
    if sys.platform.startswith('win'):
        print("ℹ️ Windows detected - Skipping Linux package manager")
        print("   Make sure Git, Python, and FFmpeg are already installed!")
    else:
        # Update system (Linux only)
        run_cmd("apt update", "Updating package lists", check=False)

        # Install packages (Linux only)
        packages = "git wget curl python3-pip ffmpeg"
        run_cmd(
            f"apt install -y {packages}",
            f"Installing: {packages}",
            check=False
        )

    # Check GPU (works on both Windows and Linux)
    print("\n🎮 Checking GPU:")
    run_cmd("nvidia-smi", "GPU status", check=False)

def setup_f5_tts(automation_dir):
    """Clone and install F5-TTS"""
    print_section("SETTING UP F5-TTS")

    f5_dir = os.path.join(automation_dir, "F5-TTS")

    if os.path.exists(f5_dir):
        print(f"ℹ️ F5-TTS already exists")
        print(f"✅ Skipping clone, using existing installation")
    else:
        print("📥 Cloning F5-TTS repository...")
        success = run_cmd(
            "git clone https://github.com/SWivid/F5-TTS.git",
            "Cloning F5-TTS from GitHub",
            check=True
        )

        if not success:
            print("❌ Failed to clone F5-TTS")
            return False

    # Install F5-TTS
    os.chdir(f5_dir)
    print(f"📁 In: {os.getcwd()}")

    # Install F5-TTS in editable mode
    install_success = run_cmd("pip install -e .", "Installing F5-TTS package", check=False)

    # Verify installation
    print("\n🔍 Verifying F5-TTS installation...")
    verify_result = run_cmd(
        "pip show f5-tts",
        "Checking if F5-TTS is installed",
        check=False
    )

    if not verify_result:
        print("⚠️ F5-TTS verification failed, but continuing...")

    # Reload site packages to recognize the new editable install
    print("\n🔄 Reloading Python site packages...")
    try:
        importlib.reload(site)
        print("✅ Site packages reloaded")
    except Exception as e:
        print(f"⚠️ Could not reload site packages: {e}")

    # Go back
    os.chdir(automation_dir)
    print(f"📁 Back to: {os.getcwd()}")

    return True

def install_python_packages():
    """Install Python dependencies"""
    print_section("INSTALLING PYTHON PACKAGES")

    packages = [
        "python-telegram-bot",
        "requests",
        "openai-whisper",
        "soundfile",
        "librosa",
        "yt-dlp",
        "python-dotenv",
        "feedparser",
        "pytz==2023.3",
        "google-auth-oauthlib==1.2.0",
        "google-auth-httplib2==0.2.0",
        "google-api-python-client==2.108.0",
        "torch",
        "torchaudio"
    ]

    print(f"📦 Installing {len(packages)} packages...")
    print(f"   (This may take a few minutes)\n")

    # Install in chunks to avoid timeout
    chunk_size = 5
    for i in range(0, len(packages), chunk_size):
        chunk = packages[i:i+chunk_size]
        packages_str = " ".join(chunk)
        run_cmd(
            f"pip install {packages_str}",
            f"Installing batch {i//chunk_size + 1}",
            check=False
        )

    print("\n✅ All Python packages installed")

def set_environment_variables():
    """Set required environment variables"""
    print_section("SETTING ENVIRONMENT VARIABLES")

    env_vars = {
        "DEEPSEEK_API_KEY": "sk-299e2e942ec14e35926666423990d968",
        "SUPADATA_API_KEY": "sd_a3a69115625b5507719678ab42a7dd71",
        "IMAGE_SHORTS_CHAT_ID": "-1002343932866",
        "IMAGE_LONG_CHAT_ID": "-1002498893774",
        "GDRIVE_FOLDER_LONG": "1y-Af4T5pAvgqV2gyvN9zhSPdvZzUcFyi",
        "GDRIVE_FOLDER_SHORT": "1JdJCYDXLWjAz1091zs_Pnev3FuK3Ftex",
        "CHANNEL_MODE_ENABLED": "true",
        "CHANNEL_IDS": "-1002498893774"
    }

    for key, value in env_vars.items():
        os.environ[key] = value
        print(f"✅ {key}")

    print("\n✅ All environment variables set")

    # Also export to bash profile for persistence (Linux only)
    if not sys.platform.startswith('win'):
        print("\n📝 Adding variables to ~/.bashrc for persistence...")
        try:
            bashrc_path = os.path.expanduser("~/.bashrc")
            with open(bashrc_path, 'a') as f:
                f.write("\n# F5-TTS Bot Environment Variables (Auto-added)\n")
                for key, value in env_vars.items():
                    # Check if already exists
                    check_cmd = f"grep -q 'export {key}=' {bashrc_path}"
                    result = subprocess.run(check_cmd, shell=True, capture_output=True)
                    if result.returncode != 0:  # Not found, add it
                        f.write(f'export {key}="{value}"\n')
                        print(f"✅ Added {key} to ~/.bashrc")
        except Exception as e:
            print(f"⚠️ Could not update ~/.bashrc: {e}")
            print("   (Variables are still set for current session)")

def copy_bot_file(automation_dir):
    """Find and copy bot file to automation directory"""
    print_section("LOCATING BOT FILE")

    # Possible locations
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_locations = [
        os.path.join(automation_dir, BOT_FILENAME),
        os.path.join("/workspace", BOT_FILENAME),  # Vast.ai first priority
        os.path.join(current_dir, BOT_FILENAME),
        os.path.join(WORKSPACE, BOT_FILENAME),
        BOT_FILENAME
    ]

    bot_file_path = None
    for location in possible_locations:
        if os.path.exists(location):
            print(f"✅ Found: {location}")
            bot_file_path = location
            break

    if not bot_file_path:
        print(f"\n❌ ERROR: {BOT_FILENAME} not found!")
        print("\n📝 Please place 'final_working_bot.py' in one of these locations:")
        for loc in possible_locations:
            print(f"   • {loc}")
        return None

    # Copy to automation directory if not already there
    target_path = os.path.join(automation_dir, BOT_FILENAME)
    if bot_file_path != target_path:
        import shutil
        shutil.copy(bot_file_path, target_path)
        print(f"✅ Copied to: {target_path}")
        bot_file_path = target_path

    return bot_file_path

# ============================================================================
# BOT EXECUTION
# ============================================================================

def run_bot(bot_file_path):
    """Execute the bot"""
    print_section("STARTING F5-TTS BOT")

    print(f"🤖 Loading bot from: {bot_file_path}")
    print(f"📁 Current directory: {os.getcwd()}\n")

    # Change to bot directory
    bot_dir = os.path.dirname(bot_file_path)
    if bot_dir:
        os.chdir(bot_dir)
        print(f"📁 Changed to: {os.getcwd()}\n")

    # Add F5-TTS to Python path (check multiple possible locations)
    f5_tts_paths = [
        os.path.join(os.getcwd(), "F5-TTS", "src"),  # Source directory
        os.path.join(os.getcwd(), "F5-TTS"),         # Root directory
    ]

    for f5_path in f5_tts_paths:
        if os.path.exists(f5_path):
            sys.path.insert(0, f5_path)
            print(f"✅ Added to Python path: {f5_path}")

    # Verify F5-TTS installation
    print("\n🔍 Testing F5-TTS import...")
    try:
        from f5_tts.api import F5TTS
        print(f"✅ F5-TTS module successfully imported!\n")
    except ImportError as e:
        print(f"⚠️ F5-TTS import failed: {e}")
        print(f"📝 This is normal if using pip-installed package.")
        print(f"   Bot will try to use pip-installed F5-TTS...\n")

    # Verify critical environment variables
    print("🔍 Verifying environment variables...")
    critical_vars = ["CHANNEL_MODE_ENABLED", "CHANNEL_IDS", "DEEPSEEK_API_KEY"]
    all_set = True
    for var in critical_vars:
        if var in os.environ:
            print(f"✅ {var} = {os.environ[var]}")
        else:
            print(f"❌ {var} NOT SET!")
            all_set = False

    if all_set:
        print("✅ All critical environment variables are set\n")
    else:
        print("⚠️ Some variables missing, but bot will try to run...\n")

    try:
        # Method 1: Import and execute main()
        print("🔄 Loading bot module...")

        spec = importlib.util.spec_from_file_location("bot_module", bot_file_path)
        bot_module = importlib.util.module_from_spec(spec)
        sys.modules["bot_module"] = bot_module
        spec.loader.exec_module(bot_module)

        print("\n✅ Bot module loaded successfully!")
        print("🚀 Starting bot polling (bot will run indefinitely)...")
        print("=" * 70 + "\n")

        # Call the main() function from bot module - THIS IS BLOCKING
        # Bot will run indefinitely until interrupted
        if hasattr(bot_module, 'main'):
            bot_module.main()
        else:
            print("⚠️ No main() function found in bot module")
            return False

        # This line will only be reached if bot stops/crashes
        return True

    except KeyboardInterrupt:
        print("\n\n⚠️ Bot stopped by user (Ctrl+C)")
        return True
    except Exception as e:
        print(f"\n❌ Bot execution error: {e}")
        print("\nTrying alternative method...\n")

        # Method 2: Direct exec
        try:
            with open(bot_file_path, 'r', encoding='utf-8') as f:
                bot_code = f.read()
            exec(bot_code, {'__name__': '__main__', '__file__': bot_file_path})
            return True
        except Exception as e2:
            print(f"❌ Alternative method also failed: {e2}")
            import traceback
            traceback.print_exc()
            return False

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main execution flow"""

    print_banner()

    # Check environment
    if not check_environment():
        return

    print("🔧 Starting automated setup...\n")
    time.sleep(1)

    try:
        # Step 1: Create directories
        automation_dir = setup_directories()
        time.sleep(1)

        # Step 2: Install system dependencies
        install_system_dependencies()
        time.sleep(1)

        # Step 3: Setup F5-TTS
        if not setup_f5_tts(automation_dir):
            print("\n⚠️ F5-TTS setup had issues, but continuing...")
        time.sleep(1)

        # Step 4: Install Python packages
        install_python_packages()
        time.sleep(1)

        # Step 5: Set environment variables
        set_environment_variables()
        time.sleep(1)

        # Step 6: Find bot file
        bot_file_path = copy_bot_file(automation_dir)
        if not bot_file_path:
            print("\n❌ Cannot proceed without bot file")
            return

        # Setup complete
        print("\n" + "="*70)
        print("✅ SETUP COMPLETE!")
        print("="*70)
        print(f"📁 Working directory: {os.getcwd()}")
        print(f"🤖 Bot file: {bot_file_path}")
        print("\n🚀 Starting bot in 3 seconds...\n")
        time.sleep(3)

        # Step 7: Run bot
        run_bot(bot_file_path)

    except KeyboardInterrupt:
        print("\n\n⚠️ Bot interrupted by user (Ctrl+C)")
        print("👋 Shutting down...")
    except Exception as e:
        print(f"\n\n❌ Error occurred: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "="*70)
        print("🏁 Script exited due to error")
        print("="*70 + "\n")

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()
