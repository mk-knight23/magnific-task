"""Pre-flight validation gates - stops pipeline before wasting resources."""

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from magnific.core.errors import PreFlightError, DiskFullError
from magnific.core.security import WorkspaceManager

if TYPE_CHECKING:
    from magnific.core.security import JailedPath


class PreFlightChecker:
    """
    Pre-flight validation that stops the pipeline before it wastes:
    - API quota (token exhaustion)
    - Disk space (filling up mid-run)
    - Memory (loading huge images)
    - Money (starting jobs that will fail)
    
    Performs:
    1. Disk space check (before and during stages)
    2. Image validation (format, size)
    3. Image optimization (resize, compress to save tokens)
    4. API key validation (optional)
    """
    
    def __init__(
        self,
        workspace: WorkspaceManager,
        min_disk_gb: float = 1.0,
        max_image_pixels: int = 1024,
        max_image_mb: float = 10.0,
    ):
        self.workspace = workspace
        self.min_disk_bytes = min_disk_gb * 1024**3
        self.max_pixels = max_image_pixels
        self.max_image_bytes = int(max_image_mb * 1024**2)
    
    def validate_environment(self) -> None:
        """Run all pre-flight checks before pipeline starts."""
        self._check_disk()
    
    def check_disk_before_stage(self, stage_name: str) -> None:
        """
        Re-check disk before each stage.
        
        Video downloads can fill disk mid-run. This catches it.
        """
        usage = shutil.disk_usage(self.workspace.root)
        if usage.free < self.min_disk_bytes:
            raise DiskFullError(
                f"[{stage_name}] Insufficient disk space. "
                f"Need {self.min_disk_bytes / 1024**3:.1f}GB, "
                f"have {usage.free / 1024**3:.1f}GB free."
            )
    
    def process_reference_images(self, paths: list[Path]) -> list["JailedPath"]:
        """
        Optimize images to prevent token bloat and memory spikes.
        
        Steps:
        1. Validate existence and format
        2. Check size limits
        3. Resize if too large (save tokens)
        4. Strip EXIF (privacy, size)
        5. Compress to JPEG (consistent format)
        6. Store in jailed refs/ directory
        
        Returns:
            List of optimized image paths inside workspace
        """
        out_paths = []
        refs_dir = self.workspace.resolve("refs", mkdir=True)
        
        for i, path in enumerate(paths):
            # Validate path
            resolved = self.workspace.validate_external_path(path, f"Reference image {i+1}")
            
            # Check file size
            file_size = resolved.stat().st_size
            if file_size > self.max_image_bytes:
                raise PreFlightError(
                    f"Reference image {i+1} too large: {file_size / 1024**2:.1f}MB "
                    f"(max {self.max_image_bytes / 1024**2:.1f}MB)"
                )
            
            # Validate and optimize
            out_path = refs_dir / f"char_{i+1}_optimized.jpg"
            
            try:
                # Convert JailedPath to str for PIL compatibility
                with Image.open(str(resolved)) as img:
                    # Validate format
                    if img.format not in ("JPEG", "PNG", "WEBP", "GIF"):
                        raise PreFlightError(
                            f"Reference image {i+1} unsupported format: {img.format}"
                        )
                    
                    # Resize if needed
                    max_dim = max(img.size)
                    if max_dim > self.max_pixels:
                        ratio = self.max_pixels / max_dim
                        new_size = (int(img.width * ratio), int(img.height * ratio))
                        img = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # Convert to RGB (strip alpha), compress
                    img.convert("RGB").save(
                        str(out_path),
                        "JPEG",
                        quality=85,
                        optimize=True,
                    )
                    
            except Exception as e:
                raise PreFlightError(
                    f"Failed to process reference image {i+1}: {e}"
                ) from e
            
            out_paths.append(out_path)
        
        return out_paths
    
    def _check_disk(self) -> None:
        """Check minimum disk space."""
        usage = shutil.disk_usage(self.workspace.root)
        if usage.free < self.min_disk_bytes:
            raise DiskFullError(
                f"Insufficient disk space. "
                f"Need {self.min_disk_bytes / 1024**3:.1f}GB, "
                f"have {usage.free / 1024**3:.1f}GB free."
            )