"""Package initialization."""

__version__ = "1.0.0"
__author__ = "Magnific Team"

from magnific.config import ConfigLoader, PipelineConfig
from magnific.core import (
    WorkspaceManager,
    OperationTracker,
    PreFlightChecker,
    ErrorClassifier,
)
from magnific.orchestrator import Orchestrator
from magnific.stages import STAGE_REGISTRY, STAGE_ORDER

__all__ = [
    "__version__",
    "__author__",
    "ConfigLoader",
    "PipelineConfig",
    "WorkspaceManager",
    "OperationTracker",
    "PreFlightChecker",
    "ErrorClassifier",
    "Orchestrator",
    "STAGE_REGISTRY",
    "STAGE_ORDER",
]