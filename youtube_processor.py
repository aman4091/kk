#!/usr/bin/env python3
"""
YouTube Channel Processor
=========================
Handles YouTube channel processing including:
- Channel URL detection
- Fetching top 1000 videos (sorted by views, >10min duration)
- Selecting 6 unique videos (15-day cooldown)
- Text chunking at 7000 characters
- Orchestrating full processing pipeline
"""

import os
import re
import json
from typing import List, Dict, Optional, Tuple
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import isodate  # For parsing ISO 8601 duration format

class YouTubeProcessorError(Exception):
    """Custom exception for YouTube processor errors"""
    pass

class YouTubeChannelProcessor:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize YouTube processor with API key"""
        self.api_key = api_key
        self.youtube = None
        if api_key:
            try:
                self.youtube = build('youtube', 'v3', developerKey=api_key)
                print("✅ YouTube API client initialized")
            except Exception as e:
                print(f"❌ YouTube API initialization error: {e}")

    def set_api_key(self, api_key: str):
        """Update YouTube API key"""
        self.api_key = api_key
        try:
            self.youtube = build('youtube', 'v3', developerKey=api_key)
            print("✅ YouTube API key updated")
        except Exception as e:
            print(f"❌ YouTube API key update error: {e}")

    # =============================================================================
    # URL DETECTION & EXTRACTION
    # =============================================================================

    @staticmethod
    def is_youtube_channel_url(url: str) -> bool:
        """
        Detect if URL is a YouTube channel URL.
        Matches:
        - youtube.com/@username
        - youtube.com/c/channelname
        - youtube.com/channel/UCxxxxxxx
        - youtube.com/user/username
        """
        channel_patterns = [
            r'youtube\.com/@[\w-]+',
            r'youtube\.com/c/[\w-]+',
            r'youtube\.com/channel/UC[\w-]+',
            r'youtube\.com/user/[\w-]+'
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in channel_patterns)

    @staticmethod
    def is_youtube_video_url(url: str) -> bool:
        """
        Detect if URL is a YouTube video URL.
        Matches:
        - youtube.com/watch?v=xxxxx
        - youtu.be/xxxxx
        """
        video_patterns = [
            r'youtube\.com/watch\?v=[\w-]+',
            r'youtu\.be/[\w-]+'
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in video_patterns)

    def extract_channel_id(self, channel_url: str) -> Optional[str]:
        """
        Extract channel ID from various YouTube channel URL formats.
        Returns channel ID (starting with UC) or None if extraction fails.
        """
        if not self.youtube:
            print("❌ YouTube API not initialized")
            return None

        try:
            # Format 1: Direct channel ID (youtube.com/channel/UCxxxxxxx)
            match = re.search(r'youtube\.com/channel/(UC[\w-]+)', channel_url)
            if match:
                return match.group(1)

            # Format 2: Custom URL (@username, /c/, /user/)
            # Extract the identifier
            username = None
            if '@' in channel_url:
                match = re.search(r'@([\w-]+)', channel_url)
                if match:
                    username = match.group(1)
            elif '/c/' in channel_url:
                match = re.search(r'/c/([\w-]+)', channel_url)
                if match:
                    username = match.group(1)
            elif '/user/' in channel_url:
                match = re.search(r'/user/([\w-]+)', channel_url)
                if match:
                    username = match.group(1)

            if username:
                # Search for channel by username/handle
                request = self.youtube.search().list(
                    part='snippet',
                    q=username,
                    type='channel',
                    maxResults=1
                )
                response = request.execute()

                if response.get('items'):
                    return response['items'][0]['snippet']['channelId']

            print(f"❌ Could not extract channel ID from: {channel_url}")
            return None

        except HttpError as e:
            print(f"❌ YouTube API error extracting channel ID: {e}")
            return None
        except Exception as e:
            print(f"❌ Error extracting channel ID: {e}")
            return None

    # =============================================================================
    # FETCH VIDEOS FROM CHANNEL
    # =============================================================================

    def fetch_channel_videos(self, channel_id: str, max_results: int = 1000) -> List[Dict]:
        """
        Fetch up to 1000 videos from a channel.
        Returns list of video metadata dicts with:
        - video_id
        - title
        - published_at
        - view_count
        - duration (in seconds)
        - url
        """
        if not self.youtube:
            raise YouTubeProcessorError("YouTube API not initialized")

        all_videos = []
        next_page_token = None

        try:
            print(f"🔍 Fetching videos from channel: {channel_id}")

            # Step 1: Get channel's uploads playlist ID
            channel_request = self.youtube.channels().list(
                part='contentDetails,snippet',
                id=channel_id
            )
            channel_response = channel_request.execute()

            if not channel_response.get('items'):
                print(f"❌ Channel not found: {channel_id}")
                return []

            channel_name = channel_response['items'][0]['snippet']['title']
            uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

            print(f"✅ Channel: {channel_name}")
            print(f"📺 Fetching from uploads playlist: {uploads_playlist_id}")

            # Step 2: Fetch videos from uploads playlist (paginated)
            fetched_count = 0
            while fetched_count < max_results:
                playlist_request = self.youtube.playlistItems().list(
                    part='snippet',
                    playlistId=uploads_playlist_id,
                    maxResults=min(50, max_results - fetched_count),  # Max 50 per request
                    pageToken=next_page_token
                )
                playlist_response = playlist_request.execute()

                video_ids = [item['snippet']['resourceId']['videoId'] for item in playlist_response.get('items', [])]

                if video_ids:
                    # Step 3: Get detailed video statistics and duration
                    videos_request = self.youtube.videos().list(
                        part='snippet,contentDetails,statistics',
                        id=','.join(video_ids)
                    )
                    videos_response = videos_request.execute()

                    for video in videos_response.get('items', []):
                        video_data = self._parse_video_data(video)
                        if video_data:
                            all_videos.append(video_data)
                            fetched_count += 1

                next_page_token = playlist_response.get('nextPageToken')
                if not next_page_token:
                    break

                print(f"📊 Fetched {fetched_count} videos so far...")

            print(f"✅ Total videos fetched: {len(all_videos)}")
            return all_videos

        except HttpError as e:
            print(f"❌ YouTube API error: {e}")
            return []
        except Exception as e:
            print(f"❌ Error fetching videos: {e}")
            return []

    def _parse_video_data(self, video: Dict) -> Optional[Dict]:
        """Parse video data from YouTube API response"""
        try:
            video_id = video['id']
            snippet = video['snippet']
            stats = video.get('statistics', {})
            duration_iso = video['contentDetails']['duration']

            # Parse ISO 8601 duration to seconds
            duration = isodate.parse_duration(duration_iso).total_seconds()

            return {
                'video_id': video_id,
                'title': snippet['title'],
                'published_at': snippet['publishedAt'],
                'view_count': int(stats.get('viewCount', 0)),
                'duration': int(duration),  # in seconds
                'url': f"https://www.youtube.com/watch?v={video_id}"
            }
        except Exception as e:
            print(f"⚠️ Error parsing video data: {e}")
            return None

    def filter_and_sort_videos(self, videos: List[Dict], min_duration_minutes: int = 10) -> List[Dict]:
        """
        Filter videos by duration and sort by view count.

        Args:
            videos: List of video dicts
            min_duration_minutes: Minimum duration in minutes (default: 10)

        Returns:
            Filtered and sorted list (highest views first)
        """
        min_duration_seconds = min_duration_minutes * 60

        # Filter by duration
        filtered = [v for v in videos if v['duration'] >= min_duration_seconds]

        print(f"📊 Filtered: {len(filtered)}/{len(videos)} videos (duration ≥ {min_duration_minutes} min)")

        # Sort by view count (descending)
        sorted_videos = sorted(filtered, key=lambda x: x['view_count'], reverse=True)

        return sorted_videos

    # =============================================================================
    # VIDEO SELECTION WITH 15-DAY COOLDOWN
    # =============================================================================

    def select_unique_videos(self, videos: List[Dict], unprocessed_ids: List[str],
                            count: int = 6) -> List[Dict]:
        """
        Select top N videos that haven't been processed recently.

        Args:
            videos: Sorted list of videos (by views, filtered by duration)
            unprocessed_ids: List of video IDs that are safe to process
            count: Number of videos to select (default: 6)

        Returns:
            List of selected video dicts
        """
        selected = []

        for video in videos:
            if video['video_id'] in unprocessed_ids:
                selected.append(video)
                if len(selected) >= count:
                    break

        print(f"✅ Selected {len(selected)}/{count} unique videos")
        return selected

    # =============================================================================
    # TEXT CHUNKING
    # =============================================================================

    @staticmethod
    def chunk_text_at_fullstop(text: str, max_chars: int = 7000) -> List[str]:
        """
        Chunk text at nearest fullstop within character limit.

        Args:
            text: Input text to chunk
            max_chars: Maximum characters per chunk (default: 7000)

        Returns:
            List of text chunks
        """
        if len(text) <= max_chars:
            return [text]

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= max_chars:
                chunks.append(remaining.strip())
                break

            # Find chunk up to max_chars
            chunk = remaining[:max_chars]

            # Find last fullstop/period in chunk
            last_period = max(
                chunk.rfind('. '),
                chunk.rfind('.\n'),
                chunk.rfind('? '),
                chunk.rfind('! ')
            )

            if last_period > max_chars * 0.5:  # At least 50% of max_chars
                # Split at sentence boundary
                split_point = last_period + 1
                chunks.append(remaining[:split_point].strip())
                remaining = remaining[split_point:].strip()
            else:
                # No good split point, force split at max_chars
                chunks.append(chunk.strip())
                remaining = remaining[max_chars:].strip()

        print(f"📦 Text chunked into {len(chunks)} parts")
        return chunks

    # =============================================================================
    # HELPER: SAVE CHUNKS TO DISK
    # =============================================================================

    @staticmethod
    def save_chunks_to_disk(chunks: List[str], video_id: str, base_dir: str) -> List[str]:
        """
        Save chunks to disk in video-specific directory.

        Args:
            chunks: List of text chunks
            video_id: YouTube video ID
            base_dir: Base directory (e.g., workspace/chunks/)

        Returns:
            List of saved file paths
        """
        video_dir = os.path.join(base_dir, video_id)
        os.makedirs(video_dir, exist_ok=True)

        saved_paths = []
        for i, chunk in enumerate(chunks, 1):
            chunk_path = os.path.join(video_dir, f"chunk_{i}.txt")
            with open(chunk_path, 'w', encoding='utf-8') as f:
                f.write(chunk)
            saved_paths.append(chunk_path)

        print(f"💾 Saved {len(chunks)} chunks to: {video_dir}")
        return saved_paths

    @staticmethod
    def save_merged_script(merged_text: str, video_id: str, base_dir: str) -> str:
        """
        Save merged/processed script to disk.

        Args:
            merged_text: Final merged script
            video_id: YouTube video ID
            base_dir: Base directory

        Returns:
            Path to saved merged script
        """
        video_dir = os.path.join(base_dir, video_id)
        os.makedirs(video_dir, exist_ok=True)

        merged_path = os.path.join(video_dir, "merged_final.txt")
        with open(merged_path, 'w', encoding='utf-8') as f:
            f.write(merged_text)

        print(f"💾 Saved merged script: {merged_path}")
        return merged_path

    # =============================================================================
    # FULL PIPELINE ORCHESTRATION
    # =============================================================================

    def get_channel_top_videos(self, channel_url: str, count: int = 6,
                               min_duration_min: int = 10) -> Tuple[Optional[str], List[Dict]]:
        """
        Complete pipeline: Get top N videos from channel.

        Args:
            channel_url: YouTube channel URL
            count: Number of videos to return (default: 6)
            min_duration_min: Minimum video duration in minutes (default: 10)

        Returns:
            Tuple[channel_id, videos]: Channel ID and list of video dicts
        """
        # Step 1: Extract channel ID
        channel_id = self.extract_channel_id(channel_url)
        if not channel_id:
            print("❌ Failed to extract channel ID")
            return None, []

        # Step 2: Fetch all videos (up to 1000)
        all_videos = self.fetch_channel_videos(channel_id, max_results=1000)
        if not all_videos:
            print("❌ No videos fetched")
            return channel_id, []

        # Step 3: Filter by duration and sort by views
        filtered_videos = self.filter_and_sort_videos(all_videos, min_duration_minutes=min_duration_min)

        print(f"✅ Pipeline complete: {len(filtered_videos)} videos ready")
        return channel_id, filtered_videos
