#!/usr/bin/env python3
"""
🤖 F5-TTS Bot - Auto Setup and Run (Single File)
================================================
Cross-Platform: Windows VPS + Linux (Vast.ai)

Ye file automatically:
1. System dependencies install karegi (Linux pe)
2. Python packages install karegi
3. F5-TTS clone aur setup karegi
4. Bot ko run karegi

Windows VPS: Install Git, Python, FFmpeg pehle, phir run karo!
Linux/Vast.ai: Seedha run karo!
"""

import os
import sys
import subprocess
import time
from pathlib import Path
import importlib
import site

# ============================================================================
# STEP 1: AUTO SETUP FUNCTION
# ============================================================================

def run_command(cmd, description="", check=True, shell=True):
    """Run a shell command with logging"""
    print(f"\n{'='*60}")
    print(f"🔧 {description}")
    print(f"💻 Command: {cmd}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("⚠️ Warnings:", result.stderr)
        print(f"✅ {description} - SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        print(f"Error: {e.stderr if e.stderr else str(e)}")
        if check:
            return False
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def setup_environment():
    """Setup complete environment from 1.txt requirements"""

    print("\n" + "="*70)
    print("🚀 F5-TTS BOT AUTO SETUP STARTING")
    print("="*70 + "\n")

    # Change to workspace directory
    # Use current directory on Windows, /workspace on Linux (Vast.ai)
    if sys.platform.startswith('win'):
        workspace = os.getcwd()
        print(f"📁 Windows detected - Using current directory: {workspace}")
    else:
        # Linux: Always use /workspace for Vast.ai compatibility
        workspace = "/workspace"
        print(f"📁 Linux detected - Using workspace: {workspace}")
        if not os.path.exists(workspace):
            print(f"⚠️ WARNING: /workspace not found, using current directory instead")
            workspace = os.getcwd()

    os.chdir(workspace)
    print(f"📁 Working directory: {os.getcwd()}")

    # ========================================================================
    # STEP 1: UPDATE SYSTEM
    # ========================================================================

    print("\n" + "🔄 STEP 1: SYSTEM UPDATE")

    # Skip apt commands on Windows
    if sys.platform.startswith('win'):
        print("ℹ️ Windows detected - Skipping Linux package manager")
        print("   Prerequisites must be installed manually:")
        print("   - Git (https://git-scm.com/download/win)")
        print("   - Python 3.8+ with pip")
        print("   - FFmpeg (https://ffmpeg.org/download.html)")
        print("   - NVIDIA GPU drivers + CUDA")
    else:
        run_command("apt update && apt upgrade -y", "System update", check=False)

    # Check NVIDIA GPU (works on both Windows and Linux)
    print("\n" + "🎮 CHECKING GPU")
    run_command("nvidia-smi", "GPU status check", check=False)

    # ========================================================================
    # STEP 2: INSTALL SYSTEM DEPENDENCIES
    # ========================================================================

    print("\n" + "📦 STEP 2: SYSTEM DEPENDENCIES")

    if not sys.platform.startswith('win'):
        # Linux only - install packages via apt
        run_command(
            "apt install -y git wget curl python3-pip ffmpeg",
            "Installing git, wget, curl, python3-pip, ffmpeg",
            check=False
        )
    else:
        print("ℹ️ Skipping apt installation on Windows")

    # ========================================================================
    # STEP 3: CREATE DIRECTORY STRUCTURE
    # ========================================================================

    print("\n" + "📂 STEP 3: CREATING DIRECTORIES")

    automation_dir = os.path.join(workspace, "f5-automation")
    os.makedirs(automation_dir, exist_ok=True)
    print(f"✅ Created: {automation_dir}")

    # Create subdirectories
    subdirs = ["input", "output", "processed", "reference", "prompts", "scripts"]
    for subdir in subdirs:
        subdir_path = os.path.join(automation_dir, subdir)
        os.makedirs(subdir_path, exist_ok=True)
        print(f"✅ Created: {subdir_path}")

    os.chdir(automation_dir)
    print(f"📁 Changed to: {os.getcwd()}")

    # ========================================================================
    # STEP 4: CLONE AND INSTALL F5-TTS
    # ========================================================================

    print("\n" + "🎵 STEP 4: F5-TTS SETUP")

    f5_dir = os.path.join(automation_dir, "F5-TTS")

    if os.path.exists(f5_dir):
        print(f"ℹ️ F5-TTS already exists at: {f5_dir}")
        print("⏭️ Skipping clone, using existing installation")
    else:
        print("📥 Cloning F5-TTS repository...")
        success = run_command(
            "git clone https://github.com/SWivid/F5-TTS.git",
            "Cloning F5-TTS from GitHub"
        )

        if not success:
            print("❌ Failed to clone F5-TTS. Exiting...")
            return False

    # Install F5-TTS in editable mode
    os.chdir(f5_dir)
    print(f"📁 Changed to: {os.getcwd()}")

    print("📦 Installing F5-TTS...")
    run_command("pip install -e .", "Installing F5-TTS package", check=False)

    # Verify installation
    print("\n🔍 Verifying F5-TTS installation...")
    run_command("pip show f5-tts", "Checking if F5-TTS is installed", check=False)

    # Reload site packages to recognize the new editable install
    print("\n🔄 Reloading Python site packages...")
    try:
        importlib.reload(site)
        print("✅ Site packages reloaded")
    except Exception as e:
        print(f"⚠️ Could not reload site packages: {e}")

    # Return to automation directory
    os.chdir(automation_dir)
    print(f"📁 Back to: {os.getcwd()}")

    # ========================================================================
    # STEP 5: INSTALL PYTHON DEPENDENCIES
    # ========================================================================

    print("\n" + "🐍 STEP 5: PYTHON PACKAGES")

    # CRITICAL: Downgrade PyTorch to 2.6.0 if needed (2.7.x breaks F5-TTS pipeline)
    print("🔍 Checking PyTorch version...")
    result = subprocess.run(
        "python3 -c 'import torch; print(torch.__version__)'",
        shell=True,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        current_version = result.stdout.strip()
        print(f"✅ Current PyTorch version: {current_version}")

        # Check if version needs reinstall (2.7+, or wrong CUDA version like cu124)
        needs_reinstall = False
        if current_version.startswith('2.7') or current_version.startswith('2.8'):
            print("⚠️ PyTorch 2.7+ detected - downgrading to 2.6.0 for F5-TTS compatibility...")
            needs_reinstall = True
        elif 'cu124' in current_version or 'cu121' in current_version or 'cu126' in current_version:
            print(f"⚠️ Wrong CUDA version detected ({current_version}) - reinstalling with cu118...")
            needs_reinstall = True
        elif not ('2.6.0' in current_version and 'cu118' in current_version):
            print(f"⚠️ Non-optimal PyTorch version - reinstalling 2.6.0+cu118...")
            needs_reinstall = True

        if needs_reinstall:
            run_command(
                "pip uninstall torch torchaudio torchvision -y && pip install torch==2.6.0+cu118 torchaudio==2.6.0+cu118 torchvision==0.21.0+cu118 --index-url https://download.pytorch.org/whl/cu118",
                "Reinstalling PyTorch 2.6.0+cu118",
                check=False
            )
        else:
            print("✅ PyTorch version is compatible")
    else:
        print("⚠️ PyTorch not found - installing 2.6.0...")
        run_command(
            "pip install torch==2.6.0+cu118 torchaudio==2.6.0+cu118 torchvision==0.21.0+cu118 --index-url https://download.pytorch.org/whl/cu118",
            "Installing PyTorch 2.6.0",
            check=False
        )

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
        "google-api-python-client==2.108.0"
    ]

    packages_str = " ".join(packages)
    run_command(
        f"pip install {packages_str}",
        "Installing Python packages",
        check=False
    )

    # ========================================================================
    # STEP 6: SET ENVIRONMENT VARIABLES
    # ========================================================================

    print("\n" + "🔐 STEP 6: ENVIRONMENT VARIABLES")

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
        print(f"✅ Set {key}")

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

    # ========================================================================
    # SETUP COMPLETE
    # ========================================================================

    print("\n" + "="*70)
    print("✅ SETUP COMPLETE!")
    print("="*70)
    print(f"📁 Working directory: {os.getcwd()}")
    print("🚀 Starting bot now...\n")

    return True


# ============================================================================
# STEP 2: EMBEDDED BOT CODE
# ============================================================================

# Read the bot code from final_working_bot.py
def get_bot_code():
    """Return the complete bot code as a string"""

    # Try to read from external file first
    bot_file = "final_working_bot.py"

    if os.path.exists(bot_file):
        print(f"📄 Reading bot code from {bot_file}")
        with open(bot_file, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        print(f"⚠️ {bot_file} not found!")
        print("Please ensure final_working_bot.py is in the same directory")
        return None


def run_bot():
    """Execute the bot code"""

    print("\n" + "="*70)
    print("🤖 STARTING F5-TTS BOT")
    print("="*70 + "\n")

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

    # Get bot code
    bot_code = get_bot_code()

    if not bot_code:
        print("❌ Cannot start bot without bot code")
        print("\n💡 SOLUTION:")
        print("   Place 'final_working_bot.py' in the same directory as this script")
        return False

    # Execute bot code in the current namespace
    try:
        exec(bot_code, globals())
        return True
    except Exception as e:
        print(f"❌ Bot execution error: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main function - setup and run"""

    print("\n")
    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║                                                                   ║")
    print("║         🤖 F5-TTS BOT - AUTO SETUP AND RUN                       ║")
    print("║                                                                   ║")
    print("║         Single File Solution for Vast.ai                         ║")
    print("║                                                                   ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print("\n")

    # Check platform
    print(f"🖥️ Detected platform: {sys.platform}")

    if sys.platform.startswith('win'):
        print("✅ Windows VPS detected")
        print("\n⚠️ IMPORTANT: Make sure you have installed:")
        print("   1. Git")
        print("   2. Python 3.8+ with pip")
        print("   3. FFmpeg")
        print("   4. NVIDIA GPU drivers + CUDA toolkit")
        input("\n   Press Enter to continue if prerequisites are met...")
    elif sys.platform.startswith('linux'):
        print("✅ Linux environment detected (Vast.ai compatible)")
    else:
        print(f"⚠️ WARNING: Untested platform: {sys.platform}")
        response = input("\n   Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("❌ Aborted by user")
            return

    # Step 1: Setup environment
    print("\n🔧 Starting environment setup...")
    setup_success = setup_environment()

    if not setup_success:
        print("\n❌ Setup failed! Cannot proceed.")
        return

    # Small delay
    time.sleep(2)

    # Step 2: Run bot
    print("\n🤖 Starting bot execution...")

    # Check if final_working_bot.py exists
    bot_file = "final_working_bot.py"
    if not os.path.exists(bot_file):
        # Try to find it in parent directory or current directory
        possible_locations = [
            os.path.join("/workspace", bot_file),  # Vast.ai first priority
            os.path.join("/workspace/f5-automation", bot_file),
            bot_file,
            os.path.join("..", bot_file),
            os.path.join(os.path.dirname(__file__), bot_file)
        ]

        found = False
        for location in possible_locations:
            if os.path.exists(location):
                print(f"✅ Found bot file at: {location}")
                # Copy it to current directory
                import shutil
                shutil.copy(location, bot_file)
                found = True
                break

        if not found:
            print(f"\n❌ ERROR: {bot_file} not found!")
            print("\n📝 INSTRUCTIONS:")
            print("   1. Place 'final_working_bot.py' in the same directory as this script")
            print("   2. Or in: /workspace/f5-automation/")
            print("   3. Then run this script again")
            return

    # Now run the bot
    run_bot()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user (Ctrl+C)")
        print("👋 Shutting down...")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n✅ Script finished")
