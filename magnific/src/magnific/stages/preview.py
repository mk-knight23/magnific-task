"""Stage 2: Preview Image Generation."""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from magnific.stages.base import BaseStage
from magnific.core.manifest import (
    StoryManifest,
    PreviewManifest,
    PreviewResult,
    SceneStatus,
)
from magnific.core.security import WorkspaceManager
from magnific.config.models import PipelineConfig
from magnific.providers.base import ImageProvider, ImageResult
from magnific.core.retry import ErrorAction, ErrorClassifier

if TYPE_CHECKING:
    from magnific.core.security import JailedPath
    from magnific.core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class PreviewStage(BaseStage):
    """
    Stage 2: Preview Image Generation.
    
    Process:
    1. Load story_manifest.json
    2. Create output directory
    3. Generate previews concurrently (semaphore limited)
    4. Handle safety filter blocks gracefully
    5. Write preview_manifest.json atomically
    
    Input: StoryManifest
    Output: PreviewManifest
    
    Concurrency:
    - Semaphore limits max concurrent API calls
    - Each scene is independent
    - Safety blocks don't crash pipeline
    
    Memory:
    - Provider byte cache prevents duplicate image loading
    - Cache cleared before Stage 3
    """
    
    def __init__(
        self,
        workspace: WorkspaceManager,
        config: PipelineConfig,
        provider: Optional[ImageProvider] = None,
        cost_tracker: Optional["CostTracker"] = None,
    ):
        super().__init__(workspace, config, "preview", cost_tracker)
        self.provider = provider or self._get_default_provider()
    
    def _get_default_provider(self) -> ImageProvider:
        """Get default image provider."""
        from magnific.providers import get_image_provider
        
        provider_name = self.config.models.preview.provider
        return get_image_provider(provider_name)
    
    async def execute(self, input_manifest: Optional[StoryManifest] = None) -> PreviewManifest:
        """Execute preview generation stage."""
        self.check_disk_space()
        
        if input_manifest is None:
            input_manifest = self._load_story_manifest()
        
        if not input_manifest.scenes:
            self.log_progress("No scenes to generate previews for")
            return PreviewManifest(
                job_id=self.workspace.root.name,
                stage="preview",
                parent_manifest="story_manifest.json",
                scenes=[],
            )
        
        # Create output directory
        previews_dir = self.workspace.resolve("previews", mkdir=True)
        
        # Get reference images (already optimized by preflight)
        refs_dir = self.workspace.resolve("refs")
        reference_images = sorted(refs_dir.glob("char_*_optimized.jpg"))
        
        # If not found in refs dir, use original reference images (validated through workspace)
        if len(reference_images) < 2:
            # Validate external paths through workspace for security
            if self.config.job and self.config.job.reference_images:
                from pathlib import Path
                validated_refs = []
                for ref_path in self.config.job.reference_images:
                    # Convert to JailedPath via validation
                    validated_ref = self.workspace.validate_external_path(
                        Path(ref_path) if isinstance(ref_path, str) else ref_path,
                        f"Reference image"
                    )
                    validated_refs.append(validated_ref)
                reference_images = validated_refs
        
        self.log_progress(f"Generating previews for {len(input_manifest.scenes)} scenes")
        
        # Check budget before expensive Imagen calls
        if self.cost_tracker:
            for _ in input_manifest.scenes:
                await self.cost_tracker.check_before_imagen()
        
        # Concurrency control
        semaphore = asyncio.Semaphore(self.config.preview_concurrency.max_concurrent)
        
        # Generate concurrently
        tasks = [
            self._generate_scene_preview(
                scene=scene,
                reference_images=reference_images,
                previews_dir=previews_dir,
                semaphore=semaphore,
            )
            for scene in input_manifest.scenes
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build manifest from results
        preview_results = []
        for i, result in enumerate(results):
            scene = input_manifest.scenes[i]
            
            if isinstance(result, Exception):
                # Error during generation
                error_str = str(result)
                action = ErrorClassifier.classify(result)
                
                preview_results.append(
                    PreviewResult(
                        scene_id=scene.scene_id,
                        scene_number=scene.scene_number,
                        title=scene.title,
                        image_prompt=scene.image_prompt,
                        video_prompt=scene.video_prompt,
                        preview_path=None,
                        status=SceneStatus.FAILED if action == ErrorAction.FAIL_SCENE else SceneStatus.BLOCKED,
                        error=error_str,
                    )
                )
            elif isinstance(result, PreviewResult):
                preview_results.append(result)
            else:
                preview_results.append(
                    PreviewResult(
                        scene_id=scene.scene_id,
                        scene_number=scene.scene_number,
                        title=scene.title,
                        image_prompt=scene.image_prompt,
                        video_prompt=scene.video_prompt,
                        status=SceneStatus.FAILED,
                        error="Unexpected result type",
                    )
                )
        
        # Clear provider cache to free memory
        self.provider.clear_cache()
        
        # Write manifest
        manifest = PreviewManifest(
            job_id=self.workspace.root.name,
            stage="preview",
            parent_manifest="story_manifest.json",
            scenes=preview_results,
            metadata={
                "model": self.config.models.preview.name,
                "concurrency": self.config.preview_concurrency.max_concurrent,
                "total_scenes": len(preview_results),
                "successful": sum(1 for r in preview_results if r.status == SceneStatus.SUCCESS),
                "failed": sum(1 for r in preview_results if r.status in (SceneStatus.FAILED, SceneStatus.BLOCKED)),
            },
        )
        
        self.atomic_write_manifest(manifest, "preview_manifest.json")
        
        success_count = manifest.completed_count
        failed_count = manifest.failed_count
        
        self.log_progress(f"Complete: {success_count} succeeded, {failed_count} failed")
        
        return manifest
    
    async def _generate_scene_preview(
        self,
        scene: any,
        reference_images: list["JailedPath"],
        previews_dir: "JailedPath",
        semaphore: asyncio.Semaphore,
    ) -> PreviewResult:
        """Generate preview for a single scene."""
        async with semaphore:
            self.log_progress(f"Generating preview: {scene.scene_id}", scene.scene_id)
            
            output_path = previews_dir / f"{scene.scene_id}.png"
            
            # Check if already exists (idempotency)
            if output_path.exists() and output_path.stat().st_size > 0:
                self.log_progress(f"Preview exists, skipping: {scene.scene_id}", scene.scene_id)
                return PreviewResult(
                        scene_id=scene.scene_id,
                        scene_number=scene.scene_number,
                        title=scene.title,
                        image_prompt=scene.image_prompt,
                        video_prompt=scene.video_prompt,
                        camera_movement=scene.camera_movement,
                        lighting_type=scene.lighting_type,
                        preview_path=output_path,
                        status=SceneStatus.SUCCESS,
                    )
            
            try:
                # Enhance prompt with cinematic specifications (SAEST framework)
                from magnific.core.prompt_enhancer import (
                    CinematicPromptEnhancer,
                    extract_lighting_type,
                    extract_lens_type,
                )
                
                enhancer = CinematicPromptEnhancer()
                
                # Extract lighting/lens from prompt if not provided
                lighting_type = scene.lighting_type or extract_lighting_type(scene.image_prompt)
                lens_type = extract_lens_type(scene.image_prompt)
                
                # Enhance prompt
                enhanced_prompt = enhancer.enhance_image_prompt(
                    base_prompt=scene.image_prompt,
                    lighting_type=lighting_type,
                    lens_type=lens_type,
                    film_stock="cinematic",
                )
                
                # Add reference context
                enhanced_prompt = enhancer.add_reference_context(
                    enhanced_prompt,
                    len(reference_images),
                )
                
                # Call provider (sync in thread) with enhanced prompt
                result: ImageResult = await self.run_sync_in_thread(
                    self.provider.generate_image,
                    prompt=enhanced_prompt,
                    reference_images=reference_images,
                    output_path=output_path,
                    config=self.config.models.preview,
                )
                
                if result.success:
                    # Record Imagen cost
                    if self.cost_tracker:
                        await self.cost_tracker.record_imagen_call()
                    
                    return PreviewResult(
                        scene_id=scene.scene_id,
                        scene_number=scene.scene_number,
                        title=scene.title,
                        image_prompt=scene.image_prompt,
                        video_prompt=scene.video_prompt,
                        preview_path=result.image_path,
                        generation_time_ms=result.generation_time_ms,
                        status=SceneStatus.SUCCESS,
                    )
                else:
                    # Provider failed (likely safety filter)
                    return PreviewResult(
                        scene_id=scene.scene_id,
                        scene_number=scene.scene_number,
                        title=scene.title,
                        image_prompt=scene.image_prompt,
                        video_prompt=scene.video_prompt,
                        status=SceneStatus.BLOCKED,
                        error=result.error or "Unknown error",
                    )
            
            except Exception as e:
                action = ErrorClassifier.classify(e)
                
                if action == ErrorAction.RETRY:
                    # Retry once with enhanced prompt
                    try:
                        # Enhance prompt again (same logic as above)
                        from magnific.core.prompt_enhancer import (
                            CinematicPromptEnhancer,
                            extract_lighting_type,
                            extract_lens_type,
                        )
                        
                        enhancer = CinematicPromptEnhancer()
                        lighting_type = scene.lighting_type or extract_lighting_type(scene.image_prompt)
                        lens_type = extract_lens_type(scene.image_prompt)
                        
                        enhanced_prompt = enhancer.enhance_image_prompt(
                            base_prompt=scene.image_prompt,
                            lighting_type=lighting_type,
                            lens_type=lens_type,
                            film_stock="cinematic",
                        )
                        
                        enhanced_prompt = enhancer.add_reference_context(
                            enhanced_prompt,
                            len(reference_images),
                        )
                        
                        result = await self.run_sync_in_thread(
                            self.provider.generate_image,
                            prompt=enhanced_prompt,
                            reference_images=reference_images,
                            output_path=output_path,
                            config=self.config.models.preview,
                        )
                        
                        if result.success:
                            return PreviewResult(
                                scene_id=scene.scene_id,
                                scene_number=scene.scene_number,
                                title=scene.title,
                                image_prompt=scene.image_prompt,
                                video_prompt=scene.video_prompt,
                                preview_path=result.image_path,
                                status=SceneStatus.SUCCESS,
                            )
                    except Exception as retry_error:
                        e = retry_error
                
                return PreviewResult(
                    scene_id=scene.scene_id,
                    scene_number=scene.scene_number,
                    title=scene.title,
                    image_prompt=scene.image_prompt,
                    video_prompt=scene.video_prompt,
                    status=SceneStatus.FAILED,
                    error=str(e),
                )
    
    def _load_story_manifest(self) -> StoryManifest:
        """Load input manifest."""
        path = self.workspace.resolve("story_manifest.json")
        if not path.exists():
            raise FileNotFoundError("story_manifest.json not found")
        return StoryManifest.from_file(path)