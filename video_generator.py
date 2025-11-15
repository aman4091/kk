#!/usr/bin/env python3
"""
Video Generator Module
Creates videos from image + audio with burned-in ASS subtitles
"""

import os
import subprocess
import whisper
import re
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

            # Transcribe audio
            result = self.whisper_model.transcribe(
                audio_path,
                task="transcribe",
                language="en",
                verbose=False
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
        """Write Whisper segments to SRT format"""
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                # Subtitle index
                f.write(f"{i}\n")

                # Timestamp
                start = self._format_timestamp(segment['start'])
                end = self._format_timestamp(segment['end'])
                f.write(f"{start} --> {end}\n")

                # Text
                f.write(f"{segment['text'].strip()}\n\n")

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

            # Step 1: Use FFmpeg to convert SRT → basic ASS
            cmd = ['ffmpeg', '-i', srt_path, '-y', output_ass_path]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"❌ FFmpeg SRT→ASS conversion failed: {result.stderr}")
                return None

            # Step 2: Inject custom ASS styling
            if ass_style:
                self._inject_ass_style(output_ass_path, ass_style)

            print(f"✅ ASS file created: {output_ass_path}")
            return output_ass_path

        except Exception as e:
            print(f"❌ SRT→ASS conversion error: {e}")
            return None

    def _inject_ass_style(self, ass_path, custom_style):
        """
        Inject custom ASS style into ASS file

        Args:
            ass_path: Path to ASS file
            custom_style: Full ASS style string (e.g., "Style: Banner,Arial,48,...")
        """
        try:
            with open(ass_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find [V4+ Styles] section and replace default style
            # Pattern: Style: Default,...
            pattern = r'(Style:\s*Default,)[^\n]+'

            # Extract style parameters from custom_style (remove "Style: Banner," prefix)
            # custom_style = "Style: Banner,Arial,48,&H00FFFFFF,..."
            # We want: "Default,Arial,48,&H00FFFFFF,..."
            if custom_style.startswith("Style:"):
                # Remove "Style: " and replace name with "Default"
                style_params = re.sub(r'Style:\s*\w+,', '', custom_style)
                replacement = r'\g<1>' + style_params
                content = re.sub(pattern, replacement, content)

            # Write back
            with open(ass_path, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"✅ Custom ASS style injected")

        except Exception as e:
            print(f"⚠️ ASS style injection failed: {e}")

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

    def create_video_with_subtitles(self, image_path, audio_path, output_path, ass_style=None):
        """
        Complete pipeline: Image + Audio → Video with subtitles

        Args:
            image_path: Path to image
            audio_path: Path to audio
            output_path: Final output video path
            ass_style: Optional custom ASS style

        Returns:
            str: Path to final video or None if failed
        """
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
            if not self.create_video_from_image_audio(image_path, audio_path, temp_video):
                return None

            # Step 2: Generate subtitles with Whisper
            print("\n📝 Step 2/4: Generating subtitles with Whisper...")
            if not self.generate_subtitles_whisper(audio_path, srt_path):
                return None

            # Step 3: Convert SRT → ASS with styling
            print("\n🎨 Step 3/4: Converting SRT → ASS with styling...")
            if not self.convert_srt_to_ass(srt_path, ass_style, ass_path):
                return None

            # Step 4: Burn subtitles into video
            print("\n🔥 Step 4/4: Burning subtitles into video...")
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

            print("\n" + "="*60)
            print(f"✅ VIDEO PIPELINE COMPLETE: {output_path}")
            print("="*60 + "\n")

            return output_path

        except Exception as e:
            print(f"\n❌ Video pipeline error: {e}")
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
