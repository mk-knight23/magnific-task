"""Pydantic configuration schemas with safety caps."""

import os
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class StoryModelConfig(BaseModel):
    """Gemini model configuration."""
    provider: Literal["google", "mock"] = "google"
    name: str = Field(default="gemini-2.0-flash-exp", min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=8192, ge=1, le=65536)
    response_mime_type: str = "application/json"


class PreviewModelConfig(BaseModel):
    """Imagen model configuration."""
    provider: Literal["google", "mock"] = "google"
    name: str = Field(default="imagen-3.0-generate-002", min_length=1)
    aspect_ratio: str = Field(default="16:9")
    sample_count: int = Field(default=1, ge=1, le=4)
    person_generation: Literal["allow_all", "allow_adult", "dont_allow"] = "allow_all"


class VideoModelConfig(BaseModel):
    """Veo model configuration."""
    provider: Literal["google", "mock"] = "google"
    name: str = Field(default="veo-2.0-generate-001", min_length=1)
    aspect_ratio: str = Field(default="16:9")
    duration_seconds: int = Field(default=5, ge=1, le=30)


class ModelsConfig(BaseModel):
    """All model configurations."""
    story: StoryModelConfig = Field(default_factory=StoryModelConfig)
    preview: PreviewModelConfig = Field(default_factory=PreviewModelConfig)
    video: VideoModelConfig = Field(default_factory=VideoModelConfig)


class StoryPromptConfig(BaseModel):
    """Story generation prompts."""
    system_prompt: str = Field(
        default="""You are a creative director and storyboard artist. 
Given character reference images and a creative brief, generate a series of scene descriptions 
that will be turned into short animated video clips.

Each scene must:
1. Feature the exact characters from the reference images
2. Have a clear narrative progression
3. Be visually distinct from other scenes
4. Work as a standalone 5-second clip

Return a JSON array of scenes with this exact structure:
[
  {
    "scene_number": 1,
    "title": "Scene Title",
    "image_prompt": "Detailed prompt for image generation...",
    "video_prompt": "Optional video-specific direction...",
    "duration_seconds": 5
  }
]

Generate 4-8 scenes total."""
    )
    user_template: str = Field(
        default="""Character 1: [attached image]
Character 2: [attached image]

Creative brief: {brief}

Generate scene descriptions for this story."""
    )


class PreviewConcurrencyConfig(BaseModel):
    """Preview generation concurrency."""
    max_concurrent: int = Field(default=3, ge=1, le=10)
    rate_limit_rpm: int = Field(default=20, ge=1, le=100)


class VideoConcurrencyConfig(BaseModel):
    """Video generation concurrency."""
    max_concurrent_polls: int = Field(default=10, ge=1, le=50)
    poll_interval_seconds: float = Field(default=10.0, ge=5.0, le=60.0)
    poll_backoff_multiplier: float = Field(default=1.5, ge=1.0, le=3.0)
    max_poll_minutes: float = Field(default=30.0, ge=5.0, le=120.0)


class RetryPolicyConfig(BaseModel):
    """Retry policy for API calls."""
    max_attempts: int = Field(default=5, ge=1, le=10)
    base_delay_seconds: float = Field(default=2.0, ge=0.5, le=10.0)
    max_delay_seconds: float = Field(default=60.0, ge=10.0, le=300.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.5, le=4.0)
    jitter: bool = True


class SafetyConfig(BaseModel):
    """Safety and resource limits."""
    skip_on_safety_block: bool = True
    fail_fast: bool = False
    min_disk_gb: float = Field(default=1.0, ge=0.1, le=100.0)
    max_image_pixels: int = Field(default=1024, ge=256, le=4096)
    max_image_mb: float = Field(default=10.0, ge=1.0, le=50.0)
    max_budget_usd: float = Field(default=10.0, ge=0.1, le=1000.0, description="Maximum estimated budget in USD")
    max_scenes: int = Field(default=8, ge=1, le=20, description="Maximum number of scenes to generate")


class OutputConfig(BaseModel):
    """Output configuration."""
    base_dir: Path = Field(default=Path("./jobs"))
    
    @field_validator("base_dir", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        return Path(v).resolve()


class JobInputConfig(BaseModel):
    """Job-specific inputs (from workflow.yaml)."""
    idea: str = Field(min_length=10, description="Creative brief")
    reference_images: list[Path] = Field(min_length=2, max_length=2)
    
    @field_validator("reference_images", mode="before")
    @classmethod
    def resolve_paths(cls, v: list[str | Path]) -> list[Path]:
        return [Path(p).resolve() for p in v]


class PipelineConfig(BaseModel):
    """Complete pipeline configuration."""
    
    # Job inputs (required for run)
    job: Optional[JobInputConfig] = None
    
    # Models
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    
    # Prompts
    prompts: StoryPromptConfig = Field(default_factory=StoryPromptConfig)
    
    # Concurrency
    preview_concurrency: PreviewConcurrencyConfig = Field(default_factory=PreviewConcurrencyConfig)
    video_concurrency: VideoConcurrencyConfig = Field(default_factory=VideoConcurrencyConfig)
    
    # Retry
    retry: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    
    # Safety
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    
    # Output
    output: OutputConfig = Field(default_factory=OutputConfig)
    
    # Resume
    resume_from_stage: Optional[Literal["story", "preview", "video"]] = None
    
    @model_validator(mode="after")
    def validate_job_inputs(self) -> "PipelineConfig":
        """Validate that job inputs are provided for run command."""
        if self.resume_from_stage and self.job is None:
            raise ValueError("job inputs required even when resuming")
        return self
    
    def get_retry_config(self) -> "RetryPolicyConfig":
        """Get retry config as RetryConfig dataclass."""
        from magnific.core.retry import RetryConfig
        return RetryConfig(
            max_attempts=self.retry.max_attempts,
            base_delay_seconds=self.retry.base_delay_seconds,
            max_delay_seconds=self.retry.max_delay_seconds,
            backoff_multiplier=self.retry.backoff_multiplier,
            jitter=self.retry.jitter,
        )