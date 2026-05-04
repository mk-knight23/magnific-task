"""Google provider module exports."""

from magnific.providers.google.gemini import GoogleGeminiProvider
from magnific.providers.google.imagen import GoogleImagenProvider
from magnific.providers.google.veo import GoogleVeoProvider

from magnific.providers import ProviderRegistry

ProviderRegistry.register("google", "story", GoogleGeminiProvider)
ProviderRegistry.register("google", "image", GoogleImagenProvider)
ProviderRegistry.register("google", "video", GoogleVeoProvider)

__all__ = [
    "GoogleGeminiProvider",
    "GoogleImagenProvider",
    "GoogleVeoProvider",
]