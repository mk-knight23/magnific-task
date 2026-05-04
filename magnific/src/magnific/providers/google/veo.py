"""Google Veo provider for video generation using REST API.

Based on official Veo 3.0 documentation:
- Model: veo-3.0-generate-001
- Endpoint: predictLongRunning (submit) + fetchPredictOperation (poll)
- Uses REST API with long-running operations
"""

import asyncio
import base64
import subprocess
import time
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from magnific.providers.base import VideoProvider, VideoSubmissionResult, VideoPollResult
from magnific.config.models import VideoModelConfig
from magnific.core.errors import ProviderError
from magnific.providers.google.client import GoogleClient

if TYPE_CHECKING:
    from magnific.core.security import JailedPath

MAX_RESPONSE_SIZE_MB = 500


class GoogleVeoProvider(VideoProvider):
    """
    Google Veo provider for video animation (Veo 3.0).
    
    Uses REST API endpoints from Vertex AI Agent Platform:
    - predictLongRunning: Submit video generation
    - fetchPredictOperation: Poll for completion
    
    Supports:
    - Text-to-video
    - Image-to-video (our use case - from preview images)
    
    Note: Veo operations can take several minutes.
    We poll with exponential backoff.
    """
    
    def __init__(self):
        self._operations: dict[str, dict] = {}
        self._project_id: Optional[str] = None
        self._location: str = "us-central1"
        self._access_token: Optional[str] = None
        
        self._session = self._create_retry_session()
    
    def _create_retry_session(self) -> requests.Session:
        """Create session with automatic retry for transient failures."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def _init_auth(self):
        """Initialize authentication for REST API calls."""
        if self._project_id is None:
            self._project_id = GoogleClient.get_project_id()
            self._location = GoogleClient.get_location()
        
        if self._access_token is None:
            self._access_token = self._get_access_token()
    
    def _get_access_token(self) -> str:
        """Get GCP access token using gcloud ADC with security hardening."""
        try:
            gcloud_path = shutil.which("gcloud")
            if not gcloud_path:
                raise ProviderError(
                    "gcloud CLI not found in PATH. Install Google Cloud SDK.",
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
            raise ProviderError(
                "Timeout getting access token",
                provider="google"
            )
        except subprocess.SubprocessError as e:
            raise ProviderError(
                f"Subprocess error: {e}",
                provider="google"
            )
    
    def _get_headers(self) -> dict:
        """Get HTTP headers for API calls."""
        self._init_auth()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json"
        }
    
    def _get_submit_url(self, model_name: str) -> str:
        """Get predictLongRunning endpoint URL."""
        self._init_auth()
        return (
            f"https://{self._location}-aiplatform.googleapis.com/v1/"
            f"projects/{self._project_id}/locations/{self._location}/"
            f"publishers/google/models/{model_name}:predictLongRunning"
        )
    
    def _get_poll_url(self, model_name: str) -> str:
        """Get fetchPredictOperation endpoint URL."""
        self._init_auth()
        return (
            f"https://{self._location}-aiplatform.googleapis.com/v1/"
            f"projects/{self._project_id}/locations/{self._location}/"
            f"publishers/google/models/{model_name}:fetchPredictOperation"
        )
    
    def submit(
        self,
        preview_image: "JailedPath",
        prompt: str,
        config: VideoModelConfig,
        camera_movement: Optional[str] = None,
    ) -> VideoSubmissionResult:
        """
        Submit a video generation request to Veo 3.0 via REST API.
        
        For image-to-video, we include the image in the request.
        Prompt enhancement should be done by the stage layer, not provider.
        
        Returns operation ID for tracking.
        """
        if not preview_image.exists():
            return VideoSubmissionResult(
                success=False,
                error=f"Preview image not found: {preview_image}",
            )
        
        try:
            model_name = config.name or "veo-3.0-generate-001"
            
            # Read image as base64
            image_bytes = preview_image.read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # Determine MIME type
            mime_type = self._get_mime_type(preview_image)
            
            # Build request body for image-to-video
            # Based on Veo 3.0 documentation
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
            
            # Submit to predictLongRunning endpoint
            url = self._get_submit_url(model_name)
            headers = self._get_headers()
            
            response = self._session.post(
                url,
                headers=headers,
                json=request_body,
                timeout=10
            )
            
            if response.status_code != 200:
                error_text = response.text
                if "safety" in error_text.lower() or "blocked" in error_text.lower():
                    return VideoSubmissionResult(
                        success=False,
                        error=f"Safety filter blocked: {error_text[:200]}"
                    )
                return VideoSubmissionResult(
                    success=False,
                    error=f"Veo API error {response.status_code}: {error_text[:200]}"
                )
            
            # Parse response to get operation ID
            result = response.json()
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
                "preview": preview_image,
                "submit_time": time.time(),
                "model_name": model_name,
                "status": "pending",
            }
            
            return VideoSubmissionResult(
                success=True,
                operation_id=op_id,
            )
        
        except requests.Timeout:
            return VideoSubmissionResult(
                success=False,
                error="Timeout submitting to Veo API"
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
    
    def poll(
        self,
        operation_id: str,
        output_path: "JailedPath",
        timeout_seconds: float = 1800,
    ) -> VideoPollResult:
        """
        Poll for video completion and download.
        
        Uses fetchPredictOperation endpoint to check status.
        When done, downloads video from response or GCS URI.
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
        
        try:
            # Build poll request
            request_body = {
                "operationName": operation_name
            }
            
            url = self._get_poll_url(model_name)
            headers = self._get_headers()
            
            response = self._session.post(
                url,
                headers=headers,
                json=request_body,
                timeout=30
            )
            
            if response.status_code != 200:
                return VideoPollResult(
                    success=False,
                    status="failed",
                    error=f"Poll error {response.status_code}: {response.text[:200]}"
                )
            
            result = response.json()
            
            # Check if done
            done = result.get("done", False)
            
            if not done:
                return VideoPollResult(
                    success=False,
                    status="running",
                )
            
            # Check for error in result
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
                # Download from GCS
                video_bytes = self._download_from_gcs(gcs_uri)
                if video_bytes:
                    output_path.write_bytes(video_bytes)
                    return VideoPollResult(
                        success=True,
                        video_path=output_path,
                        status="complete",
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
                    video_path=output_path,
                    status="complete",
                )
            
            return VideoPollResult(
                success=False,
                status="failed",
                error="No video data found"
            )
        
        except requests.Timeout:
            return VideoPollResult(
                success=False,
                status="running",
            )
        except Exception as e:
            return VideoPollResult(
                success=False,
                status="failed",
                error=str(e)
            )
    
    def _download_from_gcs(self, gcs_uri: str) -> Optional[bytes]:
        """Download video from Google Cloud Storage with size guard."""
        try:
            if gcs_uri.startswith("gs://"):
                https_url = gcs_uri.replace("gs://", "https://storage.googleapis.com/")
            else:
                return None
            
            headers = self._get_headers()
            response = self._session.get(https_url, headers=headers, timeout=60, stream=True)
            
            if response.status_code != 200:
                return None
            
            content_length = int(response.headers.get("content-length", 0))
            max_size = MAX_RESPONSE_SIZE_MB * 1024 * 1024
            
            if content_length > max_size:
                raise ProviderError(
                    f"Video too large: {content_length / 1024 / 1024:.1f}MB exceeds {MAX_RESPONSE_SIZE_MB}MB limit",
                    provider="google"
                )
            
            return response.content
            
        except ProviderError:
            raise
        except Exception:
            return None
    
    async def poll_async(
        self,
        operation_id: str,
        output_path: "JailedPath",
        poll_interval: float = 10.0,
        backoff_multiplier: float = 1.5,
        max_poll_minutes: float = 30.0,
    ) -> VideoPollResult:
        """
        Async polling with exponential backoff.
        
        This is the preferred method for concurrent polling.
        """
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
            
            # Still running - wait with backoff
            await asyncio.sleep(interval)
            interval = min(interval * backoff_multiplier, 60.0)
        
        return VideoPollResult(
            success=False,
            status="timeout",
            error=f"Polling timed out after {max_poll_minutes} minutes"
        )
    
    def check_status(self, operation_id: str) -> str:
        """
        Check operation status without downloading.
        
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
            
            response = self._session.post(
                url,
                headers=headers,
                json=request_body,
                timeout=30
            )
            
            if response.status_code != 200:
                return "failed"
            
            result = response.json()
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