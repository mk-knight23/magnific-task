"""Pydantic manifest models with atomic writes."""

import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class SceneStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class JobStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    PAUSED = "paused"


class ScenePrompt(BaseModel):
    """A single scene from Stage 1 (story generation) with SAEST framework."""
    scene_id: str = Field(description="Unique scene identifier")
    scene_number: int = Field(ge=1, description="Scene order")
    title: str = Field(min_length=1, description="Scene title")
    image_prompt: str = Field(min_length=50, description="Multi-layered SAEST prompt for image generation (200-300 words)")
    video_prompt: Optional[str] = Field(default=None, description="Motion vector prompt with camera dynamics (100-150 words)")
    duration_seconds: int = Field(default=8, ge=1, le=30, description="Target video duration")
    camera_movement: Optional[str] = Field(default=None, description="Cinematography camera movement specification")
    lighting_type: Optional[str] = Field(default=None, description="Primary lighting type (golden hour, blue hour, etc.)")
    status: SceneStatus = Field(default=SceneStatus.PENDING)
    error: Optional[str] = Field(default=None, description="Error message if failed")


class PreviewResult(BaseModel):
    """A preview image from Stage 2 with enhanced metadata."""
    scene_id: str
    scene_number: int
    title: str
    image_prompt: str
    video_prompt: Optional[str] = Field(default=None, description="Video prompt from story stage")
    camera_movement: Optional[str] = Field(default=None, description="Camera movement from story stage")
    lighting_type: Optional[str] = Field(default=None, description="Lighting type from story stage")
    preview_path: Optional[Path] = Field(default=None, description="Path to preview image (accepts os.PathLike)")
    generation_time_ms: Optional[int] = Field(default=None)
    status: SceneStatus = SceneStatus.PENDING
    error: Optional[str] = None
    
    @field_validator("preview_path", mode="before")
    @classmethod
    def convert_pathlike(cls, v):
        """Convert any os.PathLike to Path."""
        if v is None:
            return None
        if hasattr(v, '__fspath__'):
            return Path(v.__fspath__())
        return Path(v)


class VideoResult(BaseModel):
    """A video from Stage 3."""
    scene_id: str
    scene_number: int
    title: str
    preview_path: Optional[Path] = None
    video_path: Optional[Path] = Field(default=None, description="Path to MP4 video (accepts os.PathLike)")
    video_duration_sec: Optional[float] = Field(default=None)
    operation_id: Optional[str] = Field(default=None, description="Veo operation ID")
    status: SceneStatus = SceneStatus.PENDING
    error: Optional[str] = None
    
    @field_validator("preview_path", "video_path", mode="before")
    @classmethod
    def convert_pathlike(cls, v):
        """Convert any os.PathLike to Path."""
        if v is None:
            return None
        if hasattr(v, '__fspath__'):
            return Path(v.__fspath__())
        return Path(v)


class BaseManifest(BaseModel):
    """Base class for all manifests."""
    job_id: str = Field(description="UUID of the job")
    stage: str = Field(description="Stage name")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "BaseManifest":
        """Deserialize from JSON string."""
        return cls.model_validate_json(json_str)
    
    @classmethod
    def from_file(cls, path: Path) -> "BaseManifest":
        """Load from file."""
        return cls.from_json(path.read_text(encoding="utf-8"))


class StoryManifest(BaseManifest):
    """Stage 1 output: List of scene prompts."""
    stage: str = "story"
    input_summary: dict[str, Any] = Field(default_factory=dict)
    scenes: list[ScenePrompt] = Field(default_factory=list)
    
    @property
    def total_scenes(self) -> int:
        return len(self.scenes)
    
    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.scenes if s.status == SceneStatus.SUCCESS)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.scenes if s.status in (SceneStatus.FAILED, SceneStatus.BLOCKED))
    
    @property
    def computed_status(self) -> JobStatus:
        if self.completed_count == self.total_scenes:
            return JobStatus.COMPLETE
        if self.failed_count == self.total_scenes:
            return JobStatus.FAILED
        if self.completed_count > 0:
            return JobStatus.PARTIAL
        return JobStatus.RUNNING


class PreviewManifest(BaseManifest):
    """Stage 2 output: Preview images per scene."""
    stage: str = "preview"
    parent_manifest: str = Field(description="Path to story manifest")
    scenes: list[PreviewResult] = Field(default_factory=list)
    
    @property
    def total_scenes(self) -> int:
        return len(self.scenes)
    
    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.scenes if s.status == SceneStatus.SUCCESS)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.scenes if s.status in (SceneStatus.FAILED, SceneStatus.BLOCKED))
    
    def get_successful_scenes(self) -> list[PreviewResult]:
        """Get scenes that have preview images ready for video."""
        return [s for s in self.scenes if s.status == SceneStatus.SUCCESS and s.preview_path]


class VideoManifest(BaseManifest):
    """Stage 3 output: MP4 videos per scene."""
    stage: str = "video"
    parent_manifest: str = Field(description="Path to preview manifest")
    scenes: list[VideoResult] = Field(default_factory=list)
    
    @property
    def total_scenes(self) -> int:
        return len(self.scenes)
    
    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.scenes if s.status == SceneStatus.SUCCESS)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.scenes if s.status in (SceneStatus.FAILED, SceneStatus.BLOCKED))
    
    def get_successful_videos(self) -> list[VideoResult]:
        """Get successfully generated videos."""
        return [s for s in self.scenes if s.status == SceneStatus.SUCCESS and s.video_path]


class JobStatusManifest(BaseManifest):
    """High-level job state tracking."""
    stage: str = "status"
    status: JobStatus = JobStatus.CREATED
    current_stage: Optional[str] = None
    stage_progress: dict[str, str] = Field(default_factory=dict)
    config_hash: Optional[str] = None
    error: Optional[str] = None
    
    @field_validator("stage_progress")
    @classmethod
    def validate_progress(cls, v: dict) -> dict:
        valid_stages = {"story", "preview", "video"}
        for stage, status in v.items():
            if stage not in valid_stages:
                raise ValueError(f"Invalid stage: {stage}")
        return v


def atomic_write_manifest(manifest: BaseManifest, path: Path) -> None:
    """
    Atomic write pattern: write to temp, then rename.
    
    Prevents corrupt manifests if power is pulled mid-write.
    POSIX guarantees os.replace() is atomic.
    
    Handles disk full gracefully by catching write errors before rename.
    """
    path = path.resolve() if hasattr(path, 'resolve') else Path(str(path)).resolve()
    tmp_path = path.with_suffix(".json.tmp")
    
    try:
        tmp_path.write_text(manifest.to_json(), encoding="utf-8")
        
        os.replace(tmp_path, path)
    except OSError as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise e