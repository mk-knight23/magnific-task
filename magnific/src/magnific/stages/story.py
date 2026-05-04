"""Stage 1: Story & Prompt Generation."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from magnific.stages.base import BaseStage
from magnific.core.manifest import StoryManifest, ScenePrompt, SceneStatus
from magnific.core.security import WorkspaceManager
from magnific.config.models import PipelineConfig
from magnific.providers.base import StoryProvider, StoryResult

if TYPE_CHECKING:
    from magnific.core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class StoryStage(BaseStage):
    """
    Stage 1: Story & Prompt Generation.
    
    Process:
    1. Load reference images
    2. Call Gemini with system prompt
    3. Parse JSON response into scenes
    4. Validate scene count
    5. Write story_manifest.json atomically
    
    Input: None (uses config.job inputs)
    Output: StoryManifest
    """
    
    def __init__(
        self,
        workspace: WorkspaceManager,
        config: PipelineConfig,
        provider: Optional[StoryProvider] = None,
        cost_tracker: Optional["CostTracker"] = None,
    ):
        super().__init__(workspace, config, "story", cost_tracker)
        self.provider = provider or self._get_default_provider()
    
    def _get_default_provider(self) -> StoryProvider:
        """Get default story provider based on config."""
        from magnific.providers import get_story_provider
        
        provider_name = self.config.models.story.provider
        return get_story_provider(provider_name)
    
    async def execute(self, input_manifest: Optional[StoryManifest] = None) -> StoryManifest:
        """Execute story generation stage."""
        self.check_disk_space()
        
        if self.config.job is None:
            raise ValueError("job config required for story stage")
        
        self.log_progress("Starting story generation")
        
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
        
        brief = self.config.job.idea
        
        # Check budget before expensive Gemini call
        if self.cost_tracker:
            # Estimate input tokens with safety buffer (20% extra)
            estimated_input_tokens = (
                len(self.config.prompts.system_prompt) // 4 +  # ~4 chars per token
                len(self.config.prompts.user_template.replace("{brief}", brief)) // 4 +
                len(reference_images) * 500 +  # Rough estimate per image
                500  # Safety buffer
            )
            estimated_output_tokens = int(self.config.models.story.max_output_tokens * 1.2)  # 20% buffer
            await self.cost_tracker.check_before_gemini(
                estimated_input_tokens=estimated_input_tokens,
                estimated_output_tokens=estimated_output_tokens,
            )
        
        # Call provider (sync in thread)
        result: StoryResult = await self.run_sync_in_thread(
            self.provider.generate_scenes,
            reference_images=reference_images,
            brief=brief,
            config=self.config.models.story,
            system_prompt=self.config.prompts.system_prompt,
            user_template=self.config.prompts.user_template,
        )
        
        # Record actual token usage for cost tracking
        if self.cost_tracker and result.success and result.tokens_used:
            actual_input = result.estimated_input_tokens or estimated_input_tokens
            actual_output = max(0, result.tokens_used - actual_input)
            await self.cost_tracker.record_gemini_usage(
                input_tokens=actual_input,
                output_tokens=actual_output,
            )
        
        if not result.success:
            # Failed - write empty manifest with error
            manifest = StoryManifest(
                job_id=self.workspace.root.name,
                stage="story",
                input_summary={
                    "brief": brief,
                    "reference_count": len(reference_images),
                },
                scenes=[],
                metadata={
                    "error": result.error,
                    "tokens_used": result.tokens_used,
                },
            )
            self.atomic_write_manifest(manifest, "story_manifest.json")
            
            self.log_progress(f"Failed: {result.error}")
            return manifest
        
        # Success - build manifest
        scenes = result.scenes
        
        # Enforce scene count limits (safety cap)
        max_scenes = self.config.safety.max_scenes
        if len(scenes) > max_scenes:
            logger.warning(
                f"[story] Generated {len(scenes)} scenes exceeds limit {max_scenes}. "
                f"Truncating to {max_scenes} scenes."
            )
            scenes = scenes[:max_scenes]
        
        # Validate minimum scenes
        if len(scenes) < 4:
            logger.warning(
                f"[story] Only {len(scenes)} scenes generated (expected 4+)"
            )
        
        manifest = StoryManifest(
            job_id=self.workspace.root.name,
            stage="story",
            input_summary={
                "brief": brief,
                "reference_count": len(reference_images),
                "character_count": 2,
            },
            scenes=scenes,
            metadata={
                "model": self.config.models.story.name,
                "tokens_used": result.tokens_used,
                "total_scenes": len(scenes),
                "estimated_input_tokens": result.estimated_input_tokens,
            },
        )
        
        self.atomic_write_manifest(manifest, "story_manifest.json")
        
        self.log_progress(f"Complete: {len(scenes)} scenes generated")
        
        return manifest