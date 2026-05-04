"""Pipeline orchestrator - coordinates all stages."""

import logging
import signal
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from magnific.config.models import PipelineConfig
from magnific.config.loader import ConfigLoader
from magnific.core.security import WorkspaceManager
from magnific.core.preflight import PreFlightChecker
from magnific.core.cost_tracker import CostTracker
from magnific.core.manifest import (
    JobStatus,
    JobStatusManifest,
    StoryManifest,
    PreviewManifest,
    VideoManifest,
    atomic_write_manifest,
)
from magnific.core.errors import StageNotFoundError, MagnificError, BudgetExceededError
from magnific.stages import STAGE_REGISTRY, STAGE_ORDER, BaseStage

logger = logging.getLogger(__name__)


_shutdown_requested = False


def _signal_handler(signum, frame):
    """Handle graceful shutdown signals."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.warning(
        "Shutdown signal received",
        extra={"signal": signum, "signal_name": signal.Signals(signum).name}
    )


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


class Orchestrator:
    """
    Pipeline orchestrator - the conductor.
    
    Responsibilities:
    - Create/load job context
    - Determine which stages to run (resume logic)
    - Execute stages in order
    - Handle failures gracefully
    - Write job status manifest
    
    Resume Logic:
    - --from-stage: Run from specified stage onward
    - Auto-detect: Check manifest files to find last successful stage
    
    Job Lifecycle:
    CREATED → RUNNING → [COMPLETE | PARTIAL | FAILED]
    """
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.job_id: Optional[str] = None
        self.workspace: Optional[WorkspaceManager] = None
        self.cost_tracker: Optional[CostTracker] = None
    
    async def run(
        self,
        job_id: Optional[str] = None,
        from_stage: Optional[str] = None,
        only_stage: Optional[str] = None,
    ) -> JobStatusManifest:
        """
        Execute the pipeline.
        
        Args:
            job_id: Existing job ID to resume (None creates new)
            from_stage: Start from this stage (None = auto-detect)
            only_stage: Run only this stage
        
        Returns:
            Final job status manifest
        """
        # Initialize job
        self.job_id = job_id or str(uuid.uuid4())
        job_dir = self.config.output.base_dir / self.job_id
        self.workspace = WorkspaceManager(job_dir)
        
        # Initialize cost tracker with budget limit
        self.cost_tracker = CostTracker(max_budget_usd=self.config.safety.max_budget_usd)
        
        logger.info(f"[orchestrator] Job ID: {self.job_id}", extra={"job_id": self.job_id})
        logger.info(
            f"[orchestrator] Workspace: {self.workspace.root}",
            extra={"job_id": self.job_id, "workspace": str(self.workspace.root)}
        )
        logger.info(
            f"[orchestrator] Budget: ${self.config.safety.max_budget_usd:.2f}",
            extra={"job_id": self.job_id, "budget_usd": self.config.safety.max_budget_usd}
        )
        
        # Initialize job status
        status_manifest = self._init_job_status()
        
        # Pre-flight checks (new jobs only)
        if job_id is None and self.config.job:
            self._run_preflight()
        
        # Determine execution plan
        stages_to_run = self._get_execution_plan(from_stage, only_stage)
        
        logger.info(f"[orchestrator] Stages to run: {stages_to_run}", extra={"job_id": self.job_id, "stages": stages_to_run})
        
        # Execute stages
        input_manifest = None
        
        for stage_name in stages_to_run:
            if _shutdown_requested:
                logger.error(
                    "Pipeline interrupted by shutdown signal",
                    extra={"job_id": self.job_id, "stage": stage_name}
                )
                status_manifest.status = JobStatus.PAUSED
                status_manifest.error = "Shutdown requested"
                if self.cost_tracker:
                    status_manifest.metadata["cost"] = self.cost_tracker.get_summary()
                self._update_job_status(status_manifest)
                raise KeyboardInterrupt("Graceful shutdown requested")
            
            try:
                status_manifest.current_stage = stage_name
                status_manifest.status = JobStatus.RUNNING
                status_manifest.stage_progress[stage_name] = "running"
                self._update_job_status(status_manifest)
                
                # Get stage class
                stage_cls = STAGE_REGISTRY.get(stage_name)
                if stage_cls is None:
                    raise ValueError(f"Unknown stage: {stage_name}")
                
                # Create stage instance
                stage = stage_cls(
                    workspace=self.workspace,
                    config=self.config,
                    cost_tracker=self.cost_tracker,
                )
                
                # Execute
                output_manifest = await stage.execute(input_manifest)
                
                # Add cost metadata to manifest
                if output_manifest and self.cost_tracker:
                    output_manifest.metadata["cost"] = self.cost_tracker.get_summary()
                
                # Update status
                status_manifest.stage_progress[stage_name] = "complete"
                self._update_job_status(status_manifest)
                
                # Log cost progress
                if self.cost_tracker:
                    logger.info(
                        f"[orchestrator] Stage {stage_name} complete. "
                        f"Cost so far: ${self.cost_tracker.get_current_cost():.2f}, "
                        f"Remaining: ${self.cost_tracker.get_budget_remaining():.2f}",
                        extra={
                            "job_id": self.job_id,
                            "stage": stage_name,
                            "cost_usd": self.cost_tracker.get_current_cost(),
                            "budget_remaining": self.cost_tracker.get_budget_remaining(),
                        }
                    )
                
                # Pass to next stage
                input_manifest = output_manifest
                
            except StageNotFoundError as e:
                logger.error(f"[orchestrator] Stage prerequisite missing: {e}")
                status_manifest.stage_progress[stage_name] = "failed"
                status_manifest.error = str(e)
                status_manifest.status = JobStatus.FAILED
                self._update_job_status(status_manifest)
                raise
            
            except BudgetExceededError as e:
                logger.error(f"[orchestrator] Budget exceeded during {stage_name}: {e}")
                status_manifest.stage_progress[stage_name] = "failed"
                status_manifest.error = f"Budget exceeded: {e}"
                status_manifest.status = JobStatus.FAILED
                
                # Add final cost summary
                if self.cost_tracker:
                    status_manifest.metadata["cost"] = self.cost_tracker.get_summary()
                
                self._update_job_status(status_manifest)
                raise
            
            except Exception as e:
                logger.error(f"[orchestrator] Stage {stage_name} failed: {e}")
                status_manifest.stage_progress[stage_name] = "failed"
                status_manifest.error = str(e)
                
                # Determine if we should continue
                if self.config.safety.fail_fast:
                    status_manifest.status = JobStatus.FAILED
                    
                    # Add cost summary on failure
                    if self.cost_tracker:
                        status_manifest.metadata["cost"] = self.cost_tracker.get_summary()
                    
                    self._update_job_status(status_manifest)
                    raise
                
                # Continue with partial results
                input_manifest = None
        
        # Determine final status
        complete_count = sum(
            1 for s in status_manifest.stage_progress.values()
            if s == "complete"
        )
        
        if complete_count == len(STAGE_ORDER):
            status_manifest.status = JobStatus.COMPLETE
        elif complete_count > 0:
            status_manifest.status = JobStatus.PARTIAL
        else:
            status_manifest.status = JobStatus.FAILED
        
        status_manifest.current_stage = None
        
        # Add final cost summary
        if self.cost_tracker:
            status_manifest.metadata["cost"] = self.cost_tracker.get_summary()
            logger.info(
                f"[orchestrator] Final cost: ${self.cost_tracker.get_current_cost():.2f} "
                f"(budget: ${self.config.safety.max_budget_usd:.2f})",
                extra={
                    "job_id": self.job_id,
                    "final_cost_usd": self.cost_tracker.get_current_cost(),
                    "budget_usd": self.config.safety.max_budget_usd,
                }
            )
        
        self._update_job_status(status_manifest)
        
        logger.info(
            f"[orchestrator] Final status: {status_manifest.status}",
            extra={"job_id": self.job_id, "status": status_manifest.status.value}
        )
        
        return status_manifest
    
    def _init_job_status(self) -> JobStatusManifest:
        """Initialize or load job status."""
        status_path = self.workspace.resolve("job_status.json")
        
        if status_path.exists():
            return JobStatusManifest.from_file(status_path)
        
        return JobStatusManifest(
            job_id=self.job_id,
            stage="status",
            status=JobStatus.CREATED,
            stage_progress={},
            metadata={
                "created_at": datetime.utcnow().isoformat(),
            },
        )
    
    def _update_job_status(self, manifest: JobStatusManifest) -> None:
        """Write job status atomically."""
        manifest.updated_at = datetime.utcnow()
        path = self.workspace.resolve("job_status.json")
        atomic_write_manifest(manifest, path)
    
    def _run_preflight(self) -> None:
        """Run pre-flight checks and optimize images."""
        checker = PreFlightChecker(
            self.workspace,
            min_disk_gb=self.config.safety.min_disk_gb,
            max_image_pixels=self.config.safety.max_image_pixels,
            max_image_mb=self.config.safety.max_image_mb,
        )
        
        # Validate environment
        checker.validate_environment()
        
        # Process reference images
        if self.config.job and self.config.job.reference_images:
            optimized_paths = checker.process_reference_images(
                self.config.job.reference_images
            )
            logger.info(f"[preflight] Optimized {len(optimized_paths)} reference images")
    
    def _get_execution_plan(
        self,
        from_stage: Optional[str],
        only_stage: Optional[str],
    ) -> list[str]:
        """
        Determine which stages to run.
        
        Logic:
        1. If only_stage: run just that stage
        2. If from_stage: run that stage and all after
        3. If neither: check manifests to find start point
        """
        if only_stage:
            if only_stage not in STAGE_REGISTRY:
                raise ValueError(f"Invalid stage: {only_stage}")
            return [only_stage]
        
        if from_stage:
            if from_stage not in STAGE_REGISTRY:
                raise ValueError(f"Invalid stage: {from_stage}")
            
            start_idx = STAGE_ORDER.index(from_stage)
            return STAGE_ORDER[start_idx:]
        
        # Auto-detect: find last complete stage
        for stage_name in STAGE_ORDER:
            manifest_path = self.workspace.resolve(f"{stage_name}_manifest.json")
            if not manifest_path.exists():
                # This stage hasn't run - start here
                start_idx = STAGE_ORDER.index(stage_name)
                return STAGE_ORDER[start_idx:]
        
        # All stages complete
        return []
    
    def get_job_summary(self) -> dict:
        """Get summary of current job."""
        if self.workspace is None:
            return {"error": "No job initialized"}
        
        summary = {
            "job_id": self.job_id,
            "workspace": str(self.workspace.root),
        }
        
        # Load all manifests
        for stage_name in STAGE_ORDER:
            path = self.workspace.resolve(f"{stage_name}_manifest.json")
            if path.exists():
                try:
                    manifest = self._load_stage_manifest(stage_name, path)
                    summary[f"{stage_name}_scenes"] = len(manifest.scenes)
                    summary[f"{stage_name}_success"] = getattr(manifest, "completed_count", 0)
                    summary[f"{stage_name}_failed"] = getattr(manifest, "failed_count", 0)
                except Exception:
                    pass
        
        # Load job status
        status_path = self.workspace.resolve("job_status.json")
        if status_path.exists():
            status = JobStatusManifest.from_file(status_path)
            summary["status"] = status.status.value
            summary["current_stage"] = status.current_stage
        
        return summary
    
    def _load_stage_manifest(self, stage_name: str, path: Path):
        """Load manifest by stage type."""
        if stage_name == "story":
            return StoryManifest.from_file(path)
        elif stage_name == "preview":
            return PreviewManifest.from_file(path)
        elif stage_name == "video":
            return VideoManifest.from_file(path)
        else:
            raise ValueError(f"Unknown stage: {stage_name}")