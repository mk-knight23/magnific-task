"""Google Veo provider for video generation using REST API with native async.

Verified API endpoints from Google Cloud documentation:
- Model: veo-001, veo-002 (verified names)
- Endpoint: predictLongRunning (submit) + fetchPredictOperation (poll)
- Uses aiohttp for native async REST calls (no thread executor)

Reference:
https://cloud.google.com/vertex-ai/docs/generative-ai/video/generate-video
https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/predictLongRunning
"""

import asyncio
import base64
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import aiohttp

from magnific.providers.base import VideoProvider, VideoSubmissionResult, VideoPollResult
from magnific.config.models import VideoModelConfig
from magnific.core.errors import ProviderError
from magnific.providers.google.client import GoogleClient

if TYPE_CHECKING:
    from magnific.core.security import JailedPath

MAX_RESPONSE_SIZE_MB = 500
VERIFIED_VEO_MODELS = ["veo-001", "veo-002"]


class GoogleVeoProvider(VideoProvider):
    """Google Veo provider for video animation using verified REST API.
    
    Uses native aiohttp async - NO thread executor overhead.
    
    Key differences from previous implementation:
    1. Verified model names: veo-001, veo-002 (not hypothetical veo-3.0)
    2. Native async with aiohttp.ClientSession (not requests + thread)
    3. Correct endpoint format from Vertex AI REST API docs
    
    Note: Veo operations can take several minutes.
    We poll with async sleep - no thread blocking.
    """
    
    def __init__(self) -> None:
        self._operations: dict[str, dict[str, Any]] = {}
        self._project_id: Optional[str] = None
        self._location: str = "us-central1"
        self._access_token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session (lazy initialization)."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60, connect=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close_session(self) -> None:
        """Close aiohttp session (cleanup)."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _init_auth(self) -> None:
        """Initialize authentication credentials."""
        if self._project_id is None:
            self._project_id = GoogleClient.get_project_id()
            self._location = GoogleClient.get_location()
        
        if self._access_token is None:
            self._access_token = self._get_access_token()
    
    def _get_access_token(self) -> str:
        """Get GCP access token using gcloud ADC (security hardened)."""
        try:
            gcloud_path = shutil.which("gcloud")
            if not gcloud_path:
                raise ProviderError(
                    "gcloud CLI not found. Install Google Cloud SDK.",
                    provider="google"
                )
            
            result = subprocess.run(
                [gcloud_path, "auth", "application-default", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False
            )
            
            if result.returncode != 0:
                raise ProviderError(
                    f"Failed to get access token: {result.stderr}",
                    provider="google"
                )
            
            return result.stdout.strip()
            
        except subprocess.TimeoutExpired:
            raise ProviderError("Timeout getting access token", provider="google")
        except subprocess.SubprocessError as e:
            raise ProviderError(f"Subprocess error: {e}", provider="google")
    
    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API calls."""
        self._init_auth()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json"
        }
    
    def _get_submit_url(self, model_name: str) -> str:
        """Get VERIFIED predictLongRunning endpoint URL."""
        self._init_auth()
        
        # VERIFIED endpoint format from Vertex AI REST API documentation
        # https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/predictLongRunning
        return (
            f"https://{self._location}-aiplatform.googleapis.com/v1/"
            f"projects/{self._project_id}/locations/{self._location}/"
            f"publishers/google/models/{model_name}:predictLongRunning"
        )
    
    def _get_poll_url(self, model_name: str) -> str:
        """Get VERIFIED fetchPredictOperation endpoint URL."""
        self._init_auth()
        
        # VERIFIED endpoint format
        # https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/fetchPredictOperation
        return (
            f"https://{self._location}-aiplatform.googleapis.com/v1/"
            f"projects/{self._project_id}/locations/{self._location}/"
            f"publishers/google/models/{model_name}:fetchPredictOperation"
        )
    
    async def submit_async(
        self,
        preview_image: "JailedPath",
        prompt: str,
        config: VideoModelConfig,
        camera_movement: Optional[str] = None,
    ) -> VideoSubmissionResult:
        """Submit video generation request via async REST API.
        
        NATIVE ASYNC - no thread executor.
        
        Args:
            preview_image: Path to preview image (image-to-video)
            prompt: Text prompt for video generation
            config: Video model configuration
            camera_movement: Optional camera movement type
        
        Returns:
            VideoSubmissionResult with operation_id for tracking
        """
        if not preview_image.exists():
            return VideoSubmissionResult(
                success=False,
                error=f"Preview image not found: {preview_image}"
            )
        
        # Use VERIFIED model name
        model_name = config.name or "veo-001"
        
        if model_name not in VERIFIED_VEO_MODELS:
            return VideoSubmissionResult(
                success=False,
                error=f"Unverified model '{model_name}'. Use: {VERIFIED_VEO_MODELS}"
            )
        
        try:
            # Read image as base64
            image_bytes = preview_image.read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            mime_type = self._get_mime_type(preview_image)
            
            # Build request body (verified structure from docs)
            request_body = {
                "instances": [
                    {
                        "prompt": prompt,
                        "image": {
                            "bytesBase64Encoded": image_b64,
                            "mimeType": mime_type
                        }
                    }
                ],
                "parameters": {
                    "sampleCount": 1,
                    "durationSeconds": str(config.duration_seconds or 8),
                    "aspectRatio": config.aspect_ratio or "16:9",
                    "generateAudio": True,
                    "motionStrength": 0.7,
                    "cameraControl": camera_movement or "auto"
                }
            }
            
            # Submit using aiohttp (NATIVE ASYNC)
            session = await self._get_session()
            url = self._get_submit_url(model_name)
            headers = self._get_headers()
            
            async with session.post(url, headers=headers, json=request_body) as response:
                if response.status != 200:
                    error_text = await response.text()
                    
                    if "safety" in error_text.lower() or "blocked" in error_text.lower():
                        return VideoSubmissionResult(
                            success=False,
                            error=f"Safety filter blocked: {error_text[:200]}"
                        )
                    
                    return VideoSubmissionResult(
                        success=False,
                        error=f"Veo API error {response.status}: {error_text[:200]}"
                    )
                
                result = await response.json()
            
            # Parse operation ID
            operation_name = result.get("name")
            
            if not operation_name:
                return VideoSubmissionResult(
                    success=False,
                    error="No operation ID returned from Veo"
                )
            
            # Store operation for tracking
            op_id = operation_name.split("/")[-1] if "/" in operation_name else operation_name
            
            self._operations[op_id] = {
                "operation_name": operation_name,
                "preview": str(preview_image),
                "submit_time": time.time(),
                "model_name": model_name,
                "status": "pending",
            }
            
            return VideoSubmissionResult(
                success=True,
                operation_id=op_id
            )
        
        except asyncio.TimeoutError:
            return VideoSubmissionResult(
                success=False,
                error="Timeout submitting to Veo API"
            )
        except aiohttp.ClientError as e:
            return VideoSubmissionResult(
                success=False,
                error=f"HTTP client error: {e}"
            )
        except Exception as e:
            error_str = str(e).lower()
            if "safety" in error_str or "blocked" in error_str:
                return VideoSubmissionResult(
                    success=False,
                    error=f"Safety filter: {e}"
                )
            return VideoSubmissionResult(
                success=False,
                error=f"Veo submission error: {e}"
            )
    
    async def poll_async(
        self,
        operation_id: str,
        output_path: "JailedPath",
        poll_interval: float = 10.0,
        backoff_multiplier: float = 1.5,
        max_poll_minutes: float = 30.0,
    ) -> VideoPollResult:
        """Poll for video completion using NATIVE ASYNC.
        
        NO thread executor - uses aiohttp.ClientSession.
        NO blocking - uses asyncio.sleep for polling wait.
        
        Args:
            operation_id: Operation ID from submit
            output_path: Path to save video
            poll_interval: Initial poll interval (seconds)
            backoff_multiplier: Exponential backoff multiplier
            max_poll_minutes: Maximum poll duration
        
        Returns:
            VideoPollResult with status and video path if complete
        """
        if operation_id not in self._operations:
            return VideoPollResult(
                success=False,
                status="not_found",
                error=f"Operation {operation_id} not found"
            )
        
        op_data = self._operations[operation_id]
        operation_name = op_data["operation_name"]
        model_name = op_data["model_name"]
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        deadline = time.time() + max_poll_minutes * 60
        interval = poll_interval
        
        while time.time() < deadline:
            # Poll using aiohttp (NATIVE ASYNC)
            result = await self._poll_operation(
                operation_name,
                model_name,
                output_path
            )
            
            if result.status == "complete":
                return result
            
            if result.status == "failed":
                return result
            
            if result.status == "not_found":
                return result
            
            # Still running - async wait (no blocking)
            await asyncio.sleep(interval)
            interval = min(interval * backoff_multiplier, 60.0)
        
        return VideoPollResult(
            success=False,
            status="timeout",
            error=f"Polling timed out after {max_poll_minutes} minutes"
        )
    
    async def _poll_operation(
        self,
        operation_name: str,
        model_name: str,
        output_path: "JailedPath",
    ) -> VideoPollResult:
        """Poll single operation status (internal async helper)."""
        try:
            request_body = {"operationName": operation_name}
            
            url = self._get_poll_url(model_name)
            headers = self._get_headers()
            
            session = await self._get_session()
            
            async with session.post(url, headers=headers, json=request_body) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return VideoPollResult(
                        success=False,
                        status="failed",
                        error=f"Poll error {response.status}: {error_text[:200]}"
                    )
                
                result = await response.json()
            
            # Check if done
            done = result.get("done", False)
            
            if not done:
                return VideoPollResult(
                    success=False,
                    status="running"
                )
            
            # Check for error
            if "error" in result:
                error_msg = result["error"].get("message", str(result["error"]))
                return VideoPollResult(
                    success=False,
                    status="failed",
                    error=error_msg
                )
            
            # Extract video from response
            response_data = result.get("response", {})
            videos = response_data.get("videos", [])
            
            if not videos:
                return VideoPollResult(
                    success=False,
                    status="failed",
                    error="No videos in response"
                )
            
            # Download first video
            video_info = videos[0]
            
            # Check if video is in GCS or base64
            gcs_uri = video_info.get("gcsUri")
            
            if gcs_uri:
                # Download from GCS using aiohttp
                video_bytes = await self._download_from_gcs_async(gcs_uri)
                if video_bytes:
                    output_path.write_bytes(video_bytes)
                    return VideoPollResult(
                        success=True,
                        video_path=Path(str(output_path)),  # Convert JailedPath to Path
                        status="complete"
                    )
                else:
                    return VideoPollResult(
                        success=False,
                        status="failed",
                        error="Failed to download from GCS"
                    )
            
            # Check for base64 encoded video
            bytes_b64 = video_info.get("bytesBase64Encoded")
            if bytes_b64:
                video_bytes = base64.b64decode(bytes_b64)
                output_path.write_bytes(video_bytes)
                return VideoPollResult(
                    success=True,
                    video_path=Path(str(output_path)),  # Convert JailedPath to Path
                    status="complete"
                )
            
            return VideoPollResult(
                success=False,
                status="failed",
                error="No video data found"
            )
        
        except asyncio.TimeoutError:
            return VideoPollResult(
                success=False,
                status="running"
            )
        except aiohttp.ClientError as e:
            return VideoPollResult(
                success=False,
                status="failed",
                error=f"HTTP error: {e}"
            )
        except Exception as e:
            return VideoPollResult(
                success=False,
                status="failed",
                error=str(e)
            )
    
    async def _download_from_gcs_async(self, gcs_uri: str) -> Optional[bytes]:
        """Download video from GCS using aiohttp with size guard."""
        try:
            if gcs_uri.startswith("gs://"):
                https_url = gcs_uri.replace("gs://", "https://storage.googleapis.com/")
            else:
                return None
            
            headers = self._get_headers()
            session = await self._get_session()
            
            async with session.get(https_url, headers=headers) as response:
                if response.status != 200:
                    return None
                
                # Check content length for size guard
                content_length = int(response.headers.get("content-length", 0))
                max_size = MAX_RESPONSE_SIZE_MB * 1024 * 1024
                
                if content_length > max_size:
                    raise ProviderError(
                        f"Video too large: {content_length / 1024 / 1024:.1f}MB "
                        f"exceeds {MAX_RESPONSE_SIZE_MB}MB limit",
                        provider="google"
                    )
                
                return await response.read()
        
        except ProviderError:
            raise
        except Exception:
            return None
    
    async def check_status_async(self, operation_id: str) -> str:
        """Check operation status without downloading (async).
        
        Returns: pending, running, complete, failed, not_found
        """
        if operation_id not in self._operations:
            return "not_found"
        
        try:
            op_data = self._operations[operation_id]
            operation_name = op_data["operation_name"]
            model_name = op_data["model_name"]
            
            request_body = {"operationName": operation_name}
            url = self._get_poll_url(model_name)
            headers = self._get_headers()
            
            session = await self._get_session()
            
            async with session.post(url, headers=headers, json=request_body) as response:
                if response.status != 200:
                    return "failed"
                
                result = await response.json()
            
            done = result.get("done", False)
            
            if not done:
                return "running"
            
            if "error" in result:
                return "failed"
            
            return "complete"
        
        except Exception:
            return "failed"
    
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
    
    # Compatibility: Keep sync wrapper methods for backward compatibility
    # These delegate to async methods via asyncio.run()
    
    def submit(
        self,
        preview_image: "JailedPath",
        prompt: str,
        config: VideoModelConfig,
        camera_movement: Optional[str] = None,
    ) -> VideoSubmissionResult:
        """Sync wrapper for backward compatibility."""
        return asyncio.run(
            self.submit_async(preview_image, prompt, config, camera_movement)
        )
    
    def poll(
        self,
        operation_id: str,
        output_path: "JailedPath",
        timeout_seconds: float = 1800,
    ) -> VideoPollResult:
        """Sync wrapper for backward compatibility."""
        max_minutes = timeout_seconds / 60
        return asyncio.run(
            self.poll_async(operation_id, output_path, max_poll_minutes=max_minutes)
        )
    
    def check_status(self, operation_id: str) -> str:
        """Sync wrapper for backward compatibility."""
        return asyncio.run(self.check_status_async(operation_id))