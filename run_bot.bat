@echo off
setlocal enabledelayedexpansion

echo ================================================
echo    F5-TTS Bot - Automated Setup and Run
echo ================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python nahi mila! Please install Python 3.8 or higher.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Create venv if not exists
if not exist "venv" (
    echo Virtual environment bana rahe hain...
    python -m venv venv
    if errorlevel 1 (
        echo Venv create nahi ho paya!
        pause
        exit /b 1
    )
    echo Virtual environment ban gaya!
    echo.
)

:: Activate venv
echo Virtual environment activate kar rahe hain...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Venv activate nahi ho paya!
    pause
    exit /b 1
)

:: Install/Update dependencies
echo.
echo Dependencies install kar rahe hain (thoda time lagega)...
echo.

:: Install core dependencies
python -m pip install --upgrade pip >nul 2>&1

echo Installing telegram bot...
pip install python-telegram-bot --quiet

echo Installing AI libraries...
pip install openai-whisper soundfile librosa --quiet

echo Installing media tools...
pip install yt-dlp --quiet

echo Installing utilities...
pip install requests python-dotenv feedparser pytz==2023.3 --quiet

echo Installing Google APIs...
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 --quiet

echo Installing Supabase and HTTP client...
pip install supabase>=2.0.0 httpx>=0.24.0 isodate>=0.6.1 --quiet

echo Installing PyTorch (ye heavy hai, time lagega)...
pip install torch torchaudio --quiet

echo.
echo Saari dependencies install ho gayi!
echo.

:: Check if .env exists, if not create template
if not exist ".env" (
    echo .env file nahi mili, template bana rahe hain...
    echo.
    (
        echo # ========================================
        echo # F5-TTS Bot Environment Variables
        echo # ========================================
        echo.
        echo # REQUIRED: Telegram Bot Token ^(BotFather se milega^)
        echo BOT_TOKEN=your_bot_token_here
        echo.
        echo # OPTIONAL: Default chat ID
        echo CHAT_ID=your_chat_id_here
        echo.
        echo # REQUIRED: DeepSeek API Key
        echo DEEPSEEK_API_KEY=your_deepseek_api_key
        echo.
        echo # REQUIRED: Supadata API Key ^(transcription ke liye^)
        echo SUPADATA_API_KEY=your_supadata_api_key
        echo.
        echo # REQUIRED: Supabase Database Credentials
        echo SUPABASE_URL=your_supabase_project_url
        echo SUPABASE_ANON_KEY=your_supabase_anon_key
        echo.
        echo # REQUIRED: YouTube Data API v3 Key
        echo YOUTUBE_API_KEY=your_youtube_api_key
        echo.
        echo # OPTIONAL: Telegram Chat IDs for shorts and long content
        echo IMAGE_SHORTS_CHAT_ID=
        echo IMAGE_LONG_CHAT_ID=
        echo.
        echo # OPTIONAL: Google Drive Folder IDs
        echo GDRIVE_FOLDER_LONG=
        echo GDRIVE_FOLDER_SHORT=
        echo.
        echo # OPTIONAL: YouTube Channel IDs ^(comma-separated^)
        echo CHANNEL_IDS=
        echo.
        echo # OPTIONAL: Channel mode enable/disable
        echo CHANNEL_MODE_ENABLED=true
        echo.
        echo # OPTIONAL: Vast.ai credentials ^(agar use karte ho^)
        echo VAST_API_KEY=
        echo VAST_INSTANCE_ID=
        echo CONTAINER_ID=
        echo.
        echo # OPTIONAL: Gofile token
        echo GOFILE_TOKEN=
    ) > .env

    echo .env file ban gayi hai!
    echo.
    echo IMPORTANT: Apne API keys .env file mein daalo!
    echo.
    echo .env file ko notepad mein kholo aur apne API keys daalo:
    echo   - BOT_TOKEN (required)
    echo   - DEEPSEEK_API_KEY (required)
    echo   - SUPADATA_API_KEY (required)
    echo   - SUPABASE_URL and SUPABASE_ANON_KEY (required)
    echo   - YOUTUBE_API_KEY (required)
    echo.
    echo Keys daal ke dobara run_bot.bat chalana!
    echo.
    pause
    exit /b 0
)

:: Run the bot
echo.
echo ================================================
echo    Bot start ho raha hai...
echo ================================================
echo.
echo Press Ctrl+C to stop the bot
echo.

python final_working_bot.py

:: If bot exits, show message
echo.
echo ================================================
echo    Bot band ho gaya
echo ================================================
echo.
pause
