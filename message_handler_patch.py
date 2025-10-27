# Message Handler Modification for Channel Detection
# Replace the YouTube link detection section (around line 3992)

            if youtube_links:
                # Check if it's a channel or video
                for youtube_url in youtube_links:
                    # Detect channel vs video
                    if self.youtube_processor.is_youtube_channel_url(youtube_url):
                        # Channel URL detected - process as channel
                        msg_text = (
                            f"📺 **YouTube Channel Detected!**\n\n"
                            f"🔗 URL: {youtube_url[:50]}{'...' if len(youtube_url) > 50 else ''}\n\n"
                            f"🎯 Will process top 6 videos (>10 min, not processed in last 15 days)\n"
                            f"⏱️ Estimated time: 15-20 minutes"
                        )

                        try:
                            if is_channel:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=msg_text,
                                    parse_mode="Markdown"
                                )
                            else:
                                await update.message.reply_text(msg_text, parse_mode="Markdown")

                            # Process channel
                            print(f"📺 Processing YouTube channel: {youtube_url}")
                            await self.process_youtube_channel(youtube_url, update, context)

                        except Exception as e:
                            print(f"Error processing YouTube channel: {e}")
                            error_msg = f"❌ Failed to process YouTube channel: {str(e)[:100]}"
                            if is_channel:
                                await context.bot.send_message(chat_id=chat_id, text=error_msg)
                            else:
                                await update.message.reply_text(error_msg)

                    elif self.youtube_processor.is_youtube_video_url(youtube_url):
                        # Video URL detected - process as reference audio
                        msg_text = (
                            f"🔗 YouTube video detected!\n\n"
                            f"📺 URL: {youtube_url[:50]}{'...' if len(youtube_url) > 50 else ''}\n\n"
                            f"🎵 Automatically processing as Reference Audio...\n"
                            f"📥 Extracting audio → Cropping to 30s → Setting as voice reference"
                        )

                        try:
                            if is_channel:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=msg_text
                                )
                            else:
                                await update.message.reply_text(msg_text)

                            # Automatically extract audio as reference
                            print(f"🎵 Auto-processing YouTube video as Reference Audio: {youtube_url}")
                            await self.extract_youtube_audio_as_reference(youtube_url, update, context)

                        except Exception as e:
                            print(f"Error processing YouTube video: {e}")
                            error_msg = f"❌ Failed to process YouTube video: {str(e)[:100]}"
                            if is_channel:
                                await context.bot.send_message(chat_id=chat_id, text=error_msg)
                            else:
                                await update.message.reply_text(error_msg)
                    else:
                        # Unknown YouTube URL format
                        error_msg = "⚠️ Could not determine if this is a channel or video URL"
                        if is_channel:
                            await context.bot.send_message(chat_id=chat_id, text=error_msg)
                        else:
                            await update.message.reply_text(error_msg)
