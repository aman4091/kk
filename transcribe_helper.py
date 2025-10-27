#!/usr/bin/env python3
"""
Transcribe Helper - Supadata API Integration
=============================================
Extracted from working transcribe.py (D:\am\Script\transcribe.py)
Handles YouTube transcript fetching via Supadata API with:
- Async job polling for large files
- Proper error handling
- Key rotation support
"""

import os
import time
import httpx
from typing import Optional, Tuple

class SupaDataError(Exception):
    """Custom exception for Supadata API errors"""
    pass

def _headers(api_key: str) -> dict:
    """Generate headers for Supadata API requests"""
    return {
        "x-api-key": api_key,
        "Accept": "application/json",
    }

async def get_youtube_transcript(video_url: str, api_key: str) -> Tuple[Optional[str], bool]:
    """
    Get transcript from Supadata API.

    Returns:
        Tuple[Optional[str], bool]: (transcript_text, is_key_exhausted)
        - transcript_text: The transcript or None if failed
        - is_key_exhausted: True if API key quota exhausted (429 error)
    """
    if not api_key:
        print("❌ Missing Supadata API key")
        return None, False

    try:
        # Correct endpoint according to Supadata docs
        url = "https://api.supadata.ai/v1/transcript"

        # Parameters according to docs
        params = {
            "url": video_url,
            "text": True,  # Return plain text instead of timestamped chunks
            "mode": "auto"  # Try native first, fallback to AI generation
        }

        print(f"[Supadata] Requesting transcript: {video_url[:50]}...")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url, params=params, headers=_headers(api_key))

            print(f"[Supadata] Response status: {response.status_code}")

            # Handle different status codes
            if response.status_code == 401:
                print("❌ 401 Unauthorized - Invalid API key")
                return None, False

            elif response.status_code == 429:
                print("⚠️ 429 Rate Limited - API key quota exhausted")
                return None, True  # Key exhausted!

            elif response.status_code == 202:
                # Async job - need to poll for results
                job_data = response.json()
                job_id = job_data.get("jobId")
                if not job_id:
                    print("❌ Got 202 but no job ID")
                    return None, False

                print(f"[Supadata] Large file detected, polling job: {job_id}")
                return await _poll_job_result(client, job_id, api_key)

            elif response.status_code >= 400:
                error_text = response.text[:200]
                print(f"❌ Supadata error {response.status_code}: {error_text}")
                return None, False

            elif response.status_code == 200:
                # Direct response - process transcript
                data = response.json()
                transcript = _extract_transcript_text(data)
                if transcript:
                    print(f"✅ Transcript received: {len(transcript)} characters")
                    return transcript, False
                else:
                    print("❌ No transcript content found in response")
                    return None, False
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                return None, False

    except httpx.TimeoutException:
        print("❌ Supadata request timeout")
        return None, False
    except Exception as e:
        print(f"❌ Supadata error: {e}")
        return None, False

async def _poll_job_result(client: httpx.AsyncClient, job_id: str, api_key: str) -> Tuple[Optional[str], bool]:
    """
    Poll for job results when Supadata returns a job ID (202 status).

    Returns:
        Tuple[Optional[str], bool]: (transcript_text, is_key_exhausted)
    """
    poll_url = f"https://api.supadata.ai/v1/transcript/{job_id}"

    max_attempts = 60  # 5 minutes max (60 * 5 seconds)
    attempt = 0

    while attempt < max_attempts:
        try:
            response = await client.get(poll_url, headers=_headers(api_key))

            if response.status_code == 429:
                print("⚠️ 429 during polling - API key quota exhausted")
                return None, True  # Key exhausted!

            if response.status_code == 200:
                data = response.json()
                status = data.get("status")

                if status == "completed":
                    print(f"[Supadata] Job completed successfully")
                    transcript = _extract_transcript_text(data)
                    if transcript:
                        print(f"✅ Transcript received: {len(transcript)} characters")
                        return transcript, False
                    else:
                        print("❌ No transcript in completed job")
                        return None, False

                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    print(f"❌ Job failed: {error}")
                    return None, False

                elif status in ["queued", "active"]:
                    print(f"[Supadata] Job status: {status}, waiting... ({attempt + 1}/{max_attempts})")
                    await asyncio_sleep(5)  # Wait 5 seconds before next poll
                    attempt += 1
                    continue
                else:
                    print(f"❌ Unknown job status: {status}")
                    return None, False
            else:
                print(f"❌ Job status check failed: {response.status_code}")
                return None, False

        except Exception as e:
            print(f"[Supadata] Poll attempt {attempt + 1} failed: {e}")
            attempt += 1
            await asyncio_sleep(5)

    print("❌ Job polling timeout - file may be too large or processing failed")
    return None, False

def _extract_transcript_text(data: dict) -> Optional[str]:
    """
    Extract transcript text from Supadata response.
    Handles different response formats.
    """
    # Primary format: 'content' field (text=true parameter)
    text = data.get("content", "")

    if not text:
        # Fallback formats
        text = data.get("text") or data.get("transcript") or ""

        if not text and "data" in data:
            if isinstance(data["data"], str):
                text = data["data"]
            elif isinstance(data["data"], dict):
                text = data["data"].get("content") or data["data"].get("text") or ""

    # Clean and return
    return text.strip() if text else None

async def asyncio_sleep(seconds: float):
    """Async sleep wrapper"""
    import asyncio
    await asyncio.sleep(seconds)

# =============================================================================
# SYNC VERSION (for non-async contexts)
# =============================================================================

def get_youtube_transcript_sync(video_url: str, api_key: str) -> Tuple[Optional[str], bool]:
    """
    Synchronous version of get_youtube_transcript.
    Uses httpx sync client instead of async.

    Returns:
        Tuple[Optional[str], bool]: (transcript_text, is_key_exhausted)
    """
    if not api_key:
        print("❌ Missing Supadata API key")
        return None, False

    try:
        url = "https://api.supadata.ai/v1/transcript"
        params = {
            "url": video_url,
            "text": True,
            "mode": "auto"
        }

        print(f"[Supadata] Requesting transcript: {video_url[:50]}...")

        with httpx.Client(timeout=120.0) as client:
            response = client.get(url, params=params, headers=_headers(api_key))

            print(f"[Supadata] Response status: {response.status_code}")

            if response.status_code == 401:
                print("❌ 401 Unauthorized - Invalid API key")
                return None, False

            elif response.status_code == 429:
                print("⚠️ 429 Rate Limited - API key quota exhausted")
                return None, True  # Key exhausted!

            elif response.status_code == 202:
                job_data = response.json()
                job_id = job_data.get("jobId")
                if not job_id:
                    print("❌ Got 202 but no job ID")
                    return None, False

                print(f"[Supadata] Large file detected, polling job: {job_id}")
                return _poll_job_result_sync(client, job_id, api_key)

            elif response.status_code >= 400:
                error_text = response.text[:200]
                print(f"❌ Supadata error {response.status_code}: {error_text}")
                return None, False

            elif response.status_code == 200:
                data = response.json()
                transcript = _extract_transcript_text(data)
                if transcript:
                    print(f"✅ Transcript received: {len(transcript)} characters")
                    return transcript, False
                else:
                    print("❌ No transcript content found in response")
                    return None, False
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                return None, False

    except httpx.TimeoutException:
        print("❌ Supadata request timeout")
        return None, False
    except Exception as e:
        print(f"❌ Supadata error: {e}")
        return None, False

def _poll_job_result_sync(client: httpx.Client, job_id: str, api_key: str) -> Tuple[Optional[str], bool]:
    """Synchronous version of job polling"""
    poll_url = f"https://api.supadata.ai/v1/transcript/{job_id}"
    max_attempts = 60
    attempt = 0

    while attempt < max_attempts:
        try:
            response = client.get(poll_url, headers=_headers(api_key))

            if response.status_code == 429:
                print("⚠️ 429 during polling - API key quota exhausted")
                return None, True

            if response.status_code == 200:
                data = response.json()
                status = data.get("status")

                if status == "completed":
                    print(f"[Supadata] Job completed successfully")
                    transcript = _extract_transcript_text(data)
                    if transcript:
                        print(f"✅ Transcript received: {len(transcript)} characters")
                        return transcript, False
                    else:
                        print("❌ No transcript in completed job")
                        return None, False

                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    print(f"❌ Job failed: {error}")
                    return None, False

                elif status in ["queued", "active"]:
                    print(f"[Supadata] Job status: {status}, waiting... ({attempt + 1}/{max_attempts})")
                    time.sleep(5)
                    attempt += 1
                    continue
                else:
                    print(f"❌ Unknown job status: {status}")
                    return None, False
            else:
                print(f"❌ Job status check failed: {response.status_code}")
                return None, False

        except Exception as e:
            print(f"[Supadata] Poll attempt {attempt + 1} failed: {e}")
            attempt += 1
            time.sleep(5)

    print("❌ Job polling timeout")
    return None, False
