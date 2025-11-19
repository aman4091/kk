# Gemini Flash Integration for final_working_bot.py
# Copy this function into final_working_bot.py after process_with_deepseek()

async def process_with_gemini(self, transcript, chat_id, context, custom_prompt=None):
    """Process transcript through Gemini Flash API in chunks"""
    try:
        import google.generativeai as genai

        api_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY")
        prompt = custom_prompt if custom_prompt else self.gemini_prompt

        if not api_key:
            print("❌ GEMINI_API_KEY not set")
            return None

        # Configure Gemini
        genai.configure(api_key=api_key)

        # Use latest Gemini Flash model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # or gemini-1.5-flash-latest

        # Split transcript into chunks
        chunk_size = int(os.getenv("GEMINI_CHUNK_SIZE", 7000))
        chunks = self.split_text_into_chunks(transcript, chunk_size)
        processed_chunks = []

        await context.bot.send_message(chat_id, f"🤖 Processing {len(chunks)} chunks with Gemini Flash...")

        for i, chunk in enumerate(chunks):
            await context.bot.send_message(chat_id, f"🔄 Gemini chunk {i+1}/{len(chunks)}")

            max_retries = 3
            processed_text = None

            for attempt in range(1, max_retries + 1):
                try:
                    # Gemini API call
                    response = model.generate_content(
                        f"{prompt}\n\n{chunk}",
                        generation_config={
                            "temperature": 0.7,
                            "top_p": 0.95,
                            "top_k": 40,
                            "max_output_tokens": 8192,
                        },
                        safety_settings={
                            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
                        }
                    )

                    processed_text = response.text
                    break

                except Exception as e:
                    print(f"⚠️ Gemini error on chunk {i+1}, attempt {attempt}/{max_retries}: {e}")
                    if attempt < max_retries:
                        await asyncio.sleep(2 * attempt)
                        continue
                    break

            if processed_text is None:
                processed_text = chunk  # Fallback to original

            processed_chunks.append(processed_text)
            await asyncio.sleep(0.5)  # Rate limiting

        return " ".join(processed_chunks)

    except Exception as e:
        print(f"Gemini processing error: {e}")
        return None


# Unified AI Router
async def process_with_ai(self, transcript, chat_id, context, custom_prompt=None):
    """Route to Gemini or DeepSeek based on ai_provider setting"""
    if self.ai_provider == "gemini":
        return await self.process_with_gemini(transcript, chat_id, context, custom_prompt)
    else:  # deepseek
        return await self.process_with_deepseek(transcript, chat_id, context, custom_prompt)


# Commands to add (register in main())

async def setai_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch AI provider"""
    try:
        if not context.args:
            await update.message.reply_text(
                f"🤖 **Current AI Provider:** `{self.ai_provider.upper()}`\n\n"
                f"Switch with:\n"
                f"`/setai gemini` - Use Gemini Flash\n"
                f"`/setai deepseek` - Use DeepSeek",
                parse_mode="Markdown"
            )
            return

        provider = context.args[0].lower()
        if provider not in ["gemini", "deepseek"]:
            await update.message.reply_text("❌ Invalid provider! Use: gemini or deepseek")
            return

        self.ai_provider = provider
        self.save_config()

        await update.message.reply_text(
            f"✅ AI provider switched to: **{provider.upper()}**\n\n"
            f"All new processing will use {provider.capitalize()}.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def ai_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show AI provider status"""
    try:
        gemini_status = "✅ Ready" if self.gemini_api_key else "❌ Not configured"
        deepseek_status = "✅ Ready" if os.getenv("DEEPSEEK_API_KEY") else "❌ Not configured"

        status_text = (
            f"🤖 **AI Provider Status**\n\n"
            f"**Current:** {self.ai_provider.upper()}\n\n"
            f"**Gemini Flash:** {gemini_status}\n"
            f"Prompt: `{self.gemini_prompt[:50]}...`\n\n"
            f"**DeepSeek:** {deepseek_status}\n"
            f"Prompt: `{self.deepseek_prompt[:50]}...`\n\n"
            f"Switch: `/setai <provider>`"
        )

        await update.message.reply_text(status_text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def set_gemini_prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set Gemini processing prompt"""
    try:
        if context.args:
            new_prompt = " ".join(context.args)
            self.gemini_prompt = new_prompt
            self.save_config()

            await update.message.reply_text(
                f"✅ Gemini prompt updated!\n\n"
                f"📝 New prompt: {new_prompt}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"📝 Current Gemini prompt:\n{self.gemini_prompt}\n\n"
                f"💡 Usage: `/set_gemini_prompt Your new prompt here`",
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


# Command registration (add to main() function):
# application.add_handler(CommandHandler("setai", bot_instance.setai_command))
# application.add_handler(CommandHandler("ai_status", bot_instance.ai_status_command))
# application.add_handler(CommandHandler("set_gemini_prompt", bot_instance.set_gemini_prompt_command))


# Replace DeepSeek calls:
# Find all instances of: await self.process_with_deepseek(...)
# Replace with: await self.process_with_ai(...)
