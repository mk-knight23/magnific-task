"""Ghost Job Defense - tracks cloud operations for crash recovery."""

import asyncio
import json
import os
import time
from pathlib import Path
from magnific.core.security import WorkspaceManager
from magnific.core.errors import MagnificError


class OperationTracker:
    """
    Append-only state store for cloud operations.
    
    Prevents "ghost jobs" - Veo operations that continue running in the cloud
    after a local crash, costing money but producing orphaned results.
    
    Design:
    - Submission: Append operation ID immediately (crash-safe)
    - Completion: Atomic rewrite with async lock (race condition safe)
    - Resume: Load pending operations, resume polling or re-submit
    
    Format: JSONL (JSON Lines) for crash resilience
    {"scene_id": "s1", "op_id": "veo-123", "ts": 1705312200}
    """
    
    def __init__(self, workspace: WorkspaceManager):
        self._file = workspace.resolve("pending_operations.jsonl")
        self._lock = asyncio.Lock()
    
    def record_submission(self, scene_id: str, operation_id: str) -> None:
        """
        Writes immediately. Append-only is extremely crash-resilient.
        
        This is called the microsecond we receive an operation ID from Veo.
        Even if power is pulled 1ms later, this record survives.
        """
        payload = {
            "scene_id": scene_id,
            "op_id": operation_id,
            "ts": time.time(),
        }
        with open(self._file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    
    async def mark_complete(self, scene_id: str) -> None:
        """
        Removes a scene from tracking once MP4 is safely local.
        
        Uses async lock to prevent race conditions when multiple videos
        complete simultaneously.
        
        Atomic rewrite pattern:
        1. Read all pending
        2. Remove completed scene
        3. Write to temp file
        4. Atomic rename
        """
        async with self._lock:
            pending = self._load_pending()
            pending.pop(scene_id, None)
            
            # Atomic write pattern
            tmp_file = self._file.with_suffix(".jsonl.tmp")
            lines = [
                json.dumps({"scene_id": s, "op_id": o, "ts": t})
                for s, (o, t) in pending.items()
            ]
            
            if lines:
                tmp_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            else:
                # Empty file for empty pending
                tmp_file.write_text("", encoding="utf-8")
            
            os.replace(tmp_file, self._file)
    
    def get_pending_operations(self, max_age_seconds: float = 3600) -> dict[str, tuple[str, float]]:
        """
        On resume, find operations that never finished.
        
        Args:
            max_age_seconds: Operations older than this may have expired
                             on Google's side and need re-submission
        
        Returns:
            Dict of scene_id -> (operation_id, timestamp)
        """
        return self._load_pending(max_age_seconds)
    
    def _load_pending(self, max_age_seconds: float = float("inf")) -> dict[str, tuple[str, float]]:
        """Internal loader with age filtering."""
        if not self._file.exists():
            return {}
        
        pending = {}
        now = time.time()
        
        for line in self._file.read_text(encoding="utf-8").strip().splitlines():
            if not line:
                continue
            try:
                data = json.loads(line)
                scene_id = data["scene_id"]
                op_id = data["op_id"]
                ts = data.get("ts", 0)
                
                # Filter stale operations (likely expired on Google's side)
                if now - ts <= max_age_seconds:
                    pending[scene_id] = (op_id, ts)
            except json.JSONDecodeError:
                continue
        
        return pending
    
    def clear_all(self) -> None:
        """Clear all pending operations (after successful job completion)."""
        if self._file.exists():
            self._file.write_text("", encoding="utf-8")