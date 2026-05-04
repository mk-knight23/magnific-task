"""Base stage with hybrid async pattern."""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TypeVar

from magnific.core.security import WorkspaceManager
from magnific.core.manifest import BaseManifest, atomic_write_manifest
from magnific.core.retry import ErrorAction, ErrorClassifier, RetryConfig, RetryHandler
from magnific.core.cost_tracker import CostTracker
from magnific.config.models import PipelineConfig

T = TypeVar("T")


logger = logging.getLogger(__name__)


class BaseStage(ABC):
    """
    Abstract base for all pipeline stages.
    
    Implements:
    - Atomic manifest writes
    - Hybrid concurrency (sync SDKs in thread executor)
    - Retry logic with error classification
    - Workspace security
    - Cost tracking
    
    Subclasses implement execute() which is the actual stage logic.
    """
    
    def __init__(
        self,
        workspace: WorkspaceManager,
        config: PipelineConfig,
        stage_name: str,
        cost_tracker: Optional[CostTracker] = None,
    ):
        self.workspace = workspace
        self.config = config
        self.stage_name = stage_name
        self.retry_handler = RetryHandler(config.get_retry_config())
        self.cost_tracker = cost_tracker
    
    @abstractmethod
    async def execute(self, input_manifest: Optional[BaseManifest] = None) -> BaseManifest:
        """
        Execute the stage logic.
        
        Args:
            input_manifest: Input from previous stage (None for Stage 1)
        
        Returns:
            Output manifest for this stage
        """
        pass
    
    def atomic_write_manifest(self, manifest: BaseManifest, filename: str) -> None:
        """
        Atomic write to prevent corruption.
        
        Pattern: write to temp, then rename.
        """
        path = self.workspace.resolve(filename)
        atomic_write_manifest(manifest, path)
        logger.info(f"[{self.stage_name}] Wrote manifest: {filename}")
    
    @staticmethod
    async def run_sync_in_thread(
        sync_func: Callable[..., T],
        *args: Any,
        timeout: float = 300.0,
        **kwargs: Any,
    ) -> T:
        """
        Run synchronous function in thread executor.
        
        This is the Hybrid Concurrency Pattern.
        Google's genai/imagen SDKs are blocking.
        We run them in ThreadPoolExecutor so they don't freeze
        the asyncio event loop.
        
        Args:
            sync_func: Blocking function to run
            timeout: Max execution time (prevent hangs)
        
        Returns:
            Result of sync_func
        
        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            None,  # Default ThreadPoolExecutor
            lambda: sync_func(*args, **kwargs),
        )
        return await asyncio.wait_for(future, timeout=timeout)
    
    async def execute_with_retry(
        self,
        fn: Callable[[], Awaitable[T]],
        context: str = "",
    ) -> T:
        """
        Execute async function with retry logic.
        
        Uses error classification to decide:
        - RETRY: Backoff and retry
        - FAIL_SCENE: Mark failed, no retry
        - ABORT_JOB: Raise immediately
        """
        return await self.retry_handler.execute(fn)
    
    def should_retry_error(self, error: Exception) -> bool:
        """Check if error should be retried."""
        action = ErrorClassifier.classify(error)
        return action == ErrorAction.RETRY
    
    def check_disk_space(self) -> None:
        """Check disk before stage execution."""
        from magnific.core.preflight import PreFlightChecker
        
        checker = PreFlightChecker(
            self.workspace,
            min_disk_gb=self.config.safety.min_disk_gb,
        )
        checker.check_disk_before_stage(self.stage_name)
    
    def log_progress(self, message: str, scene_id: Optional[str] = None) -> None:
        """Log progress message with structured fields."""
        extra = {
            "job_id": self.workspace.root.name,
            "stage": self.stage_name,
        }
        if scene_id:
            extra["scene_id"] = scene_id
        if self.cost_tracker:
            extra["cost_usd"] = self.cost_tracker.get_current_cost()
        
        if scene_id:
            logger.info(f"[{self.stage_name}] [{scene_id}] {message}", extra=extra)
        else:
            logger.info(f"[{self.stage_name}] {message}", extra=extra)