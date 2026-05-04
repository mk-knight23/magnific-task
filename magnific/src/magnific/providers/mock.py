"""Mock providers for testing."""

import base64
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from magnific.providers.base import (
    StoryProvider,
    ImageProvider,
    VideoProvider,
    StoryResult,
    ImageResult,
    VideoSubmissionResult,
    VideoPollResult,
)
from magnific.config.models import (
    StoryModelConfig,
    PreviewModelConfig,
    VideoModelConfig,
)
from magnific.core.manifest import ScenePrompt

if TYPE_CHECKING:
    from magnific.core.security import JailedPath


class MockStoryProvider(StoryProvider):
    """Mock story provider for testing."""
    
    def __init__(self, scene_count: int = 5, fail_mode: bool = False):
        self.scene_count = scene_count
        self.fail_mode = fail_mode
        self.last_call_time: Optional[float] = None
    
    def generate_scenes(
        self,
        reference_images: list["JailedPath"],
        brief: str,
        config: StoryModelConfig,
        system_prompt: str,
        user_template: str,
    ) -> StoryResult:
        self.last_call_time = time.time()
        
        if self.fail_mode:
            return StoryResult(
                success=False,
                scenes=[],
                error="Mock failure: safety filter blocked",
            )
        
        scenes = []
        for i in range(1, self.scene_count + 1):
            scenes.append(
                ScenePrompt(
                    scene_id=f"scene_{i:03d}",
                    scene_number=i,
                    title=f"Scene {i}: Mock Title",
                    image_prompt=f"Mock image prompt for scene {i} with characters from references",
                    video_prompt=f"Mock video direction for scene {i}",
                    duration_seconds=5,
                )
            )
        
        return StoryResult(
            success=True,
            scenes=scenes,
            tokens_used=1000,
        )


class MockImageProvider(ImageProvider):
    """Mock image provider for testing with memory cache."""
    
    def __init__(self, fail_scenes: set[int] | None = None):
        self.fail_scenes = fail_scenes or set()
        self._byte_cache: dict[Path, bytes] = {}
        self.last_call_time: Optional[float] = None
    
    def generate_image(
        self,
        prompt: str,
        reference_images: list["JailedPath"],
        output_path: "JailedPath",
        config: PreviewModelConfig,
    ) -> ImageResult:
        self.last_call_time = time.time()
        
        # Extract scene number from path if possible
        scene_num = self._extract_scene_number(output_path)
        if scene_num in self.fail_scenes:
            return ImageResult(
                success=False,
                error="Mock failure: safety filter blocked",
            )
        
        # Generate mock image data (small PNG header)
        mock_data = self._create_mock_png()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(mock_data)
        
        return ImageResult(
            success=True,
            image_path=output_path,
            generation_time_ms=500,
        )
    
    def get_cached_bytes(self, path: "JailedPath") -> Optional[bytes]:
        """Get or create cached bytes."""
        if path not in self._byte_cache:
            if path.exists():
                self._byte_cache[path] = path.read_bytes()
        return self._byte_cache.get(path)
    
    def clear_cache(self) -> None:
        """Clear byte cache."""
        self._byte_cache.clear()
    
    def _extract_scene_number(self, path: Path) -> int:
        """Extract scene number from filename like scene_001.png."""
        name = path.stem
        if "scene_" in name:
            try:
                num_str = name.split("_")[1]
                return int(num_str)
            except (IndexError, ValueError):
                pass
        return 0
    
    def _create_mock_png(self) -> bytes:
        """Create minimal valid PNG."""
        # PNG signature + minimal IHDR + IDAT + IEND
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGWAHL6"
            "vwAAAABJRU5ErkJggg=="
        )


class MockVideoProvider(VideoProvider):
    """Mock video provider for testing."""
    
    def __init__(
        self,
        operation_delay: float = 2.0,
        fail_operations: set[str] | None = None,
    ):
        self.operation_delay = operation_delay
        self.fail_operations = fail_operations or set()
        self._operations: dict[str, dict] = {}
        self.last_submit_time: Optional[float] = None
    
    def submit(
        self,
        preview_image: "JailedPath",
        prompt: str,
        config: VideoModelConfig,
    ) -> VideoSubmissionResult:
        self.last_submit_time = time.time()
        
        # Generate mock operation ID
        op_id = f"mock-veo-{int(time.time() * 1000)}"
        
        self._operations[op_id] = {
            "preview": preview_image,
            "prompt": prompt,
            "submit_time": time.time(),
            "status": "pending",
        }
        
        return VideoSubmissionResult(
            success=True,
            operation_id=op_id,
        )
    
    def poll(
        self,
        operation_id: str,
        output_path: "JailedPath",
        timeout_seconds: float = 1800,
    ) -> VideoPollResult:
        if operation_id in self.fail_operations:
            return VideoPollResult(
                success=False,
                status="failed",
                error="Mock failure: operation failed",
            )
        
        if operation_id not in self._operations:
            return VideoPollResult(
                success=False,
                status="not_found",
                error=f"Operation {operation_id} not found",
            )
        
        op = self._operations[operation_id]
        elapsed = time.time() - op["submit_time"]
        
        # Simulate processing time
        if elapsed < self.operation_delay:
            return VideoPollResult(
                success=False,
                status="running",
            )
        
        # Complete - write mock video
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self._create_mock_mp4())
        
        return VideoPollResult(
            success=True,
            video_path=output_path,
            status="complete",
        )
    
    def check_status(self, operation_id: str) -> str:
        if operation_id not in self._operations:
            return "not_found"
        
        op = self._operations[operation_id]
        elapsed = time.time() - op["submit_time"]
        
        if elapsed < self.operation_delay:
            return "running"
        return "complete"
    
    async def poll_async(
        self,
        operation_id: str,
        output_path: "JailedPath",
        poll_interval: float = 10.0,
        backoff_multiplier: float = 1.5,
        max_poll_minutes: float = 30.0,
    ) -> VideoPollResult:
        """Async polling with backoff."""
        import asyncio
        
        deadline = time.time() + max_poll_minutes * 60
        interval = poll_interval
        
        while time.time() < deadline:
            result = self.poll(operation_id, output_path)
            
            if result.status == "complete":
                return result
            
            if result.status == "failed":
                return result
            
            if result.status == "not_found":
                return result
            
            await asyncio.sleep(interval)
            interval = min(interval * backoff_multiplier, 60.0)
        
        return VideoPollResult(
            success=False,
            status="timeout",
            error=f"Polling timed out after {max_poll_minutes} minutes"
        )
    
    def _create_mock_mp4(self) -> bytes:
        """Create minimal mock MP4 (not valid format, just bytes)."""
        return b"MOCK_MP4_DATA_" + bytes([0] * 100)


# Register mock providers
from magnific.providers import ProviderRegistry

ProviderRegistry.register("mock", "story", MockStoryProvider)
ProviderRegistry.register("mock", "image", MockImageProvider)
ProviderRegistry.register("mock", "video", MockVideoProvider)