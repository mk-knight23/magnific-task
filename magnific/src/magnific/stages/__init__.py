"""Stage module exports."""

from magnific.stages.base import BaseStage
from magnific.stages.story import StoryStage
from magnific.stages.preview import PreviewStage
from magnific.stages.video import VideoStage

STAGE_REGISTRY: dict[str, type[BaseStage]] = {
    "story": StoryStage,
    "preview": PreviewStage,
    "video": VideoStage,
}

STAGE_ORDER = ["story", "preview", "video"]

__all__ = [
    "BaseStage",
    "StoryStage",
    "PreviewStage",
    "VideoStage",
    "STAGE_REGISTRY",
    "STAGE_ORDER",
]