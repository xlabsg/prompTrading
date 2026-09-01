"""Audio transcription using OpenAI Whisper (local model)."""

import logging
import os
from typing import Optional

import torch
import whisper

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""
    pass


class WhisperTranscriber:
    """Whisper-based audio transcriber with caching."""

    def __init__(self, model_name: str = "base", device: Optional[str] = None):
        """Initialize Whisper transcriber.

        Args:
            model_name: Whisper model size (tiny, base, small, medium, large)
                       - tiny: fastest, lowest accuracy (~1GB RAM)
                       - base: good balance (~1GB RAM) [DEFAULT]
                       - small: better accuracy (~2GB RAM)
                       - medium: high accuracy (~5GB RAM)
                       - large: best accuracy (~10GB RAM)
            device: Device to run model on ('cuda', 'cpu', or None for auto-detect)
        """
        self.model_name = model_name

        # Auto-detect device
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        logger.info(f"Initializing Whisper model: {model_name} on {self.device}")

        try:
            self.model = whisper.load_model(model_name, device=self.device)
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise TranscriptionError(f"Model initialization failed: {str(e)}")

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> str:
        """Transcribe audio file to text.

        Args:
            audio_path: Path to audio file
            language: Language code (e.g., 'en', 'zh'). Auto-detected if None.
            task: 'transcribe' or 'translate' (to English)

        Returns:
            Transcribed text

        Raises:
            TranscriptionError: If transcription fails
        """
        if not os.path.exists(audio_path):
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        logger.info(f"Transcribing audio: {audio_path}")

        try:
            # Whisper transcription options
            options = {
                "task": task,
                "language": language,
                "fp16": self.device == "cuda",  # Use FP16 on GPU for speed
            }

            result = self.model.transcribe(audio_path, **options)

            text = result["text"].strip()
            detected_language = result.get("language", "unknown")

            logger.info(f"Transcription completed. Language: {detected_language}, Length: {len(text)} chars")

            return text

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise TranscriptionError(f"Failed to transcribe audio: {str(e)}")


# Global transcriber instance (lazy initialization)
_transcriber: Optional[WhisperTranscriber] = None


def transcribe_audio(
    audio_path: str,
    model_name: str = "base",
    language: Optional[str] = None,
) -> str:
    """Transcribe audio file to text using Whisper.

    This is a convenience function that uses a global transcriber instance
    to avoid reloading the model for each transcription.

    Args:
        audio_path: Path to audio file
        model_name: Whisper model size (tiny, base, small, medium, large)
        language: Language code (e.g., 'en', 'zh'). Auto-detected if None.

    Returns:
        Transcribed text

    Raises:
        TranscriptionError: If transcription fails

    Example:
        >>> text = transcribe_audio("audio.m4a", model_name="base")
        >>> print(text)
        'In this video, I will explain a trading strategy...'
    """
    global _transcriber

    # Initialize transcriber if not already done
    if _transcriber is None or _transcriber.model_name != model_name:
        _transcriber = WhisperTranscriber(model_name=model_name)

    return _transcriber.transcribe(audio_path, language=language)


def get_supported_models() -> list[str]:
    """Get list of supported Whisper model names.

    Returns:
        List of model names sorted by size
    """
    return ["tiny", "base", "small", "medium", "large"]


def estimate_transcription_time(duration_seconds: int, model_name: str = "base") -> int:
    """Estimate transcription time based on audio duration and model.

    Args:
        duration_seconds: Audio duration in seconds
        model_name: Whisper model size

    Returns:
        Estimated transcription time in seconds

    Note:
        This is a rough estimate. Actual time depends on hardware.
        - tiny: ~0.1x real-time (10 min audio = 1 min transcription)
        - base: ~0.2x real-time (10 min audio = 2 min transcription)
        - small: ~0.5x real-time (10 min audio = 5 min transcription)
        - medium: ~1.0x real-time (10 min audio = 10 min transcription)
        - large: ~2.0x real-time (10 min audio = 20 min transcription)
    """
    time_multipliers = {
        "tiny": 0.1,
        "base": 0.2,
        "small": 0.5,
        "medium": 1.0,
        "large": 2.0,
    }

    multiplier = time_multipliers.get(model_name, 0.2)
    return int(duration_seconds * multiplier)
