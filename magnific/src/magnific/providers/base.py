"""Abstract provider interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from magnific.config.models import (
    StoryModelConfig,
    PreviewModelConfig,
    VideoModelConfig,
)
from magnific.core.manifest import ScenePrompt

if TYPE_CHECKING:
    from magnific.core.security import JailedPath


@dataclass
class StoryResult:
    """Result from story generation."""
    success: bool
    scenes: list[ScenePrompt]
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    estimated_input_tokens: Optional[int] = None


@dataclass
class ImageResult:
    """Result from image generation."""
    success: bool
    image_path: Optional[Path] = None
    error: Optional[str] = None
    generation_time_ms: Optional[int] = None


@dataclass
class VideoSubmissionResult:
    """Result from video submission."""
    success: bool
    operation_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class VideoPollResult:
    """Result from video polling."""
    success: bool
    video_path: Optional[Path] = None
    status: str = "pending"
    error: Optional[str] = None


class StoryProvider(ABC):
    """
    Interface for story/prompt generation.
    
    Implementations:
    - GoogleGeminiProvider
    - MockStoryProvider (for testing)
    """
    
    @abstractmethod
    def generate_scenes(
        self,
        reference_images: list["JailedPath"],
        brief: str,
        config: StoryModelConfig,
        system_prompt: str,
        user_template: str,
    ) -> StoryResult:
        """Generate scene prompts from reference images and brief."""
        pass


class ImageProvider(ABC):
    """
    Interface for preview image generation.
    
    Implementations:
    - GoogleImagenProvider
    - MockImageProvider (for testing)
    
    Design note: Image providers should implement a byte cache
    to prevent memory duplication when generating multiple scenes
    with the same reference images.
    """
    
    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        reference_images: list["JailedPath"],
        output_path: "JailedPath",
        config: PreviewModelConfig,
    ) -> ImageResult:
        """Generate a preview image for a scene."""
        pass
    
    def clear_cache(self) -> None:
        """Clear any cached reference image data."""
        pass
    
    def get_cached_bytes(self, path: "JailedPath") -> Optional[bytes]:
        """Get cached image bytes (memory optimization)."""
        return None


class VideoProvider(ABC):
    """
    Interface for video generation.
    
    Implementations:
    - GoogleVeoProvider
    - MockVideoProvider (for testing)
    
    Video generation is asynchronous:
    1. submit() -> operation_id
    2. poll(operation_id) -> status, video_path when complete
    """
    
    @abstractmethod
    def submit(
        self,
        preview_image: "JailedPath",
        prompt: str,
        config: VideoModelConfig,
    ) -> VideoSubmissionResult:
        """Submit a video generation request."""
        pass
    
    @abstractmethod
    def poll(
        self,
        operation_id: str,
        output_path: "JailedPath",
        timeout_seconds: float = 1800,
    ) -> VideoPollResult:
        """Poll for video completion and download."""
        pass
    
    @abstractmethod
    def check_status(self, operation_id: str) -> str:
        """Check operation status without downloading."""
        pass
    
    @abstractmethod
    async def poll_async(
        self,
        operation_id: str,
        output_path: "JailedPath",
        poll_interval: float = 10.0,
        backoff_multiplier: float = 1.5,
        max_poll_minutes: float = 30.0,
    ) -> VideoPollResult:
        """Async polling with exponential backoff."""
        pass