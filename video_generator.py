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
        """Initialize video generator with Whisper model and GPU detection"""
        self.whisper_model = None
        self.gpu_encoder = self._detect_gpu_encoder()
        print("✅ VideoGenerator initialized")

    def _detect_gpu_encoder(self):
        """Detect available NVIDIA hardware encoder for FFmpeg"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True,
                text=True,
                timeout=5
            )

            # Check for NVENC encoders
            if 'h264_nvenc' in result.stdout:
                print("🚀 GPU Encoder: NVIDIA h264_nvenc detected")
                return 'h264_nvenc'
            else:
                print("⚠️  GPU Encoder: Not found, using CPU (libx264)")
                return 'libx264'
        except Exception as e:
            print(f"⚠️  GPU Encoder detection failed: {e}, using CPU (libx264)")
            return 'libx264'

    def load_whisper_model(self, model_size="base"):
        """Load Whisper model for subtitle generation with GPU support"""
        if not self.whisper_model:
            # Auto-detect GPU availability for Whisper
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                print(f"🔄 Loading Whisper model ({model_size}) on {device.upper()}...")
                self.whisper_model = whisper.load_model(model_size, device=device)
                print(f"✅ Whisper model loaded on {device.upper()}")
            except Exception as e:
                # Fallback to CPU if GPU fails
                print(f"⚠️  GPU loading failed, using CPU: {e}")
                self.whisper_model = whisper.load_model(model_size)
                print("✅ Whisper model loaded on CPU")
        return self.whisper_model

    def _get_audio_duration(self, audio_path):
        """Get audio duration in seconds using FFprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return float(result.stdout.strip())
        except:
            return 0

    def _get_video_duration(self, video_path):
        """Get video duration in seconds using FFprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return float(result.stdout.strip())
        except:
            return 0

    def create_video_from_image_audio(self, image_path, audio_path, output_path, progress_callback=None):
        """
        Create MP4 video from static image + audio with real-time progress

        Args:
            image_path: Path to image file
            audio_path: Path to audio file (WAV/MP3)
            output_path: Output video path (MP4)
            progress_callback: Optional function(percentage, message) for progress updates

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

            # Get audio duration for progress calculation
            duration = self._get_audio_duration(audio_path)

            # FFmpeg command: Loop image for duration of audio with GPU encoding
            cmd = [
                'ffmpeg',
                '-loop', '1',                     # Loop image
                '-i', image_path,                 # Input image
                '-i', audio_path,                 # Input audio
                '-c:v', self.gpu_encoder,         # Video codec (GPU if available)
            ]

            # Add GPU-specific flags for NVENC
            if self.gpu_encoder == 'h264_nvenc':
                cmd.extend([
                    '-preset', 'p4',              # NVENC preset (p1=fast, p7=slow/quality)
                    '-tune', 'hq',                # High quality tuning
                    '-rc', 'vbr',                 # Variable bitrate
                    '-cq', '23',                  # Quality level (lower=better, 23=good)
                    '-b:v', '5M',                 # Target bitrate
                ])
            else:
                # CPU encoding options (libx264)
                cmd.extend([
                    '-tune', 'stillimage',        # Optimize for still image
                ])

            # Common options
            cmd.extend([
                '-c:a', 'aac',                    # Audio codec
                '-b:a', '192k',                   # Audio bitrate
                '-pix_fmt', 'yuv420p',            # Pixel format (compatibility)
                '-shortest',                      # Match shortest input (audio duration)
                '-progress', 'pipe:1',            # Enable progress output
                '-y',                             # Overwrite output
                output_path
            ])

            # Run FFmpeg with real-time progress monitoring
            print(f"🔍 DEBUG: Starting FFmpeg process...")
            print(f"🔍 DEBUG: Encoder: {self.gpu_encoder}")
            print(f"🔍 DEBUG: Command: {' '.join(cmd[:10])}...")  # First 10 args

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     universal_newlines=True, bufsize=1)
            print(f"🔍 DEBUG: Process started, PID: {process.pid}")

            # Monitor progress with throttling to avoid spamming Telegram API
            last_reported = 0  # Track last reported percentage
            last_progress_time = 0
            import time

            try:
                for line in process.stdout:
                    if line.startswith('out_time_ms='):
                        # Extract current time in microseconds
                        time_ms = int(line.split('=')[1])
                        current_time = time_ms / 1000000  # Convert to seconds

                        if duration > 0:
                            percentage = min(100, (current_time / duration) * 100)

                            # Throttle: Only update every 5% to avoid API rate limits
                            if percentage - last_reported >= 5.0 or percentage >= 99.9:
                                print(f"\r📹 Video creation progress: {percentage:.1f}%", end='', flush=True)
                                print(f" (time: {current_time:.1f}/{duration:.1f}s)", flush=True)

                                if progress_callback:
                                    progress_callback(percentage, f"Creating video: {percentage:.1f}%")

                                last_reported = percentage
                                last_progress_time = time.time()

                    # Check for stalled progress (no update in 30 seconds)
                    if last_progress_time > 0 and (time.time() - last_progress_time) > 30:
                        print(f"\n⚠️ WARNING: No progress update for 30 seconds! Last: {last_reported:.1f}%")
                        print(f"🔍 DEBUG: Checking if FFmpeg is still alive...")
                        if process.poll() is not None:
                            print(f"❌ FFmpeg process died! Return code: {process.returncode}")
                            break
                        last_progress_time = time.time()  # Reset timer

            except Exception as e:
                print(f"\n❌ Error during progress monitoring: {e}")
                import traceback
                traceback.print_exc()

            process.wait()
            print()  # New line after progress

            # Capture stderr for detailed error info
            stderr = process.stderr.read()

            if process.returncode == 0:
                print(f"✅ Video created: {output_path}")
                return True
            else:
                print(f"❌ FFmpeg failed with return code: {process.returncode}")
                print(f"🔍 DEBUG: FFmpeg stderr output:")
                print("=" * 80)
                print(stderr[-2000:] if len(stderr) > 2000 else stderr)  # Last 2000 chars
                print("=" * 80)
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
                ass_style = 'Style: Default,Arial,48,&H00FFFFFF,&H00FFFFFF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,4,0,0,5,40,40,40,1'

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

    def _parse_ass_style(self, ass_style):
        """
        Parse ASS style string to extract key parameters

        Args:
            ass_style: ASS style string (e.g., "Style: Default,Arial,48,...")

        Returns:
            dict: Parsed style parameters
        """
        # Default values
        params = {
            'fontsize': 48,
            'alignment': 5,  # Middle-center
            'marginv': 40,
            'marginl': 40,
            'marginr': 40,
            'back_color': '&H80000000'  # Semi-transparent black
        }

        try:
            # Parse style string
            # Format: Style: Name,Fontname,Fontsize,...,Alignment,MarginL,MarginR,MarginV,Encoding
            parts = ass_style.split(',')
            if len(parts) >= 22:
                params['fontsize'] = int(parts[2])
                params['back_color'] = parts[6]  # BackColour
                params['alignment'] = int(parts[18])
                params['marginl'] = int(parts[19])
                params['marginr'] = int(parts[20])
                params['marginv'] = int(parts[21])
        except:
            pass  # Use defaults if parsing fails

        return params

    def _calculate_box_dimensions(self, text, style_params):
        r"""
        Calculate box dimensions and position for ASS drawing

        Args:
            text: Text content (with \N line breaks)
            style_params: Parsed style parameters

        Returns:
            dict: Box dimensions and position
        """
        # Parse text into lines
        lines = text.split('\\N')
        line_count = len(lines)

        # Font metrics estimation
        fontsize = style_params['fontsize']
        line_height = int(fontsize * 1.2)  # Typical line height is 120% of font size

        # Calculate text dimensions
        # Estimate average character width as 52% of font size (reduced from 60% for tighter fit)
        char_width = fontsize * 0.52
        max_line_length = max(len(line) for line in lines)
        text_width = int(max_line_length * char_width)
        text_height = int(line_count * line_height)

        # Add padding (15px horizontal, 18px vertical - reduced for narrower box)
        padding_h = 15
        padding_v = 18
        box_width = text_width + (2 * padding_h)
        box_height = text_height + (2 * padding_v)

        # Resolution (from ASS header)
        res_x = 1920
        res_y = 1080

        # Calculate position based on alignment
        alignment = style_params['alignment']
        marginl = style_params['marginl']
        marginr = style_params['marginr']
        marginv = style_params['marginv']

        # Horizontal position (1=left, 2=center, 3=right for alignment)
        h_align = ((alignment - 1) % 3) + 1
        if h_align == 1:  # Left
            x1 = marginl
        elif h_align == 2:  # Center
            x1 = (res_x - box_width) // 2
        else:  # Right (3)
            x1 = res_x - marginr - box_width

        # Vertical position (1-3=bottom, 4-6=middle, 7-9=top)
        v_align = (alignment - 1) // 3
        if v_align == 0:  # Bottom (1-3)
            y1 = res_y - marginv - box_height
        elif v_align == 1:  # Middle (4-6)
            y1 = (res_y - box_height) // 2
        else:  # Top (7-9)
            y1 = marginv

        x2 = x1 + box_width
        y2 = y1 + box_height

        return {
            'x1': x1,
            'y1': y1,
            'x2': x2,
            'y2': y2,
            'width': box_width,
            'height': box_height,
            'corner_radius': 25  # Medium rounded corners
        }

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
        # ASS file header (minimal, matches working banner.ass)
        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
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

        # Parse ASS style to get parameters
        style_params = self._parse_ass_style(ass_style)

        # Parse SRT and convert to ASS events with single unified box
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
            # Use \N (ASS line break) for multi-line text
            text = '\\N'.join(lines[2:])

            # Calculate box dimensions and position
            box = self._calculate_box_dimensions(text, style_params)

            # Get background color from style (convert ASS color format)
            back_color = style_params['back_color']
            # ASS color format: &HAABBGGRR (alpha, blue, green, red in hex)
            # For drawing, we need &HAABBGGRR format as-is

            # Event 1: Draw background box with rounded corners (Layer 0)
            # ASS Drawing commands: m (move), l (line), b (bezier curve for rounded corners)
            # Rounded rectangle using bezier curves at corners
            r = box['corner_radius']
            x1, y1, x2, y2 = box['x1'], box['y1'], box['x2'], box['y2']

            # Draw rounded rectangle path (clockwise from top-left after corner)
            # Format: m start_x start_y l ... b cx1 cy1 cx2 cy2 x y (bezier curve)
            drawing_cmd = (
                f"m {x1+r} {y1} "  # Start: top edge after left corner
                f"l {x2-r} {y1} "  # Top edge to right corner
                f"b {x2} {y1} {x2} {y1} {x2} {y1+r} "  # Top-right corner (bezier)
                f"l {x2} {y2-r} "  # Right edge
                f"b {x2} {y2} {x2} {y2} {x2-r} {y2} "  # Bottom-right corner
                f"l {x1+r} {y2} "  # Bottom edge
                f"b {x1} {y2} {x1} {y2} {x1} {y2-r} "  # Bottom-left corner
                f"l {x1} {y1+r} "  # Left edge
                f"b {x1} {y1} {x1} {y1} {x1+r} {y1}"   # Top-left corner (close)
            )

            # Drawing tags:
            # \p1 = enable drawing mode
            # \an7 = top-left alignment (for absolute positioning)
            # \pos(0,0) = position at origin (drawing uses absolute coords)
            # \1c = primary color (fill color)
            # \3a&HFF& = hide border (fully transparent outline)
            # \bord0 = no border
            # \shad0 = no shadow
            box_event = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{{\\p1\\an7\\pos(0,0)\\1c{back_color}\\3a&HFF&\\bord0\\shad0}}{drawing_cmd}"
            ass_events.append(box_event)

            # Event 2: Draw text on top (Layer 1)
            # Disable box rendering for text: \bord0 (no border), \shad0 (no shadow), \3a&HFF& (transparent outline)
            # Use alignment from style
            text_event = f"Dialogue: 1,{start_time},{end_time},Default,,0,0,0,,{{\\bord0\\shad0\\3a&HFF&}}{text}"
            ass_events.append(text_event)

        # Combine header + events
        return ass_header + '\n'.join(ass_events)

    def burn_subtitles(self, video_path, ass_path, output_path, progress_callback=None):
        """
        Burn ASS subtitles into video with real-time progress

        Args:
            video_path: Input video path
            ass_path: ASS subtitle file path
            output_path: Output video with burned subtitles
            progress_callback: Optional function(percentage, message) for progress updates

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

            # Get video duration for progress calculation
            duration = self._get_video_duration(video_path)

            # FFmpeg command: Burn ASS subtitles
            # Use absolute path for ASS file to avoid path issues
            ass_abs_path = os.path.abspath(ass_path)

            # Windows path fix for FFmpeg (convert \ to / and escape :)
            if os.name == 'nt':
                ass_abs_path = ass_abs_path.replace('\\', '/').replace(':', '\\:')

            # FFmpeg command: Burn ASS subtitles with GPU encoding
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vf', f"ass={ass_abs_path}",
                '-c:v', self.gpu_encoder,       # Video codec (GPU if available)
            ]

            # Add GPU-specific flags for NVENC
            if self.gpu_encoder == 'h264_nvenc':
                cmd.extend([
                    '-preset', 'p4',            # NVENC preset (balanced speed/quality)
                    '-tune', 'hq',              # High quality tuning
                    '-rc', 'vbr',               # Variable bitrate
                    '-cq', '23',                # Quality level
                    '-b:v', '5M',               # Target bitrate
                ])

            # Common options
            cmd.extend([
                '-c:a', 'copy',                 # Copy audio (no re-encode)
                '-progress', 'pipe:1',          # Enable progress output
                '-y',
                output_path
            ])

            # Run FFmpeg with real-time progress monitoring
            print(f"🔍 DEBUG: Starting subtitle burning...")
            print(f"🔍 DEBUG: Encoder: {self.gpu_encoder}")

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     universal_newlines=True, bufsize=1)
            print(f"🔍 DEBUG: Process started, PID: {process.pid}")

            # Monitor progress with throttling to avoid spamming Telegram API
            last_reported = 0  # Track last reported percentage
            last_progress_time = 0
            import time

            try:
                for line in process.stdout:
                    if line.startswith('out_time_ms='):
                        # Extract current time in microseconds
                        time_ms = int(line.split('=')[1])
                        current_time = time_ms / 1000000  # Convert to seconds

                        if duration > 0:
                            percentage = min(100, (current_time / duration) * 100)

                            # Throttle: Only update every 5% to avoid API rate limits
                            if percentage - last_reported >= 5.0 or percentage >= 99.9:
                                print(f"\r🔥 Subtitle burning progress: {percentage:.1f}%", end='', flush=True)
                                print(f" (time: {current_time:.1f}/{duration:.1f}s)", flush=True)

                                if progress_callback:
                                    progress_callback(percentage, f"Burning subtitles: {percentage:.1f}%")

                                last_reported = percentage
                                last_progress_time = time.time()

                    # Check for stalled progress
                    if last_progress_time > 0 and (time.time() - last_progress_time) > 30:
                        print(f"\n⚠️ WARNING: No progress update for 30 seconds! Last: {last_reported:.1f}%")
                        if process.poll() is not None:
                            print(f"❌ FFmpeg process died! Return code: {process.returncode}")
                            break
                        last_progress_time = time.time()

            except Exception as e:
                print(f"\n❌ Error during subtitle burning monitoring: {e}")
                import traceback
                traceback.print_exc()

            process.wait()
            print()  # New line after progress

            # Capture stderr
            stderr = process.stderr.read()

            if process.returncode == 0:
                print(f"✅ Subtitles burned: {output_path}")
                return True
            else:
                print(f"❌ FFmpeg failed with return code: {process.returncode}")
                print(f"🔍 DEBUG: FFmpeg stderr output:")
                print("=" * 80)
                print(stderr[-2000:] if len(stderr) > 2000 else stderr)
                print("=" * 80)
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
            send_progress("📹 [0-25%] Creating video from image + audio...")

            # Progress callback for video creation (0-25% range)
            def video_progress(pct, msg):
                scaled_pct = pct * 0.25  # Scale to 0-25%
                send_progress(f"📹 [{scaled_pct:.1f}%] {msg}")

            if not self.create_video_from_image_audio(image_path, audio_path, temp_video, progress_callback=video_progress):
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
            send_progress("🔥 [75-100%] Burning subtitles into video...")

            # Progress callback for subtitle burning (75-100% range)
            def burn_progress(pct, msg):
                scaled_pct = 75 + (pct * 0.25)  # Scale to 75-100%
                send_progress(f"🔥 [{scaled_pct:.1f}%] {msg}")

            if not self.burn_subtitles(temp_video, ass_path, output_path, progress_callback=burn_progress):
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
