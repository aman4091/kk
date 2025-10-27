# New Command Handlers for API Key Management and Supabase Setup
# Add these methods to WorkingF5Bot class

    # =============================================================================
    # SUPABASE & API KEY MANAGEMENT COMMANDS
    # =============================================================================

    async def set_supabase_url_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Supabase URL via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing Supabase URL\n\n"
                    "Usage: /set_supabase_url <your_supabase_url>\n\n"
                    "Example:\n"
                    "/set_supabase_url https://xxxxx.supabase.co"
                )
                return

            url = context.args[0]
            os.environ["SUPABASE_URL"] = url

            # Reinitialize Supabase client
            self.supabase = SupabaseClient(url=url, key=os.getenv("SUPABASE_ANON_KEY"))

            await update.message.reply_text(
                f"✅ Supabase URL set successfully!\n\n"
                f"🔗 URL: {url[:30]}...\n\n"
                f"Next: Set anon key with /set_supabase_key"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting Supabase URL: {str(e)}")

    async def set_supabase_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Supabase Anon Key via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing Supabase Anon Key\n\n"
                    "Usage: /set_supabase_key <your_anon_key>\n\n"
                    "Example:\n"
                    "/set_supabase_key eyJhbGciOiJIUzI1..."
                )
                return

            key = context.args[0]
            os.environ["SUPABASE_ANON_KEY"] = key

            # Reinitialize Supabase client
            self.supabase = SupabaseClient(url=os.getenv("SUPABASE_URL"), key=key)

            if self.supabase.is_connected():
                # Try to initialize tables
                self.supabase.init_tables()

                await update.message.reply_text(
                    f"✅ Supabase connected successfully!\n\n"
                    f"🔑 Key: {key[:20]}...\n\n"
                    f"📊 Database ready for use!\n\n"
                    f"💡 Next steps:\n"
                    f"1. /set_youtube_key <api_key>\n"
                    f"2. /add_supadata_key <api_key>\n"
                    f"3. /set_deepseek_key <api_key>"
                )
            else:
                await update.message.reply_text(
                    "⚠️ Supabase key set but connection failed.\n"
                    "Please check your credentials."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting Supabase key: {str(e)}")

    async def set_youtube_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set YouTube Data API key via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing YouTube API Key\n\n"
                    "Usage: /set_youtube_key <your_api_key>\n\n"
                    "Example:\n"
                    "/set_youtube_key AIzaSyBxxxxxxxxxxxxxx\n\n"
                    "Get API key from:\n"
                    "https://console.cloud.google.com/apis/credentials"
                )
                return

            api_key = context.args[0]

            # Store in Supabase
            if self.supabase.is_connected():
                success = self.supabase.store_api_key('youtube', api_key)
                if success:
                    # Update YouTube processor
                    self.youtube_processor.set_api_key(api_key)

                    await update.message.reply_text(
                        f"✅ YouTube API key saved to database!\n\n"
                        f"🔑 Key: {api_key[:20]}...\n\n"
                        f"You can now process YouTube channels!"
                    )
                else:
                    await update.message.reply_text("❌ Failed to save API key to database")
            else:
                # Fallback: Store in memory only
                self.youtube_processor.set_api_key(api_key)
                await update.message.reply_text(
                    f"⚠️ YouTube API key set (memory only)\n\n"
                    f"🔑 Key: {api_key[:20]}...\n\n"
                    f"⚠️ Supabase not connected. Key won't persist after restart.\n"
                    f"Use /set_supabase_url and /set_supabase_key first."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting YouTube key: {str(e)}")

    async def add_supadata_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add Supadata API key to pool via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing Supadata API Key\n\n"
                    "Usage: /add_supadata_key <your_api_key>\n\n"
                    "Example:\n"
                    "/add_supadata_key sd_xxxxxxxxxx\n\n"
                    "💡 You can add multiple keys for rotation!"
                )
                return

            api_key = context.args[0]

            # Store in Supabase
            if self.supabase.is_connected():
                success = self.supabase.store_api_key('supadata', api_key)
                if success:
                    # Get total active keys
                    all_keys = self.supabase.get_all_api_keys_status()
                    supadata_keys = [k for k in all_keys if k['key_type'] == 'supadata' and k['is_active']]

                    await update.message.reply_text(
                        f"✅ Supadata API key added to pool!\n\n"
                        f"🔑 Key: {api_key[:20]}...\n\n"
                        f"📊 Total active Supadata keys: {len(supadata_keys)}\n\n"
                        f"💡 Keys will auto-rotate on quota exhaustion"
                    )
                else:
                    await update.message.reply_text("❌ Failed to save API key to database")
            else:
                await update.message.reply_text(
                    "⚠️ Supabase not connected!\n\n"
                    "Use /set_supabase_url and /set_supabase_key first."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error adding Supadata key: {str(e)}")

    async def set_deepseek_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set DeepSeek API key via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing DeepSeek API Key\n\n"
                    "Usage: /set_deepseek_key <your_api_key>\n\n"
                    "Example:\n"
                    "/set_deepseek_key sk-xxxxxxxxxx"
                )
                return

            api_key = context.args[0]

            # Store in Supabase
            if self.supabase.is_connected():
                success = self.supabase.store_api_key('deepseek', api_key)
                if success:
                    await update.message.reply_text(
                        f"✅ DeepSeek API key saved to database!\n\n"
                        f"🔑 Key: {api_key[:20]}...\n\n"
                        f"Bot will use this key for text processing."
                    )
                else:
                    await update.message.reply_text("❌ Failed to save API key to database")
            else:
                # Update environment variable as fallback
                os.environ["DEEPSEEK_API_KEY"] = api_key
                await update.message.reply_text(
                    f"⚠️ DeepSeek API key set (memory only)\n\n"
                    f"🔑 Key: {api_key[:20]}...\n\n"
                    f"⚠️ Supabase not connected. Key won't persist.\n"
                    f"Use /set_supabase_url and /set_supabase_key first."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting DeepSeek key: {str(e)}")

    async def set_channel_prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set custom prompt for channel video processing"""
        try:
            if not context.args:
                # Show current prompt
                current_prompt = "Default: Rewrite this content to be more engaging for audio"
                if self.supabase.is_connected():
                    saved_prompt = self.supabase.get_prompt('channel')
                    if saved_prompt:
                        current_prompt = saved_prompt

                await update.message.reply_text(
                    f"📝 Channel Processing Prompt\n\n"
                    f"Current prompt:\n{current_prompt}\n\n"
                    f"Usage: /set_channel_prompt <your_prompt>\n\n"
                    f"Example:\n"
                    f"/set_channel_prompt Rewrite this transcript into engaging storytelling format"
                )
                return

            new_prompt = ' '.join(context.args)

            # Store in Supabase
            if self.supabase.is_connected():
                success = self.supabase.save_prompt('channel', new_prompt)
                if success:
                    await update.message.reply_text(
                        f"✅ Channel prompt saved to database!\n\n"
                        f"📝 New prompt:\n{new_prompt}\n\n"
                        f"This will be used for all channel video processing."
                    )
                else:
                    await update.message.reply_text("❌ Failed to save prompt to database")
            else:
                await update.message.reply_text(
                    "⚠️ Supabase not connected!\n\n"
                    "Prompt not saved. Use /set_supabase_url and /set_supabase_key first."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting prompt: {str(e)}")

    async def list_keys_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all API keys status"""
        try:
            if not self.supabase.is_connected():
                await update.message.reply_text(
                    "⚠️ Supabase not connected!\n\n"
                    "Use /set_supabase_url and /set_supabase_key to connect."
                )
                return

            keys = self.supabase.get_all_api_keys_status()

            if not keys:
                await update.message.reply_text(
                    "📊 No API keys found in database.\n\n"
                    "Add keys using:\n"
                    "• /set_youtube_key\n"
                    "• /add_supadata_key\n"
                    "• /set_deepseek_key"
                )
                return

            # Group by type
            youtube_keys = [k for k in keys if k['key_type'] == 'youtube']
            supadata_keys = [k for k in keys if k['key_type'] == 'supadata']
            deepseek_keys = [k for k in keys if k['key_type'] == 'deepseek']

            message = "📊 **API Keys Status**\n\n"

            # YouTube keys
            message += f"🎥 **YouTube API ({len(youtube_keys)} keys)**\n"
            for k in youtube_keys:
                status = "✅ Active" if k['is_active'] else "❌ Inactive"
                message += f"  • {k['api_key'][:20]}... - {status}\n"
            message += "\n"

            # Supadata keys
            message += f"📜 **Supadata API ({len(supadata_keys)} keys)**\n"
            active_count = sum(1 for k in supadata_keys if k['is_active'])
            message += f"  Active: {active_count}/{len(supadata_keys)}\n"
            for k in supadata_keys:
                status = "✅ Active" if k['is_active'] else "❌ Exhausted"
                message += f"  • {k['api_key'][:20]}... - {status}\n"
            message += "\n"

            # DeepSeek keys
            message += f"🤖 **DeepSeek API ({len(deepseek_keys)} keys)**\n"
            for k in deepseek_keys:
                status = "✅ Active" if k['is_active'] else "❌ Inactive"
                message += f"  • {k['api_key'][:20]}... - {status}\n"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error listing keys: {str(e)}")
