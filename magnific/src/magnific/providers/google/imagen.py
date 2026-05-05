"""Google Imagen provider for preview image generation.

Verified model names from Google Cloud documentation:
- imagen-3.0-generate-002 (Imagen 3, verified)
- imagegeneration@006 (Legacy verified name)

Note: Vertex AI SDK is synchronous - requires thread executor for async.
Unlike Veo (REST), Imagen SDK has no native async support.

Reference:
https://cloud.google.com/vertex-ai/generative-ai/docs/image/overview
"""

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from magnific.providers.base import ImageProvider, ImageResult
from magnific.config.models import PreviewModelConfig
from magnific.core.errors import ProviderError, SafetyFilterError
from magnific.providers.google.client import GoogleClient

if TYPE_CHECKING:
    from magnific.core.security import JailedPath

VERIFIED_IMAGEN_MODELS = ["imagen-3.0-generate-002", "imagegeneration@006"]


class GoogleImagenProvider(ImageProvider):
    """Google Imagen provider for preview image generation.
    
    Uses VERIFIED Vertex AI Imagen model names.
    
    SDK nature: SYNCHRONOUS (no native async)
    Pattern: Thread executor for async contexts (correct)
    
    Why thread executor?
    - Vertex AI vision_models SDK is blocking
    - No aiohttp-style async available
    - Thread executor is the correct pattern here
    
    Memory optimization: Byte cache for reference images
    to prevent loading same images multiple times during
    concurrent scene generation.
    """
    
    def __init__(self):
        self._client = None
        self._byte_cache: dict["JailedPath", bytes] = {}
        self._cache_lock = asyncio.Lock()
    
    def _init_client(self):
        """Lazy client initialization with Vertex AI."""
        if self._client is None:
            try:
                # Initialize Vertex AI (requires project + location)
                GoogleClient.init_vertex_ai()
                
                from vertexai.preview.vision_models import ImageGenerationModel
                self._client = ImageGenerationModel
            except ImportError:
                raise ProviderError(
                    "vertexai not installed. "
                    "Install with: pip install google-cloud-aiplatform",
                    provider="google",
                )
        return self._client
    
    def generate_image(
        self,
        prompt: str,
        reference_images: list["JailedPath"],
        output_path: "JailedPath",
        config: PreviewModelConfig,
    ) -> ImageResult:
        """Generate a preview image using VERIFIED Imagen model.
        
        Imagen 3 verified model names:
        - imagen-3.0-generate-002 (recommended)
        - imagegeneration@006 (legacy)
        
        Prompt enhancement should be done by the stage layer, not provider.
        """
        ImageGenerationModel = self._init_client()
        start_time = time.time()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use VERIFIED model name
        model_name = config.name or "imagen-3.0-generate-002"
        
        if model_name not in VERIFIED_IMAGEN_MODELS:
            return ImageResult(
                success=False,
                error=f"Unverified model '{model_name}'. Use: {VERIFIED_IMAGEN_MODELS}"
            )
        
        try:
            # Load VERIFIED model
            model = ImageGenerationModel.from_pretrained(model_name)
            
            # Generate image (prompt already enhanced by stage)
            response = model.generate_images(
                prompt=prompt,
                number_of_images=1,
                aspect_ratio=config.aspect_ratio,
                # Use default safety settings (block_fewest requires allowlisting)
                # safety_filter_level="block_fewest",  # Removed - requires allowlisting
                # person_generation=config.person_generation,  # Removed for now
            )
            
            # Handle response (Imagen 3 returns 'images' attribute)
            if response:
                # Try both possible response structures
                if hasattr(response, 'images') and len(response.images) > 0:
                    generated_image = response.images[0]
                elif hasattr(response, 'generated_images') and len(response.generated_images) > 0:
                    generated_image = response.generated_images[0]
                else:
                    return ImageResult(
                        success=False,
                        error="No images generated in response"
                    )
                
                # Save the generated image
                generated_image.save(str(output_path))
                
                elapsed = time.time() - start_time
                
                return ImageResult(
                    success=True,
                    image_path=output_path,
                    generation_time_ms=int(elapsed * 1000)
                )
            else:
                return ImageResult(
                    success=False,
                    error="Empty response from Imagen"
                )
        
        except Exception as e:
            error_str = str(e).lower()
            
            if "safety" in error_str or "blocked" in error_str or "content policy" in error_str:
                return ImageResult(
                    success=False,
                    error=f"Safety filter blocked: {e}"
                )
            
            return ImageResult(
                success=False,
                error=f"Imagen API error: {e}"
            )
    
    def get_cached_bytes(self, path: "JailedPath") -> Optional[bytes]:
        """Get cached image bytes (prevents memory duplication)."""
        if path in self._byte_cache:
            return self._byte_cache[path]
        
        if path.exists():
            data = path.read_bytes()
            self._byte_cache[path] = data
            return data
        
        return None
    
    async def get_cached_bytes_async(self, path: "JailedPath") -> Optional[bytes]:
        """Async version with lock for concurrent access."""
        async with self._cache_lock:
            return self.get_cached_bytes(path)
    
    def clear_cache(self) -> None:
        """Clear byte cache to free memory."""
        self._byte_cache.clear()
    
    def _get_mime_type(self, path: "JailedPath") -> str:
        """Get MIME type from file extension."""
        ext = path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        return mime_map.get(ext, "image/jpeg")