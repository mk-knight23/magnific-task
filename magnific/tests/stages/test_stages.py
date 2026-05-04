"""Tests for stage execution."""

import pytest
import asyncio

from magnific.stages.story import StoryStage
from magnific.stages.preview import PreviewStage
from magnific.stages.video import VideoStage
from magnific.core.manifest import SceneStatus


class TestStoryStage:
    """Tests for story generation stage."""
    
    @pytest.mark.asyncio
    async def test_execute_success(self, workspace, sample_config, mock_story_provider):
        """Successful story generation."""
        stage = StoryStage(
            workspace=workspace,
            config=sample_config,
            provider=mock_story_provider,
        )
        
        # Create refs directory with placeholder images
        refs_dir = workspace.resolve("refs", mkdir=True)
        from PIL import Image
        Image.new("RGB", (50, 50)).save(refs_dir / "char_1_optimized.jpg")
        Image.new("RGB", (50, 50)).save(refs_dir / "char_2_optimized.jpg")
        
        manifest = await stage.execute()
        
        assert manifest.stage == "story"
        assert len(manifest.scenes) == 3
        assert manifest.scenes[0].scene_id == "scene_001"
    
    @pytest.mark.asyncio
    async def test_execute_failure(self, workspace, sample_config):
        """Failed story generation handled."""
        from magnific.providers.mock import MockStoryProvider
        
        fail_provider = MockStoryProvider(fail_mode=True)
        stage = StoryStage(
            workspace=workspace,
            config=sample_config,
            provider=fail_provider,
        )
        
        refs_dir = workspace.resolve("refs", mkdir=True)
        from PIL import Image
        Image.new("RGB", (50, 50)).save(refs_dir / "char_1_optimized.jpg")
        Image.new("RGB", (50, 50)).save(refs_dir / "char_2_optimized.jpg")
        
        manifest = await stage.execute()
        
        assert manifest.stage == "story"
        assert len(manifest.scenes) == 0
        assert "error" in manifest.metadata


class TestPreviewStage:
    """Tests for preview generation stage."""
    
    @pytest.mark.asyncio
    async def test_execute_success(self, workspace, sample_config, mock_image_provider, sample_story_manifest):
        """Successful preview generation."""
        # Write input manifest
        from magnific.core.manifest import atomic_write_manifest
        atomic_write_manifest(sample_story_manifest, workspace.resolve("story_manifest.json"))
        
        stage = PreviewStage(
            workspace=workspace,
            config=sample_config,
            provider=mock_image_provider,
        )
        
        manifest = await stage.execute(sample_story_manifest)
        
        assert manifest.stage == "preview"
        assert len(manifest.scenes) == 2
    
    @pytest.mark.asyncio
    async def test_partial_failure(self, workspace, sample_config, sample_story_manifest):
        """Partial failure handled gracefully."""
        from magnific.providers.mock import MockImageProvider
        
        fail_provider = MockImageProvider(fail_scenes={1})
        
        # Write input manifest
        from magnific.core.manifest import atomic_write_manifest
        atomic_write_manifest(sample_story_manifest, workspace.resolve("story_manifest.json"))
        
        stage = PreviewStage(
            workspace=workspace,
            config=sample_config,
            provider=fail_provider,
        )
        
        manifest = await stage.execute(sample_story_manifest)
        
        assert manifest.stage == "preview"
        assert manifest.failed_count == 1
        assert manifest.completed_count == 1


class TestVideoStage:
    """Tests for video generation stage."""
    
    @pytest.mark.asyncio
    async def test_execute_success(self, workspace, sample_config, mock_video_provider):
        """Successful video generation with tracking."""
        from magnific.core.manifest import PreviewManifest, PreviewResult, atomic_write_manifest
        
        # Create input manifest
        preview_manifest = PreviewManifest(
            job_id=workspace.root.name,
            stage="preview",
            parent_manifest="story_manifest.json",
            scenes=[
                PreviewResult(
                    scene_id="scene_001",
                    scene_number=1,
                    title="Scene 1",
                    image_prompt="Test",
                    preview_path=workspace.resolve("previews", "scene_001.png", mkdir=True),
                    status=SceneStatus.SUCCESS,
                ),
            ],
        )
        
        # Create preview file
        from PIL import Image
        Image.new("RGB", (50, 50)).save(workspace.resolve("previews", "scene_001.png"))
        
        atomic_write_manifest(preview_manifest, workspace.resolve("preview_manifest.json"))
        
        stage = VideoStage(
            workspace=workspace,
            config=sample_config,
            provider=mock_video_provider,
        )
        
        manifest = await stage.execute(preview_manifest)
        
        assert manifest.stage == "video"
        assert len(manifest.scenes) == 1
    
    @pytest.mark.asyncio
    async def test_operation_tracking(self, workspace, sample_config, mock_video_provider):
        """Operation IDs tracked for crash recovery."""
        from magnific.core.manifest import PreviewManifest, PreviewResult, atomic_write_manifest
        from magnific.core.tracking import OperationTracker
        
        preview_manifest = PreviewManifest(
            job_id=workspace.root.name,
            stage="preview",
            parent_manifest="story_manifest.json",
            scenes=[
                PreviewResult(
                    scene_id="scene_001",
                    scene_number=1,
                    title="Scene 1",
                    image_prompt="Test",
                    preview_path=workspace.resolve("previews", "scene_001.png", mkdir=True),
                    status=SceneStatus.SUCCESS,
                ),
            ],
        )
        
        from PIL import Image
        Image.new("RGB", (50, 50)).save(workspace.resolve("previews", "scene_001.png"))
        atomic_write_manifest(preview_manifest, workspace.resolve("preview_manifest.json"))
        
        tracker = OperationTracker(workspace)
        
        stage = VideoStage(
            workspace=workspace,
            config=sample_config,
            provider=mock_video_provider,
        )
        
        await stage.execute(preview_manifest)
        
        # After completion, pending should be cleared
        pending = tracker.get_pending_operations()
        assert "scene_001" not in pending