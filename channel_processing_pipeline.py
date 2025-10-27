# YouTube Channel Processing Pipeline
# Add this method to WorkingF5Bot class

    async def process_youtube_channel(self, channel_url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Complete pipeline to process a YouTube channel:
        1. Fetch top 1000 videos (>10min, sorted by views)
        2. Select 6 unique videos (15-day cooldown)
        3. For each video:
           - Get transcript
           - Chunk at 7000 chars
           - Process chunks with DeepSeek
           - Generate audio with global counter
           - Upload to Gofile
        4. Send all audio links
        """
        chat_id = update.effective_chat.id

        try:
            await update.message.reply_text(
                "🔍 **YouTube Channel Detected!**\n\n"
                "📊 Starting channel processing...",
                parse_mode="Markdown"
            )

            # Step 1: Initialize YouTube processor with API key
            if not self.youtube_processor.youtube:
                # Get API key from database
                if self.supabase.is_connected():
                    yt_key = self.supabase.get_active_api_key('youtube')
                    if yt_key:
                        self.youtube_processor.set_api_key(yt_key)
                    else:
                        await update.message.reply_text(
                            "❌ No YouTube API key found!\n\n"
                            "Use /set_youtube_key to add one."
                        )
                        return
                else:
                    await update.message.reply_text(
                        "❌ Supabase not connected!\n\n"
                        "Use /set_supabase_url and /set_supabase_key first."
                    )
                    return

            # Step 2: Fetch channel videos
            await update.message.reply_text("📺 Fetching channel videos...")

            channel_id, all_videos = self.youtube_processor.get_channel_top_videos(
                channel_url, count=1000, min_duration_min=10
            )

            if not channel_id or not all_videos:
                await update.message.reply_text(
                    "❌ Failed to fetch channel videos.\n"
                    "Please check the channel URL."
                )
                return

            await update.message.reply_text(
                f"✅ Found {len(all_videos)} videos (>10 min)\n"
                f"🎯 Selecting top 6 unique videos..."
            )

            # Step 3: Get unprocessed video IDs (15-day cooldown)
            all_video_ids = [v['video_id'] for v in all_videos]
            unprocessed_ids = all_video_ids  # Default: all

            if self.supabase.is_connected():
                unprocessed_ids = self.supabase.get_unprocessed_videos(all_video_ids, days=15)

            # Step 4: Select top 6
            selected_videos = self.youtube_processor.select_unique_videos(
                all_videos, unprocessed_ids, count=6
            )

            if not selected_videos:
                await update.message.reply_text(
                    "⚠️ No new videos to process!\n\n"
                    "All videos have been processed in the last 15 days.\n"
                    "Try again later or try a different channel."
                )
                return

            await update.message.reply_text(
                f"✅ Selected {len(selected_videos)} videos\n\n"
                f"📹 Starting processing...\n"
                f"⏱️ This may take 15-20 minutes"
            )

            # Step 5: Process each video
            processed_count = 0
            all_audio_links = []

            for idx, video in enumerate(selected_videos, 1):
                video_id = video['video_id']
                video_url = video['url']
                video_title = video['title']

                try:
                    await update.message.reply_text(
                        f"📹 **Video {idx}/6**\n"
                        f"🎬 {video_title[:60]}...\n"
                        f"👁️ Views: {video['view_count']:,}\n\n"
                        f"🔄 Processing...",
                        parse_mode="Markdown"
                    )

                    # Step 5a: Get transcript
                    transcript, key_exhausted = await self._get_transcript_with_rotation(video_url)

                    if not transcript:
                        await update.message.reply_text(f"❌ Video {idx}: Transcript fetch failed. Skipping...")
                        continue

                    await update.message.reply_text(
                        f"✅ Video {idx}: Transcript received ({len(transcript)} chars)"
                    )

                    # Step 5b: Chunk transcript
                    chunks = self.youtube_processor.chunk_text_at_fullstop(transcript, max_chars=7000)
                    await update.message.reply_text(
                        f"📦 Video {idx}: Split into {len(chunks)} chunks"
                    )

                    # Step 5c: Process chunks with DeepSeek
                    processed_chunks = await self._process_chunks_with_deepseek(
                        chunks, video_id, chat_id, update, context, idx, len(selected_videos)
                    )

                    if not processed_chunks:
                        await update.message.reply_text(f"❌ Video {idx}: DeepSeek processing failed. Skipping...")
                        continue

                    # Step 5d: Merge chunks
                    merged_script = "\n\n".join(processed_chunks)

                    # Save merged script
                    self.youtube_processor.save_merged_script(merged_script, video_id, self.chunks_dir)

                    await update.message.reply_text(
                        f"✅ Video {idx}: Script processed ({len(merged_script)} chars)\n"
                        f"🎵 Generating audio..."
                    )

                    # Step 5e: Generate audio with global counter
                    audio_links = await self._generate_audio_with_counter(
                        merged_script, video_id, chat_id, update, context
                    )

                    if audio_links:
                        all_audio_links.extend(audio_links)
                        processed_count += 1

                        # Mark video as processed in database
                        if self.supabase.is_connected():
                            counter = self.supabase.get_counter()
                            self.supabase.mark_video_processed(
                                video_id, video_url, channel_id, str(chat_id), counter
                            )

                        await update.message.reply_text(
                            f"✅ Video {idx}/{len(selected_videos)} complete!\n"
                            f"📊 Progress: {processed_count} successful"
                        )
                    else:
                        await update.message.reply_text(f"❌ Video {idx}: Audio generation failed. Skipping...")

                except Exception as e:
                    print(f"Error processing video {idx}: {e}")
                    await update.message.reply_text(
                        f"❌ Video {idx}: Error - {str(e)[:100]}\n"
                        f"Continuing with next video..."
                    )
                    continue

            # Step 6: Final summary
            if processed_count > 0:
                summary = (
                    f"🎉 **Channel Processing Complete!**\n\n"
                    f"✅ Successfully processed: {processed_count}/{len(selected_videos)} videos\n"
                    f"🔗 Total audio files: {len(all_audio_links)}\n\n"
                    f"📊 All audio links have been sent above.\n"
                    f"💾 Scripts saved in: {self.chunks_dir}/"
                )
                await update.message.reply_text(summary, parse_mode="Markdown")
            else:
                await update.message.reply_text(
                    "❌ No videos were successfully processed.\n"
                    "Please check logs for errors."
                )

        except Exception as e:
            error_msg = f"❌ Channel processing error: {str(e)}"
            print(error_msg)
            await update.message.reply_text(error_msg[:500])

    async def _get_transcript_with_rotation(self, video_url: str) -> tuple:
        """
        Get transcript with automatic Supadata key rotation on exhaustion.
        Returns: (transcript_text, key_exhausted)
        """
        max_attempts = 5  # Try up to 5 different keys

        for attempt in range(max_attempts):
            # Get active Supadata key
            api_key = None
            if self.supabase.is_connected():
                api_key = self.supabase.get_active_api_key('supadata')
            else:
                api_key = os.getenv("SUPADATA_API_KEY")

            if not api_key:
                print("❌ No Supadata API key available")
                return None, False

            # Try to get transcript
            transcript, key_exhausted = await get_youtube_transcript(video_url, api_key)

            if transcript:
                return transcript, False

            if key_exhausted:
                print(f"⚠️ Supadata key exhausted. Rotating... (attempt {attempt + 1}/{max_attempts})")
                # Mark key as exhausted
                if self.supabase.is_connected():
                    self.supabase.mark_key_exhausted(api_key)
                continue
            else:
                # Other error, no point rotating
                return None, False

        print("❌ All Supadata keys exhausted")
        return None, True

    async def _process_chunks_with_deepseek(self, chunks: list, video_id: str, chat_id: int,
                                           update: Update, context: ContextTypes.DEFAULT_TYPE,
                                           video_idx: int, total_videos: int) -> list:
        """
        Process each chunk with DeepSeek API and save to disk.
        Returns list of processed chunks.
        """
        # Get DeepSeek API key
        deepseek_key = None
        if self.supabase.is_connected():
            deepseek_key = self.supabase.get_active_api_key('deepseek')
        if not deepseek_key:
            deepseek_key = os.getenv("DEEPSEEK_API_KEY")

        if not deepseek_key:
            print("❌ No DeepSeek API key available")
            return []

        # Get custom prompt if available
        prompt = None
        if self.supabase.is_connected():
            prompt = self.supabase.get_prompt('channel')
        if not prompt:
            prompt = "Rewrite this content to be more engaging and natural for text-to-speech audio:"

        processed_chunks = []

        # Save original chunks
        self.youtube_processor.save_chunks_to_disk(chunks, video_id, self.chunks_dir)

        for chunk_idx, chunk in enumerate(chunks, 1):
            try:
                await update.message.reply_text(
                    f"🤖 Video {video_idx}: Processing chunk {chunk_idx}/{len(chunks)}..."
                )

                # Process with DeepSeek (use existing method from bot)
                processed = await self.process_with_deepseek(
                    chunk, chat_id, context, custom_prompt=prompt
                )

                if processed:
                    processed_chunks.append(processed)
                else:
                    # Fallback to original chunk
                    processed_chunks.append(chunk)

            except Exception as e:
                print(f"Error processing chunk {chunk_idx}: {e}")
                # Fallback to original chunk
                processed_chunks.append(chunk)

        return processed_chunks

    async def _generate_audio_with_counter(self, script: str, video_id: str, chat_id: int,
                                          update: Update, context: ContextTypes.DEFAULT_TYPE) -> list:
        """
        Generate audio using F5-TTS with global counter-based naming.
        Returns list of Gofile links.
        """
        try:
            # Get and increment global counter
            counter = 0
            if self.supabase.is_connected():
                counter = self.supabase.increment_counter()
            else:
                # Fallback: use timestamp
                counter = int(time.time()) % 10000

            # Generate audio (use existing generate_audio method)
            # Modify output path to use counter
            base_output_path = os.path.join(OUTPUT_DIR, f"{counter}")

            # Use existing audio generation logic but with custom filename
            raw_output = f"{base_output_path}_raw.wav"
            enhanced_output = f"{base_output_path}_enhanced.wav"

            # Generate raw audio
            await update.message.reply_text(f"🎵 Generating audio {counter}_raw.wav...")
            raw_success = await self._generate_f5_audio(script, raw_output, chat_id, context)

            if not raw_success:
                return []

            # Apply filters for enhanced version
            await update.message.reply_text(f"🎛️ Creating enhanced version...")
            self.apply_audio_filters(raw_output, enhanced_output)

            # Upload both files
            links = []

            for file_path in [raw_output, enhanced_output]:
                if os.path.exists(file_path):
                    filename = os.path.basename(file_path)
                    size_mb = os.path.getsize(file_path) // (1024 * 1024)

                    # Upload to Gofile
                    link = await self.upload_single_to_gofile(file_path)

                    if link:
                        await update.message.reply_text(
                            f"🔗 **{filename}** ({size_mb} MB)\n{link}",
                            parse_mode="Markdown"
                        )
                        links.append(link)
                    else:
                        await update.message.reply_text(f"⚠️ Failed to upload {filename}")

            return links

        except Exception as e:
            print(f"Error generating audio: {e}")
            return []

    async def _generate_f5_audio(self, text: str, output_path: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Generate audio using F5-TTS (wrapper around existing method).
        Returns True if successful.
        """
        try:
            # Use existing generate_audio method from the bot
            # This is a simplified version - you may need to adapt based on your existing implementation

            if not self.f5_model or not self.reference_audio:
                print("❌ F5-TTS model or reference audio not initialized")
                return False

            # Generate audio (use your existing F5-TTS generation code)
            # This is placeholder - adapt to your actual F5-TTS implementation
            from f5_tts.api import F5TTS

            # Generate audio chunks
            wav = self.f5_model.infer(
                ref_audio=self.reference_audio,
                ref_text=self.reference_text,
                gen_text=text[:self.chunk_size],  # Use configured chunk size
                speed=self.audio_speed
            )

            # Save audio
            import soundfile as sf
            sf.write(output_path, wav, 24000)

            return True

        except Exception as e:
            print(f"F5-TTS generation error: {e}")
            return False
