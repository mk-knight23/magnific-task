"""Google Gemini provider for story generation."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from magnific.providers.base import StoryProvider, StoryResult
from magnific.config.models import StoryModelConfig
from magnific.core.manifest import ScenePrompt
from magnific.core.errors import ProviderError
from magnific.providers.google.client import GoogleClient

if TYPE_CHECKING:
    from magnific.core.security import JailedPath


class GoogleGeminiProvider(StoryProvider):
    """
    Google Gemini provider for story/prompt generation.
    
    Uses vertexai SDK (Vertex AI) or google-generativeai (AI Studio).
    Should be wrapped in thread executor for async contexts.
    
    Safety: Handles Gemini's safety filter responses correctly.
    """
    
    def __init__(self):
        self._client = None
        self._mode = None
    
    def _init_client(self):
        """Lazy client initialization - Vertex AI primary, AI Studio fallback."""
        if self._client is None:
            try:
                # Use Vertex AI (requires project setup)
                GoogleClient.init_vertex_ai()
                
                # Import Vertex AI Gemini
                from vertexai.generative_models import GenerativeModel, Part
                self._client = GenerativeModel
                self._part_class = Part
                self._mode = "vertex-ai"
                    
            except ImportError:
                raise ProviderError(
                    "vertexai not installed. "
                    "Install with: pip install google-cloud-aiplatform",
                    provider="google",
                )
        return self._client
    
    def generate_scenes(
        self,
        reference_images: list["JailedPath"],
        brief: str,
        config: StoryModelConfig,
        system_prompt: str,
        user_template: str,
    ) -> StoryResult:
        """
        Generate scene prompts using Gemini via Vertex AI.
        
        Process:
        1. Load reference images using Part.from_image()
        2. Construct multimodal prompt
        3. Call Gemini with system instruction
        4. Parse JSON from response (handle markdown blocks)
        5. Return structured scenes
        """
        GenerativeModel = self._init_client()
        Part = self._part_class
        
        # Estimate input tokens with safety buffer (rough: 1 token ~ 4 chars + image tokens)
        system_tokens = len(system_prompt) // 4
        user_tokens = len(user_template.replace("{brief}", brief)) // 4
        image_tokens = len(reference_images) * 500 + 500  # Safety buffer
        estimated_input_tokens = system_tokens + user_tokens + image_tokens
        
        # Load images using Vertex AI Part.from_data (direct bytes)
        image_parts = []
        for path in reference_images:
            if not path.exists():
                return StoryResult(
                    success=False,
                    scenes=[],
                    error=f"Reference image not found: {path}",
                )
            
            try:
                # Vertex AI format: Part.from_data with bytes
                img_bytes = path.read_bytes()
                mime_type = self._get_mime_type(path)
                part = Part.from_data(data=img_bytes, mime_type=mime_type)
                image_parts.append(part)
            except Exception as e:
                return StoryResult(
                    success=False,
                    scenes=[],
                    error=f"Failed to load image {path}: {e}",
                )
        
        # Construct prompt
        user_prompt = user_template.replace("{brief}", brief)
        
        # Create model with system instruction
        model = GenerativeModel(
            config.name,
            system_instruction=system_prompt,
        )
        
        # Build contents: images + text
        contents = image_parts + [user_prompt]
        
        try:
            response = model.generate_content(contents)
            
            # Check for safety blocks
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                return StoryResult(
                    success=False,
                    scenes=[],
                    error=f"Safety filter blocked: {response.prompt_feedback.block_reason}",
                )
            
            # Parse JSON response
            text = response.text
            scenes = self._parse_scenes_json(text)
            
            if not scenes:
                return StoryResult(
                    success=False,
                    scenes=[],
                    error="Failed to parse scenes from Gemini response",
                )
            
            # Get actual token usage
            total_tokens = response.usage_metadata.total_token_count if hasattr(response, 'usage_metadata') else estimated_input_tokens + 2000
            
            return StoryResult(
                success=True,
                scenes=scenes,
                tokens_used=total_tokens,
                estimated_input_tokens=estimated_input_tokens,
            )
        
        except Exception as e:
            error_str = str(e).lower()
            if "safety" in error_str or "blocked" in error_str:
                return StoryResult(
                    success=False,
                    scenes=[],
                    error=f"Safety filter: {e}",
                )
            
            return StoryResult(
                success=False,
                scenes=[],
                error=f"Gemini API error: {e}",
            )
    
    def _parse_scenes_json(self, text: str) -> list[ScenePrompt]:
        """Parse JSON array of scenes."""
        # Try direct parse
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try extracting JSON array from text
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    return []
            else:
                return []
        
        if not isinstance(data, list):
            return []
        
        scenes = []
        for i, item in enumerate(data, 1):
            try:
                scene = ScenePrompt(
                    scene_id=f"scene_{i:03d}",
                    scene_number=item.get("scene_number", i),
                    title=item.get("title", f"Scene {i}"),
                    image_prompt=item.get("image_prompt", ""),
                    video_prompt=item.get("video_prompt"),
                    duration_seconds=item.get("duration_seconds", 8),
                    camera_movement=item.get("camera_movement"),
                    lighting_type=item.get("lighting_type"),
                )
                scenes.append(scene)
            except Exception:
                continue
        
        return scenes
    
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