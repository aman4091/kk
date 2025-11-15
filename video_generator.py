#!/usr/bin/env python3
"""
Video Generator Module
Creates videos from image + audio with burned-in ASS subtitles
"""

import os
import subprocess
import whisper
import re
import asyncio
from pathlib import Path


class VideoGenerator:
    def __init__(self):
        """Initialize video generator with Whisper model"""
        self.whisper_model = None
        print("✅ VideoGenerator initialized")

    def load_whisper_model(self, model_size="base"):
        """Load Whisper model for subtitle generation"""
        if not self.whisper_model:
            print(f"🔄 Loading Whisper model ({model_size})...")
            self.whisper_model = whisper.load_model(model_size)
            print("✅ Whisper model loaded")
        return self.whisper_model

    def create_video_from_image_audio(self, image_path, audio_path, output_path):
        """
        Create MP4 video from static image + audio

        Args:
            image_path: Path to image file
            audio_path: Path to audio file (WAV/MP3)
            output_path: Output video path (MP4)

        Returns:
            bool: True if successful
        """
        try:
            print(f"🎬 Creating video: {output_path}")
            print(f"   Image: {image_path}")
            print(f"   Audio: {audio_path}")

            # Ensure paths exist
            if not os.path.exists(image_path):
                print(f"❌ Image not found: {image_path}")
                return False

            if not os.path.exists(audio_path):
                print(f"❌ Audio not found: {audio_path}")
                return False

            # FFmpeg command: Loop image for duration of audio
            cmd = [
                'ffmpeg',
                '-loop', '1',                     # Loop image
                '-i', image_path,                 # Input image
                '-i', audio_path,                 # Input audio
                '-c:v', 'libx264',                # Video codec
                '-tune', 'stillimage',            # Optimize for still image
                '-c:a', 'aac',                    # Audio codec
                '-b:a', '192k',                   # Audio bitrate
                '-pix_fmt', 'yuv420p',            # Pixel format (compatibility)
                '-shortest',                      # Match shortest input (audio duration)
                '-y',                             # Overwrite output
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"✅ Video created: {output_path}")
                return True
            else:
                print(f"❌ FFmpeg error: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ Video creation error: {e}")
            return False

    def generate_subtitles_whisper(self, audio_path, output_srt_path=None):
        """
        Generate SRT subtitles from audio using Whisper

        Args:
            audio_path: Path to audio file
            output_srt_path: Optional output SRT path

        Returns:
            str: Path to generated SRT file
        """
        try:
            print(f"📝 Generating subtitles: {audio_path}")

            # Load model if not loaded
            if not self.whisper_model:
                self.load_whisper_model()

            # Transcribe audio with formatting options
            result = self.whisper_model.transcribe(
                audio_path,
                task="transcribe",
                language="en",
                verbose=False,
                word_timestamps=False  # Don't split by words (prevents overlapping boxes)
            )

            # Default output path
            if not output_srt_path:
                base_name = Path(audio_path).stem
                output_srt_path = f"output/{base_name}.srt"

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_srt_path), exist_ok=True)

            # Write SRT file
            self._write_srt(result['segments'], output_srt_path)

            print(f"✅ Subtitles generated: {output_srt_path}")
            return output_srt_path

        except Exception as e:
            print(f"❌ Subtitle generation error: {e}")
            return None

    def _write_srt(self, segments, output_path):
        """Write Whisper segments to SRT format with line wrapping"""
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                # Subtitle index
                f.write(f"{i}\n")

                # Timestamp
                start = self._format_timestamp(segment['start'])
                end = self._format_timestamp(segment['end'])
                f.write(f"{start} --> {end}\n")

                # Text with line wrapping (max 50 chars per line for 1920x1080)
                text = segment['text'].strip()
                wrapped_text = self._wrap_text(text, max_chars=50)
                f.write(f"{wrapped_text}\n\n")

    def _wrap_text(self, text, max_chars=50):
        """
        Wrap text to multiple lines for better readability

        Args:
            text: Input text
            max_chars: Maximum characters per line (default 50 for 1920x1080)

        Returns:
            str: Text with line breaks
        """
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            word_length = len(word)
            # +1 for space
            if current_length + word_length + len(current_line) > max_chars:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                    current_length = word_length
                else:
                    # Single word longer than max_chars - add it anyway
                    lines.append(word)
            else:
                current_line.append(word)
                current_length += word_length

        # Add remaining words
        if current_line:
            lines.append(' '.join(current_line))

        return '\n'.join(lines)

    def _format_timestamp(self, seconds):
        """Format seconds to SRT timestamp (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def convert_srt_to_ass(self, srt_path, ass_style=None, output_ass_path=None):
        """
        Convert SRT to ASS format with custom styling
        Creates complete ASS file manually (NOT using FFmpeg conversion)

        Args:
            srt_path: Path to SRT file
            ass_style: Custom ASS style string (optional)
            output_ass_path: Optional output ASS path

        Returns:
            str: Path to generated ASS file
        """
        try:
            print(f"🎨 Converting SRT → ASS: {srt_path}")

            # Default output path
            if not output_ass_path:
                output_ass_path = srt_path.replace('.srt', '.ass')

            # Default ASS style (if not provided)
            if not ass_style:
                ass_style = 'Style: Default,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,4,0,0,5,40,40,40,1'

            # Parse SRT file
            with open(srt_path, 'r', encoding='utf-8') as f:
                srt_content = f.read()

            # Create ASS file manually with proper structure
            ass_content = self._create_ass_from_srt(srt_content, ass_style)

            # Write ASS file
            with open(output_ass_path, 'w', encoding='utf-8') as f:
                f.write(ass_content)

            print(f"✅ ASS file created: {output_ass_path}")
            return output_ass_path

        except Exception as e:
            print(f"❌ SRT→ASS conversion error: {e}")
            return None

    def _srt_time_to_ass(self, srt_time):
        """
        Convert SRT time format to ASS time format

        SRT:  00:00:01,500 (HH:MM:SS,mmm - milliseconds)
        ASS:  0:00:01.50  (H:MM:SS.cc - centiseconds)

        Args:
            srt_time: SRT format time string (e.g., "00:00:01,500")

        Returns:
            str: ASS format time string (e.g., "0:00:01.50")
        """
        # Split by comma: "00:00:01,500" → ["00:00:01", "500"]
        time_part, ms_part = srt_time.split(',')

        # Parse HH:MM:SS
        h, m, s = time_part.split(':')
        h = int(h)  # Remove leading zeros (00 → 0)

        # Convert milliseconds to centiseconds (1000ms → 100cs)
        # 500ms → 50cs, 100ms → 10cs
        centiseconds = int(ms_part) // 10

        # Format: H:MM:SS.cc (centiseconds are 2 digits)
        return f"{h}:{m}:{s}.{centiseconds:02d}"

    def _create_ass_from_srt(self, srt_content, ass_style):
        """
        Create complete ASS file from SRT content with custom style

        Args:
            srt_content: SRT file content as string
            ass_style: Full ASS style string (e.g., "Style: Default,Arial,48,...")

        Returns:
            str: Complete ASS file content
        """
        # ASS file header (for 1920x1080 videos)
        ass_header = """[Script Info]
Title: Generated Subtitles
ScriptType: v4.00+
Collisions: Reverse
PlayDepth: 0
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
"""

        # Add custom style (replace "Banner" with "Default" if needed)
        if 'Style: Banner,' in ass_style:
            ass_style = ass_style.replace('Style: Banner,', 'Style: Default,')
        elif not ass_style.startswith('Style:'):
            ass_style = 'Style: Default,' + ass_style

        ass_header += ass_style + '\n\n'

        # Events section header
        ass_header += """[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # Parse SRT and convert to ASS events
        ass_events = []
        srt_blocks = srt_content.strip().split('\n\n')

        for block in srt_blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue

            # Parse timing (line 2: 00:00:01,000 --> 00:00:05,000)
            timing_line = lines[1]
            if '-->' not in timing_line:
                continue

            start_time, end_time = timing_line.split('-->')
            start_time = self._srt_time_to_ass(start_time.strip())
            end_time = self._srt_time_to_ass(end_time.strip())

            # Parse text (line 3+)
            # Use \N (ASS line break) to keep all lines in single box
            text = '\\N'.join(lines[2:])

            # Add \an5 tag for center alignment (keeps box centered, text inside aligned)
            # This ensures single box with properly aligned multi-line text
            text_with_alignment = '{\\an5}' + text

            # Create ASS event
            # Format: Dialogue: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
            ass_event = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text_with_alignment}"
            ass_events.append(ass_event)

        # Combine header + events
        return ass_header + '\n'.join(ass_events)

    def burn_subtitles(self, video_path, ass_path, output_path):
        """
        Burn ASS subtitles into video

        Args:
            video_path: Input video path
            ass_path: ASS subtitle file path
            output_path: Output video with burned subtitles

        Returns:
            bool: True if successful
        """
        try:
            print(f"🔥 Burning subtitles into video: {output_path}")

            # Ensure files exist
            if not os.path.exists(video_path):
                print(f"❌ Video not found: {video_path}")
                return False

            if not os.path.exists(ass_path):
                print(f"❌ ASS file not found: {ass_path}")
                return False

            # FFmpeg command: Burn ASS subtitles
            # Use absolute path for ASS file to avoid path issues
            ass_abs_path = os.path.abspath(ass_path)

            # Windows path fix for FFmpeg (convert \ to / and escape :)
            if os.name == 'nt':
                ass_abs_path = ass_abs_path.replace('\\', '/').replace(':', '\\:')

            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vf', f"ass={ass_abs_path}",
                '-c:a', 'copy',                 # Copy audio (no re-encode)
                '-y',
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"✅ Subtitles burned: {output_path}")
                return True
            else:
                print(f"❌ FFmpeg subtitle burn error: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ Subtitle burn error: {e}")
            return False

    def create_video_with_subtitles(self, image_path, audio_path, output_path, ass_style=None, progress_callback=None, event_loop=None):
        """
        Complete pipeline: Image + Audio → Video with subtitles

        Args:
            image_path: Path to image
            audio_path: Path to audio
            output_path: Final output video path
            ass_style: Optional custom ASS style
            progress_callback: Optional async function(message) for progress updates
            event_loop: Optional event loop for running async callbacks

        Returns:
            str: Path to final video or None if failed
        """

        def send_progress(msg):
            """Helper to send progress updates safely"""
            if progress_callback and event_loop:
                try:
                    asyncio.run_coroutine_threadsafe(progress_callback(msg), event_loop)
                except Exception as e:
                    print(f"⚠️ Progress callback error: {e}")

        try:
            print("\n" + "="*60)
            print("🎬 VIDEO GENERATION PIPELINE")
            print("="*60)

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Temp file paths
            base_name = Path(audio_path).stem
            temp_video = f"output/{base_name}_temp.mp4"
            srt_path = f"output/{base_name}.srt"
            ass_path = f"output/{base_name}.ass"

            # Step 1: Create video (image + audio)
            print("\n📹 Step 1/4: Creating video from image + audio...")
            send_progress("📹 [25%] Creating video from image + audio...")

            if not self.create_video_from_image_audio(image_path, audio_path, temp_video):
                return None

            # Step 2: Generate subtitles with Whisper
            print("\n📝 Step 2/4: Generating subtitles with Whisper...")
            send_progress("📝 [50%] Generating subtitles with Whisper AI...")

            if not self.generate_subtitles_whisper(audio_path, srt_path):
                return None

            # Step 3: Convert SRT → ASS with styling
            print("\n🎨 Step 3/4: Converting SRT → ASS with styling...")
            send_progress("🎨 [75%] Converting subtitles to ASS format...")

            if not self.convert_srt_to_ass(srt_path, ass_style, ass_path):
                return None

            # Step 4: Burn subtitles into video
            print("\n🔥 Step 4/4: Burning subtitles into video...")
            send_progress("🔥 [90%] Burning subtitles into video...")

            if not self.burn_subtitles(temp_video, ass_path, output_path):
                return None

            # Cleanup temp files
            try:
                os.remove(temp_video)
                os.remove(srt_path)
                os.remove(ass_path)
                print("\n🧹 Cleaned up temporary files")
            except:
                pass

            send_progress("✅ [100%] Video generation complete!")

            print("\n" + "="*60)
            print(f"✅ VIDEO PIPELINE COMPLETE: {output_path}")
            print("="*60 + "\n")

            return output_path

        except Exception as e:
            print(f"\n❌ Video pipeline error: {e}")
            import traceback
            traceback.print_exc()
            return None


# Example usage
if __name__ == '__main__':
    vg = VideoGenerator()

    # Test video creation
    result = vg.create_video_with_subtitles(
        image_path="test_image.jpg",
        audio_path="test_audio.wav",
        output_path="output/test_final.mp4",
        ass_style="Style: Banner,Arial,48,&H00FFFFFF,&H00FFFFFF,&H80000000,&H00000000,-1,0,0,0,100,100,0,0,3,12,0,5,40,40,40,1"
    )

    if result:
        print(f"✅ Success: {result}")
    else:
        print("❌ Failed")
