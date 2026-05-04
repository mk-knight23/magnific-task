"""Provider module exports and registry."""

from typing import Callable, Type

from magnific.providers.base import (
    StoryProvider,
    ImageProvider,
    VideoProvider,
    StoryResult,
    ImageResult,
    VideoSubmissionResult,
    VideoPollResult,
)


class ProviderRegistry:
    """
    Registry for provider implementations.
    
    Allows dynamic provider selection via config.
    """
    
    _providers: dict[str, dict[str, Type]] = {
        "google": {},
        "mock": {},
    }
    
    @classmethod
    def register(cls, provider: str, capability: str, impl: Type) -> None:
        """Register a provider implementation."""
        if provider not in cls._providers:
            cls._providers[provider] = {}
        cls._providers[provider][capability] = impl
    
    @classmethod
    def get(cls, provider: str, capability: str) -> Type:
        """Get a provider implementation."""
        try:
            return cls._providers[provider][capability]
        except KeyError:
            available = list(cls._providers.keys())
            raise ValueError(
                f"No {capability} provider registered for '{provider}'. "
                f"Available: {available}"
            )
    
    @classmethod
    def list_providers(cls) -> list[str]:
        """List available provider names."""
        return list(cls._providers.keys())


def get_story_provider(provider: str = "google") -> StoryProvider:
    """Factory for story providers."""
    cls = ProviderRegistry.get(provider, "story")
    return cls()


def get_image_provider(provider: str = "google") -> ImageProvider:
    """Factory for image providers."""
    cls = ProviderRegistry.get(provider, "image")
    return cls()


def get_video_provider(provider: str = "google") -> VideoProvider:
    """Factory for video providers."""
    cls = ProviderRegistry.get(provider, "video")
    return cls()


# Import providers to trigger registration
try:
    from magnific.providers import google
except ImportError:
    pass

try:
    from magnific.providers import mock
except ImportError:
    pass


__all__ = [
    "StoryProvider",
    "ImageProvider",
    "VideoProvider",
    "StoryResult",
    "ImageResult",
    "VideoSubmissionResult",
    "VideoPollResult",
    "ProviderRegistry",
    "get_story_provider",
    "get_image_provider",
    "get_video_provider",
]