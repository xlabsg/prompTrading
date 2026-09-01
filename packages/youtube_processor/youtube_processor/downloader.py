"""YouTube video audio downloader using yt-dlp."""

import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

import yt_dlp

logger = logging.getLogger(__name__)


def _get_ydl_opts(base_opts: Optional[Dict] = None) -> Dict:
    """Build yt-dlp options with anti-bot measures for SaaS service.

    Uses yt-dlp's built-in features to avoid YouTube bot detection without
    requiring cookies from individual users.

    Args:
        base_opts: Base options to override

    Returns:
        Complete yt-dlp options dictionary
    """
    opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        # Realistic user agent - use mobile UA (less strict)
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        # Anti-bot measures - try multiple client types
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'mediaconnect'],  # Try multiple clients in order
            }
        },
        # Rate limiting to avoid triggering bot detection
        'sleep_interval': 2,  # Sleep 2 seconds between requests (increased)
        'max_sleep_interval': 5,  # Maximum random sleep (increased)
        # Retry configuration
        'retries': 10,  # More retries
        'fragment_retries': 10,
        # Don't ignore errors - we want to catch them
        'ignoreerrors': False,
        # Format selection
        'format': 'bestaudio/best',
        # Additional anti-detection
        'geo_bypass': True,  # Bypass geographic restrictions
        'no_playlist': True,  # Only download single video
    }

    # Optional: Allow admin to configure cookies for the service
    # (NOT for individual users, but for the service itself)
    cookies_file = os.getenv('YOUTUBE_SERVICE_COOKIES_FILE')
    if cookies_file and os.path.exists(cookies_file):
        logger.info(f"Using service-level cookies: {cookies_file}")
        opts['cookiefile'] = cookies_file

    # Merge base options
    if base_opts:
        opts.update(base_opts)

    return opts


class VideoTooLongError(Exception):
    """Raised when video duration exceeds maximum allowed."""
    pass


class VideoDownloadError(Exception):
    """Raised when video download fails."""
    pass


def get_video_info(url: str) -> Dict:
    """Get YouTube video metadata without downloading.

    Args:
        url: YouTube video URL

    Returns:
        Dictionary containing video metadata:
        - id: Video ID
        - title: Video title
        - duration: Duration in seconds
        - uploader: Channel name
        - description: Video description
        - view_count: Number of views
        - like_count: Number of likes

    Raises:
        VideoDownloadError: If unable to fetch video info
    """
    ydl_opts = _get_ydl_opts({'extract_flat': True})

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Check if info is None (happens with ignoreerrors=True)
            if info is None:
                raise VideoDownloadError(
                    "Unable to fetch video information. "
                    "The video may be private, restricted, or YouTube is blocking automated access. "
                    "Please try again later or use a different video."
                )

            return {
                'id': info.get('id', ''),
                'title': info.get('title', ''),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', ''),
                'description': info.get('description', ''),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'thumbnail': info.get('thumbnail', ''),
            }
    except VideoDownloadError:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to get video info: {error_msg}")

        # Check for common errors and provide helpful messages
        if "Sign in to confirm you're not a bot" in error_msg or "bot" in error_msg.lower():
            raise VideoDownloadError(
                "YouTube is temporarily blocking automated access. "
                "This is a known limitation of YouTube's bot detection. "
                "Please try again later or use an alternative video source."
            )
        elif "HTTP Error 403" in error_msg or "forbidden" in error_msg.lower():
            raise VideoDownloadError(
                "The video is private, region-restricted, or not available. "
                "Please check the video URL or try a different video."
            )
        elif "Video unavailable" in error_msg or "not found" in error_msg.lower():
            raise VideoDownloadError(
                "The video is not available. It may have been deleted or made private."
            )
        else:
            raise VideoDownloadError(f"Unable to fetch video information: {error_msg}")


def download_audio(
    url: str,
    output_dir: Optional[str] = None,
    max_duration: int = 1800,
) -> str:
    """Download audio from YouTube video.

    Args:
        url: YouTube video URL
        output_dir: Directory to save audio file (uses temp dir if None)
        max_duration: Maximum allowed video duration in seconds (default: 1800 = 30 min)

    Returns:
        Path to downloaded audio file (.m4a format)

    Raises:
        VideoTooLongError: If video exceeds max_duration
        VideoDownloadError: If download fails
    """
    # First, check video duration
    video_info = get_video_info(url)
    duration = video_info.get('duration', 0)

    if duration > max_duration:
        raise VideoTooLongError(
            f"Video duration ({duration}s) exceeds maximum allowed ({max_duration}s). "
            f"Please use a shorter video (max {max_duration // 60} minutes)."
        )

    logger.info(f"Downloading audio from: {video_info['title']} ({duration}s)")

    # Create output directory
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="youtube_audio_")
    else:
        os.makedirs(output_dir, exist_ok=True)

    output_template = os.path.join(output_dir, '%(id)s.%(ext)s')

    ydl_opts = _get_ydl_opts({
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }],
    })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get('id', 'audio')

            # yt-dlp saves as .m4a after post-processing
            audio_path = os.path.join(output_dir, f"{video_id}.m4a")

            if not os.path.exists(audio_path):
                raise VideoDownloadError(f"Downloaded audio file not found: {audio_path}")

            logger.info(f"Audio downloaded successfully: {audio_path}")
            return audio_path

    except VideoTooLongError:
        raise
    except VideoDownloadError:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error during download: {error_msg}")

        if "Sign in to confirm you're not a bot" in error_msg or "bot" in error_msg.lower():
            raise VideoDownloadError(
                "YouTube is temporarily blocking automated access. "
                "This is a known limitation. Please try again later or use a different video."
            )
        else:
            raise VideoDownloadError(f"Download failed: {error_msg}")


def validate_youtube_url(url: str) -> bool:
    """Validate if URL is a valid YouTube URL.

    Args:
        url: URL to validate

    Returns:
        True if valid YouTube URL, False otherwise
    """
    youtube_domains = [
        'youtube.com',
        'www.youtube.com',
        'youtu.be',
        'm.youtube.com',
    ]

    url_lower = url.lower()
    return any(domain in url_lower for domain in youtube_domains)
