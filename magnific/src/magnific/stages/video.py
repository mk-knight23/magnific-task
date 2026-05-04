"""Stage 3: Video Animation."""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from magnific.stages.base import BaseStage
from magnific.core.manifest import (
    PreviewManifest,
    VideoManifest,
    VideoResult,
    SceneStatus,
)
from magnific.core.security import WorkspaceManager
from magnific.core.tracking import OperationTracker
from magnific.config.models import PipelineConfig
from magnific.providers.base import VideoProvider, VideoPollResult

if TYPE_CHECKING:
    from magnific.core.security import JailedPath
    from magnific.core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class VideoStage(BaseStage):
    """
    Stage 3: Video Animation.
    
    Process:
    1. Load preview_manifest.json
    2. Filter to successful previews
    3. Initialize OperationTracker (ghost job defense)
    4. Check for pending operations from crash
    5. Submit all videos (record operation IDs immediately)
    6. Poll all operations concurrently
    7. Download completed videos
    8. Mark complete in tracker
    9. Write video_manifest.json atomically
    
    Input: PreviewManifest
    Output: VideoManifest
    
    Crash Recovery:
    - Operation IDs written immediately
    - On resume: check pending_operations.jsonl
    - Resume polling existing operations or re-submit
    
    Concurrency:
    - Submit sequentially (rate limits)
    - Poll concurrently (wall time = slowest)
    """
    
    def __init__(
        self,
        workspace: WorkspaceManager,
        config: PipelineConfig,
        provider: Optional[VideoProvider] = None,
        cost_tracker: Optional["CostTracker"] = None,
    ):
        super().__init__(workspace, config, "video", cost_tracker)
        self.provider = provider or self._get_default_provider()
        self.tracker = OperationTracker(workspace)
    
    def _get_default_provider(self) -> VideoProvider:
        """Get default video provider."""
        from magnific.providers import get_video_provider
        
        provider_name = self.config.models.video.provider
        return get_video_provider(provider_name)
    
    async def execute(self, input_manifest: Optional[PreviewManifest] = None) -> VideoManifest:
        """Execute video animation stage."""
        self.check_disk_space()
        
        if input_manifest is None:
            input_manifest = self._load_preview_manifest()
        
        # Get scenes with successful previews
        successful_scenes = input_manifest.get_successful_scenes()
        
        if not successful_scenes:
            self.log_progress("No successful previews to animate")
            return VideoManifest(
                job_id=self.workspace.root.name,
                stage="video",
                parent_manifest="preview_manifest.json",
                scenes=[],
            )
        
        # Create output directory
        videos_dir = self.workspace.resolve("videos", mkdir=True)
        
        self.log_progress(f"Generating videos for {len(successful_scenes)} scenes")
        
        # Check for pending operations (crash recovery)
        pending_ops = self.tracker.get_pending_operations(
            max_age_seconds=self.config.video_concurrency.max_poll_minutes * 60
        )
        
        # Build video results
        video_results: list[VideoResult] = []
        
        # Phase 1: Submit new videos
        scenes_to_submit = [
            s for s in successful_scenes
            if s.scene_id not in pending_ops
        ]
        
        scenes_to_poll = [
            s for s in successful_scenes
            if s.scene_id in pending_ops
        ]
        
        self.log_progress(
            f"Submitting {len(scenes_to_submit)} new, "
            f"resuming {len(scenes_to_poll)} existing"
        )
        
        # Check budget before expensive Veo calls
        if self.cost_tracker:
            duration = self.config.models.video.duration_seconds
            for _ in scenes_to_submit:
                await self.cost_tracker.check_before_veo(duration_seconds=duration)
        
        # Submit new videos (sequentially to respect rate limits)
        for scene in scenes_to_submit:
            result = await self._submit_video(scene, videos_dir)
            video_results.append(result)
        
        # Phase 2: Poll all operations concurrently
        all_polling_scenes = scenes_to_submit + scenes_to_poll
        
        poll_tasks = [
            self._poll_video(scene, videos_dir, pending_ops.get(scene.scene_id))
            for scene in all_polling_scenes
        ]
        
        poll_results = await asyncio.gather(*poll_tasks, return_exceptions=True)
        
        # Update results from polling
        for i, result in enumerate(poll_results):
            if isinstance(result, Exception):
                logger.error(f"[video] Poll error for {all_polling_scenes[i].scene_id}: {result}")
            elif isinstance(result, VideoResult):
                # Update existing result or add new
                existing = next(
                    (r for r in video_results if r.scene_id == result.scene_id),
                    None
                )
                if existing:
                    video_results.remove(existing)
                video_results.append(result)
        
        # Build manifest
        manifest = VideoManifest(
            job_id=self.workspace.root.name,
            stage="video",
            parent_manifest="preview_manifest.json",
            scenes=video_results,
            metadata={
                "model": self.config.models.video.name,
                "duration_seconds": self.config.models.video.duration_seconds,
                "total_scenes": len(video_results),
                "successful": sum(1 for r in video_results if r.status == SceneStatus.SUCCESS),
                "failed": sum(1 for r in video_results if r.status in (SceneStatus.FAILED, SceneStatus.BLOCKED)),
            },
        )
        
        self.atomic_write_manifest(manifest, "video_manifest.json")
        
        # Clear tracker if all complete
        if manifest.completed_count == len(video_results):
            self.tracker.clear_all()
        
        self.log_progress(
            f"Complete: {manifest.completed_count} succeeded, "
            f"{manifest.failed_count} failed"
        )
        
        return manifest
    
    async def _submit_video(
        self,
        scene: any,
        videos_dir: "JailedPath",
    ) -> VideoResult:
        """Submit video generation request."""
        self.log_progress(f"Submitting: {scene.scene_id}", scene.scene_id)
        
        preview_path = scene.preview_path
        if preview_path is None:
            return VideoResult(
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                title=scene.title,
                status=SceneStatus.FAILED,
                error="No preview path",
            )
        
        try:
            # Enhance video prompt with motion physics (SAEST framework)
            from magnific.core.prompt_enhancer import (
                CinematicPromptEnhancer,
                extract_motion_type,
            )
            
            enhancer = CinematicPromptEnhancer()
            base_prompt = scene.video_prompt or scene.image_prompt
            motion_type = extract_motion_type(base_prompt)
            
            enhanced_prompt = enhancer.enhance_video_prompt(
                base_prompt=base_prompt,
                motion_type=motion_type,
                camera_movement=scene.camera_movement,
            )
            
            result = await self.run_sync_in_thread(
                self.provider.submit,
                preview_image=preview_path,
                prompt=enhanced_prompt,
                config=self.config.models.video,
                camera_movement=scene.camera_movement,
            )
            
            if result.success and result.operation_id:
                # Record operation ID immediately (crash-safe)
                self.tracker.record_submission(scene.scene_id, result.operation_id)
                
                return VideoResult(
                    scene_id=scene.scene_id,
                    scene_number=scene.scene_number,
                    title=scene.title,
                    preview_path=preview_path,
                    operation_id=result.operation_id,
                    status=SceneStatus.RUNNING,
                )
            else:
                return VideoResult(
                    scene_id=scene.scene_id,
                    scene_number=scene.scene_number,
                    title=scene.title,
                    preview_path=preview_path,
                    status=SceneStatus.FAILED,
                    error=result.error or "Submission failed",
                )
        
        except Exception as e:
            return VideoResult(
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                title=scene.title,
                preview_path=preview_path,
                status=SceneStatus.FAILED,
                error=str(e),
            )
    
    async def _poll_video(
        self,
        scene: any,
        videos_dir: "JailedPath",
        operation_id: Optional[str] = None,
    ) -> VideoResult:
        """Poll for video completion."""
        
        # If scene was already submitted in this run, get its operation_id
        if operation_id is None:
            pending = self.tracker.get_pending_operations()
            operation_id = pending.get(scene.scene_id, (None, 0))[0] if scene.scene_id in pending else None
        
        if operation_id is None:
            return VideoResult(
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                title=scene.title,
                status=SceneStatus.FAILED,
                error="No operation ID to poll",
            )
        
        output_path = videos_dir / f"{scene.scene_id}.mp4"
        
        self.log_progress(f"Polling: {scene.scene_id} (op={operation_id})", scene.scene_id)
        
        try:
            result = await self.provider.poll_async(
                operation_id=operation_id,
                output_path=output_path,
                poll_interval=self.config.video_concurrency.poll_interval_seconds,
                backoff_multiplier=self.config.video_concurrency.poll_backoff_multiplier,
                max_poll_minutes=self.config.video_concurrency.max_poll_minutes,
            )
            
            if result.success:
                # Mark complete in tracker
                await self.tracker.mark_complete(scene.scene_id)
                
                # Record Veo cost
                if self.cost_tracker:
                    await self.cost_tracker.record_veo_call(
                        duration_seconds=self.config.models.video.duration_seconds
                    )
                
                return VideoResult(
                    scene_id=scene.scene_id,
                    scene_number=scene.scene_number,
                    title=scene.title,
                    preview_path=scene.preview_path,
                    video_path=result.video_path,
                    video_duration_sec=self.config.models.video.duration_seconds,
                    operation_id=operation_id,
                    status=SceneStatus.SUCCESS,
                )
            else:
                return VideoResult(
                    scene_id=scene.scene_id,
                    scene_number=scene.scene_number,
                    title=scene.title,
                    preview_path=scene.preview_path,
                    operation_id=operation_id,
                    status=SceneStatus.FAILED,
                    error=result.error or f"Status: {result.status}",
                )
        
        except Exception as e:
            return VideoResult(
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                title=scene.title,
                preview_path=scene.preview_path,
                operation_id=operation_id,
                status=SceneStatus.FAILED,
                error=str(e),
            )
    
    def _load_preview_manifest(self) -> PreviewManifest:
        """Load input manifest."""
        path = self.workspace.resolve("preview_manifest.json")
        if not path.exists():
            raise FileNotFoundError("preview_manifest.json not found")
        return PreviewManifest.from_file(path)