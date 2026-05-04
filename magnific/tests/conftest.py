"""Test fixtures for magnific tests."""

import asyncio
import pytest
import tempfile
from pathlib import Path
from PIL import Image

from magnific.core.security import WorkspaceManager
from magnific.core.tracking import OperationTracker
from magnific.config.models import PipelineConfig, JobInputConfig


@pytest.fixture
def temp_dir():
    """Create temporary directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def workspace(temp_dir):
    """Create test workspace."""
    job_dir = temp_dir / "test-job"
    return WorkspaceManager(job_dir)


@pytest.fixture
def sample_config(temp_dir):
    """Create sample pipeline config."""
    ref1 = temp_dir / "char1.jpg"
    ref2 = temp_dir / "char2.jpg"
    
    # Create sample images
    Image.new("RGB", (100, 100), color="red").save(ref1)
    Image.new("RGB", (100, 100), color="blue").save(ref2)
    
    return PipelineConfig(
        job=JobInputConfig(
            idea="A test story about two characters",
            reference_images=[ref1, ref2],
        ),
        output={"base_dir": temp_dir / "jobs"},
    )


@pytest.fixture
def sample_story_manifest(workspace):
    """Create sample story manifest."""
    from magnific.core.manifest import StoryManifest, ScenePrompt
    
    return StoryManifest(
        job_id=workspace.root.name,
        stage="story",
        scenes=[
            ScenePrompt(
                scene_id="scene_001",
                scene_number=1,
                title="Scene 1",
                image_prompt="A detailed test prompt with sufficient length for Pydantic validation that describes the scene with cinematic details and lighting specifications",
                duration_seconds=5,
            ),
            ScenePrompt(
                scene_id="scene_002",
                scene_number=2,
                title="Scene 2",
                image_prompt="Another detailed test prompt meeting the minimum length requirement with character descriptions and environmental context for testing",
                duration_seconds=5,
            ),
        ],
    )


@pytest.fixture
def mock_story_provider():
    """Mock story provider."""
    from magnific.providers.mock import MockStoryProvider
    return MockStoryProvider(scene_count=3)


@pytest.fixture
def mock_image_provider():
    """Mock image provider."""
    from magnific.providers.mock import MockImageProvider
    return MockImageProvider()


@pytest.fixture
def mock_video_provider():
    """Mock video provider."""
    from magnific.providers.mock import MockVideoProvider
    return MockVideoProvider(operation_delay=0.5)