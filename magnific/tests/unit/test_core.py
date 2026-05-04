"""Unit tests for core modules."""

import pytest
from pathlib import Path

from magnific.core.errors import SecurityViolationError, PreFlightError
from magnific.core.security import WorkspaceManager
from magnific.core.tracking import OperationTracker
from magnific.core.manifest import StoryManifest, atomic_write_manifest
from magnific.core.retry import ErrorClassifier, ErrorAction


class TestWorkspaceManager:
    """Tests for security jail."""
    
    def test_resolve_inside_jail(self, workspace):
        """Normal path resolution works."""
        path = workspace.resolve("subdir", "file.txt", mkdir=True)
        assert path.exists()
        assert workspace.contains(path)
    
    def test_reject_path_traversal(self, workspace):
        """Path traversal blocked."""
        with pytest.raises(SecurityViolationError):
            workspace.resolve("..", "..", "etc", "passwd")
    
    def test_reject_absolute_path(self, workspace, tmp_path):
        """Absolute path outside jail blocked."""
        external = tmp_path / "external.txt"
        external.touch()
        
        with pytest.raises(SecurityViolationError):
            workspace.resolve(str(external))
    
    def test_symlink_escape_detected(self, workspace, tmp_path):
        """Symlink pointing outside jail blocked."""
        external = tmp_path / "external.txt"
        external.touch()
        
        link = workspace.resolve("link.txt")
        link.symlink_to(external)
        
        # Reading the symlink target should fail
        with pytest.raises(SecurityViolationError):
            workspace.resolve("link.txt", strict=True)


class TestOperationTracker:
    """Tests for ghost job defense."""
    
    def test_record_submission(self, workspace):
        """Submission recorded immediately."""
        tracker = OperationTracker(workspace)
        tracker.record_submission("scene_001", "op-123")
        
        pending = tracker.get_pending_operations()
        assert "scene_001" in pending
        assert pending["scene_001"][0] == "op-123"
    
    def test_mark_complete(self, workspace):
        """Completed scene removed from tracking."""
        tracker = OperationTracker(workspace)
        tracker.record_submission("scene_001", "op-123")
        
        asyncio.run(tracker.mark_complete("scene_001"))
        
        pending = tracker.get_pending_operations()
        assert "scene_001" not in pending
    
    def test_multiple_operations(self, workspace):
        """Multiple operations tracked."""
        tracker = OperationTracker(workspace)
        tracker.record_submission("s1", "op-1")
        tracker.record_submission("s2", "op-2")
        tracker.record_submission("s3", "op-3")
        
        pending = tracker.get_pending_operations()
        assert len(pending) == 3


class TestAtomicWrite:
    """Tests for atomic manifest writes."""
    
    def test_atomic_write_preserves_data(self, workspace, sample_story_manifest):
        """Atomic write preserves manifest data."""
        path = workspace.resolve("test_manifest.json")
        atomic_write_manifest(sample_story_manifest, path)
        
        loaded = StoryManifest.from_file(path)
        assert loaded.job_id == sample_story_manifest.job_id
        assert len(loaded.scenes) == len(sample_story_manifest.scenes)


class TestErrorClassifier:
    """Tests for error classification."""
    
    def test_rate_limit_retryable(self):
        """Rate limits are retryable."""
        from magnific.core.errors import RateLimitError
        
        error = RateLimitError("429 Too Many Requests")
        action = ErrorClassifier.classify(error)
        assert action == ErrorAction.RETRY
    
    def test_safety_filter_not_retryable(self):
        """Safety filters are NOT retryable."""
        from magnific.core.errors import SafetyFilterError
        
        error = SafetyFilterError("Content blocked by safety filter")
        action = ErrorClassifier.classify(error)
        assert action == ErrorAction.FAIL_SCENE


import asyncio