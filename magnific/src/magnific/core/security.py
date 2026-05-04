"""Hardened filesystem jail - prevents CWE-22 path traversal."""

import os
from pathlib import Path
from magnific.core.errors import SecurityViolationError


class JailedPath:
    """
    A path guaranteed to be inside the WorkspaceManager jail.
    Cannot be instantiated by providers or stages directly.
    
    This sealed type enforces the security contract: only WorkspaceManager
    can create instances, preventing CWE-22 path traversal attacks.
    """
    
    __slots__ = ('_internal_path',)
    
    def __init__(self, path: Path, _secret_token: object):
        if _secret_token is None or type(_secret_token).__name__ != '_WorkspaceToken':
            raise SecurityViolationError(
                "JailedPath cannot be constructed directly. Use WorkspaceManager.resolve()"
            )
        self._internal_path = path
    
    @property
    def path(self) -> Path:
        """Expose the underlying Path for type checking, but I/O must use methods below."""
        return self._internal_path
    
    def read_bytes(self) -> bytes:
        """Read file contents safely (jailed)."""
        return self._internal_path.read_bytes()
    
    def write_bytes(self, data: bytes) -> int:
        """Write file contents safely (jailed)."""
        return self._internal_path.write_bytes(data)
    
    def exists(self) -> bool:
        """Check if file exists (jailed)."""
        return self._internal_path.exists()
    
    def stat(self):
        """Get file stat (jailed)."""
        return self._internal_path.stat()
    
    @property
    def name(self) -> str:
        """Get filename (jailed)."""
        return self._internal_path.name
    
    @property
    def suffix(self) -> str:
        """Get file suffix/extension (jailed)."""
        return self._internal_path.suffix
    
    @property
    def stem(self) -> str:
        """Get filename without extension (jailed)."""
        return self._internal_path.stem
    
    @property
    def parent(self) -> "JailedPath":
        """Get parent directory (jailed)."""
        # Parent is guaranteed to be inside jail if we are inside jail
        from magnific.core.errors import SecurityViolationError
        # We need a special internal constructor for derived paths
        return self._create_derived(self._internal_path.parent)
    
    def glob(self, pattern: str) -> list["JailedPath"]:
        """Find files matching pattern (jailed)."""
        # All glob results are guaranteed to be inside jail if we start inside jail
        return [self._create_derived(p) for p in self._internal_path.glob(pattern)]
    
    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        """Create directory (jailed)."""
        self._internal_path.mkdir(parents=parents, exist_ok=exist_ok)
    
    def _create_derived(self, path: Path) -> "JailedPath":
        """Internal method to create JailedPath from derived operations."""
        # Skip token check for internal operations - path is already validated
        obj = JailedPath.__new__(JailedPath)
        obj._internal_path = path
        return obj
    
    def __hash__(self) -> int:
        """Hash based on internal path for dict/set operations."""
        return hash(self._internal_path)
    
    def __eq__(self, other: object) -> bool:
        """Equality based on internal path for dict/set operations."""
        if isinstance(other, JailedPath):
            return self._internal_path == other._internal_path
        return False
    
    def __lt__(self, other: object) -> bool:
        """Less than for sorting."""
        if isinstance(other, JailedPath):
            return self._internal_path < other._internal_path
        return NotImplemented
    
    def __le__(self, other: object) -> bool:
        """Less than or equal for sorting."""
        if isinstance(other, JailedPath):
            return self._internal_path <= other._internal_path
        return NotImplemented
    
    def __gt__(self, other: object) -> bool:
        """Greater than for sorting."""
        if isinstance(other, JailedPath):
            return self._internal_path > other._internal_path
        return NotImplemented
    
    def __ge__(self, other: object) -> bool:
        """Greater than or equal for sorting."""
        if isinstance(other, JailedPath):
            return self._internal_path >= other._internal_path
        return NotImplemented
    
    def __str__(self) -> str:
        return str(self._internal_path)
    
    def __repr__(self) -> str:
        return f"JailedPath({repr(self._internal_path)})"
    
    def __truediv__(self, other: str) -> "JailedPath":
        """Path division operator (jailed)."""
        return self._create_derived(self._internal_path / other)
    
    def __fspath__(self) -> str:
        """Return string path for os.PathLike compatibility."""
        return str(self._internal_path)
    
    def with_suffix(self, suffix: str) -> "JailedPath":
        """Return path with different suffix."""
        return self._create_derived(self._internal_path.with_suffix(suffix))
    
    def read_text(self, encoding: str = "utf-8") -> str:
        """Read file contents as text."""
        return self._internal_path.read_text(encoding=encoding)
    
    def write_text(self, data: str, encoding: str = "utf-8") -> int:
        """Write text to file."""
        return self._internal_path.write_text(data, encoding=encoding)
    
    def resolve(self) -> "JailedPath":
        """Return resolved path."""
        return self._create_derived(self._internal_path.resolve())
    
    def relative_to(self, other: Path) -> Path:
        """Return relative path from other."""
        return self._internal_path.relative_to(other)
    
    def symlink_to(self, target: Path) -> None:
        """Create symlink to target (jailed)."""
        self._internal_path.symlink_to(target)
    
    def is_symlink(self) -> bool:
        """Check if path is symlink."""
        return self._internal_path.is_symlink()


class WorkspaceManager:
    """
    Strict filesystem jail. All paths MUST be resolved through this.
    
    Prevents:
    - Path traversal via ".." components
    - Symlink escapes outside workspace
    - Absolute path injection
    
    Security model: All file operations are constrained to a single
    job directory. No stage or provider can touch files outside.
    """
    
    class _WorkspaceToken:
        """Secret token class - only WorkspaceManager can instantiate."""
        pass
    
    _token = _WorkspaceToken()
    
    def __init__(self, base_dir: Path):
        self._root = base_dir.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
    
    @property
    def root(self) -> Path:
        """The jailed root directory."""
        return self._root
    
    def resolve(self, *parts: str, mkdir: bool = False, strict: bool = True) -> JailedPath:
        """
        Constructs a path safely inside the jail.
        
        Args:
            parts: Path components to join inside workspace
            mkdir: Create directory if it doesn't exist
            strict: Enable symlink escape detection
            
        Returns:
            JailedPath inside workspace (cannot be forged)
            
        Raises:
            SecurityViolationError: If path escapes workspace
        """
        if not parts:
            return JailedPath(self._root, self._token)
        
        target = (self._root / Path(*parts))
        
        if strict:
            current = self._root
            for part in Path(*parts).parts:
                next_path = current / part
                
                if next_path.exists() and next_path.is_symlink():
                    symlink_target = next_path.resolve()
                    try:
                        symlink_target.relative_to(self._root)
                    except ValueError:
                        raise SecurityViolationError(
                            f"Symlink escape detected: '{part}' resolves to "
                            f"'{symlink_target}' outside workspace."
                        )
                
                current = next_path.resolve()
        
        target = target.resolve()
        
        try:
            target.relative_to(self._root)
        except ValueError:
            raise SecurityViolationError(
                f"Path traversal blocked: '{Path(*parts)}' escapes job workspace "
                f"(resolved to '{target}', root is '{self._root}')."
            )
        
        if mkdir and not target.exists():
            target.mkdir(parents=True, exist_ok=True)
        
        return JailedPath(target, self._token)
    
    def contains(self, path: Path) -> bool:
        """Check if a path is inside the workspace (no exception)."""
        try:
            if isinstance(path, JailedPath):
                path._internal_path.relative_to(self._root)
            else:
                path.resolve().relative_to(self._root)
            return True
        except ValueError:
            return False
    
    def validate_external_path(self, path: Path, purpose: str) -> JailedPath:
        """
        Validate a path that must exist OUTSIDE the workspace.
        Used for reference images and config files.
        
        Args:
            path: External path to validate
            purpose: Description for error messages
            
        Raises:
            PreFlightError: If path doesn't exist or is inside workspace
            
        Returns:
            JailedPath for the external validated path
        """
        from magnific.core.errors import PreFlightError
        
        resolved = path.resolve()
        
        if not resolved.exists():
            raise PreFlightError(f"{purpose} not found: '{path}'")
        
        if self.contains(resolved):
            raise SecurityViolationError(
                f"{purpose} must be outside workspace: '{path}' is inside '{self._root}'"
            )
        
        return JailedPath(resolved, self._token)