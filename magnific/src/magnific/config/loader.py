"""Configuration loading with YAML merging and env var validation."""

import os
from pathlib import Path
from typing import Any, Optional
import yaml
from pydantic import ValidationError

from magnific.config.models import PipelineConfig
from magnific.core.errors import ConfigValidationError, InvalidApiKeyError


class ConfigLoader:
    """
    Configuration loader with hierarchy support.
    
    Precedence (highest to lowest):
    1. CLI arguments (--set overrides)
    2. Job-specific config (workflow.yaml)
    3. User defaults (~/.magnific/config.yaml)
    4. System defaults (embedded in package)
    
    Environment variables:
    - GOOGLE_API_KEY: Required for Google APIs
    - MAGNIFIC_CONFIG: Path to default config
    """
    
    DEFAULT_CONFIG_NAME = "default.yaml"
    
    @classmethod
    def load(
        cls,
        config_path: Optional[Path] = None,
        overrides: Optional[dict[str, Any]] = None,
    ) -> PipelineConfig:
        """
        Load configuration from file with defaults and overrides.
        
        Args:
            config_path: Path to workflow config (optional)
            overrides: CLI --set overrides
            
        Returns:
            Validated PipelineConfig
            
        Raises:
            ConfigValidationError: Schema validation failed
        """
        # Load default config
        default = cls._load_default_config()
        
        # Load job-specific config
        job_config = {}
        if config_path:
            job_config = cls._load_yaml_file(config_path)
        
        # Merge: job config overrides defaults
        merged = cls._merge_configs(default, job_config)
        
        # Apply CLI overrides
        if overrides:
            merged = cls._apply_overrides(merged, overrides)
        
        # Validate with Pydantic
        try:
            config = PipelineConfig.model_validate(merged)
        except ValidationError as e:
            raise ConfigValidationError(
                f"Configuration validation failed:\n{cls._format_validation_errors(e)}"
            ) from e
        
        return config
    
    @classmethod
    def validate_api_key(cls) -> str:
        """
        Validate that GOOGLE_API_KEY is set.
        
        Returns:
            The API key value
            
        Raises:
            InvalidApiKeyError: API key missing
        """
        key = os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise InvalidApiKeyError(
                "GOOGLE_API_KEY environment variable not set. "
                "Set it before running: export GOOGLE_API_KEY='your-key'"
            )
        return key
    
    @classmethod
    def generate_workflow_config(
        cls,
        idea: str,
        reference_images: list[Path],
        output_path: Path,
        template_path: Optional[Path] = None,
    ) -> PipelineConfig:
        """
        Generate a workflow config from user inputs.
        
        Args:
            idea: Creative brief
            reference_images: Character reference image paths
            output_path: Where to write the config
            template_path: Optional base template
            
        Returns:
            Generated PipelineConfig
        """
        # Load template
        template = {}
        if template_path:
            template = cls._load_yaml_file(template_path)
        else:
            template = cls._load_default_config()
        
        # Inject job inputs
        template.setdefault("job", {})
        template["job"]["idea"] = idea
        template["job"]["reference_images"] = [str(p) for p in reference_images]
        
        # Validate
        config = PipelineConfig.model_validate(template)
        
        # Write to output
        cls._write_yaml_file(output_path, template)
        
        return config
    
    @classmethod
    def _load_default_config(cls) -> dict[str, Any]:
        """Load system default config."""
        # Check for MAGNIFIC_CONFIG env var
        env_config = os.environ.get("MAGNIFIC_CONFIG")
        if env_config:
            return cls._load_yaml_file(Path(env_config))
        
        # Check for user config
        user_config = Path.home() / ".magnific" / "config.yaml"
        if user_config.exists():
            return cls._load_yaml_file(user_config)
        
        # Use embedded defaults
        default_path = Path(__file__).parent.parent.parent.parent / "config" / cls.DEFAULT_CONFIG_NAME
        if default_path.exists():
            return cls._load_yaml_file(default_path)
        
        # Return minimal defaults
        return cls._get_embedded_defaults()
    
    @classmethod
    def _load_yaml_file(cls, path: Path) -> dict[str, Any]:
        """Load YAML file safely."""
        if not path.exists():
            raise ConfigValidationError(f"Config file not found: {path}")
        
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"YAML parsing error in {path}: {e}") from e
    
    @classmethod
    def _write_yaml_file(cls, path: Path, data: dict[str, Any]) -> None:
        """Write YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    @classmethod
    def _merge_configs(cls, base: dict, override: dict) -> dict[str, Any]:
        """Deep merge two configs (override wins)."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    @classmethod
    def _apply_overrides(cls, config: dict, overrides: dict[str, Any]) -> dict:
        """Apply CLI --set overrides (key.path=value)."""
        for key_path, value in overrides.items():
            keys = key_path.split(".")
            current = config
            
            # Navigate to the target key
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            
            # Set the value
            current[keys[-1]] = value
        
        return config
    
    @classmethod
    def _format_validation_errors(cls, error: ValidationError) -> str:
        """Format Pydantic validation errors for display."""
        lines = []
        for err in error.errors():
            loc = ".".join(str(x) for x in err["loc"])
            lines.append(f"  {loc}: {err['msg']}")
        return "\n".join(lines)
    
    @classmethod
    def _get_embedded_defaults(cls) -> dict[str, Any]:
        """Get minimal embedded defaults."""
        return {
            "models": {
                "story": {"name": "gemini-2.0-flash-exp", "temperature": 0.7},
                "preview": {"name": "imagen-3.0-generate-002", "aspect_ratio": "16:9"},
                "video": {"name": "veo-2.0-generate-001", "duration_seconds": 5},
            },
            "preview_concurrency": {"max_concurrent": 3, "rate_limit_rpm": 20},
            "video_concurrency": {"max_concurrent_polls": 10, "poll_interval_seconds": 10},
            "retry": {"max_attempts": 5, "base_delay_seconds": 2.0},
            "safety": {"min_disk_gb": 1.0, "max_image_pixels": 1024},
            "output": {"base_dir": "./jobs"},
        }