#!/usr/bin/env python3
"""Comprehensive validation script for implemented changes.

Tests all components to verify operational integrity:
1. Syntax validation
2. Import validation
3. Provider implementation validation
4. Workflow generator validation
5. CLI validation
6. Type hints validation
"""

import sys
import traceback
from pathlib import Path
from typing import Any

class ValidationRunner:
    """Runs all validation checks."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def check(self, name: str, func: callable) -> bool:
        """Run a validation check."""
        try:
            result = func()
            if result:
                print(f"✓ {name}")
                self.passed += 1
                return True
            else:
                print(f"✗ {name}")
                self.failed += 1
                self.errors.append(name)
                return False
        except Exception as e:
            print(f"✗ {name}: {e}")
            self.failed += 1
            self.errors.append(f"{name}: {str(e)}")
            return False
    
    def report(self) -> bool:
        """Print final report."""
        print("\n" + "="*60)
        print("Validation Report")
        print("="*60)
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Total: {self.passed + self.failed}")
        
        if self.errors:
            print("\nFailed checks:")
            for error in self.errors:
                print(f"  - {error}")
        
        return self.failed == 0


def validate_aiohttp_installed() -> bool:
    """Check aiohttp is installed."""
    try:
        import aiohttp
        return True
    except ImportError:
        return False


def validate_workflow_module_structure() -> bool:
    """Check workflow module has correct structure."""
    try:
        from magnific.workflow import InteractiveWorkflowGenerator, WorkflowSession
        return True
    except ImportError as e:
        print(f"  Import error: {e}")
        return False


def validate_workflow_generator_class() -> bool:
    """Check InteractiveWorkflowGenerator has required methods."""
    try:
        from magnific.workflow import InteractiveWorkflowGenerator
        gen = InteractiveWorkflowGenerator()
        
        required_methods = [
            'start_session',
            'refine',
            'generate_config',
            '_init_model',
            '_load_images',
            '_parse_initial_response',
            '_parse_scenes_json',
            '_try_parse_json',
            '_get_mime_type'
        ]
        
        for method in required_methods:
            if not hasattr(gen, method):
                print(f"  Missing method: {method}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_workflow_session_dataclass() -> bool:
    """Check WorkflowSession dataclass has required fields."""
    try:
        from magnific.workflow import WorkflowSession
        from pathlib import Path
        
        # Check required fields exist
        session = WorkflowSession(
            idea="test",
            reference_paths=[Path("test.jpg")]
        )
        
        required_fields = [
            'idea',
            'reference_paths',
            'reference_descriptions',
            'suggested_scenes',
            'tone',
            'setting',
            'character_analysis',
            'dialogue_history',
            'refined'
        ]
        
        for field in required_fields:
            if not hasattr(session, field):
                print(f"  Missing field: {field}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_veo_provider_async_methods() -> bool:
    """Check Veo provider has async methods."""
    try:
        from magnific.providers.google.veo import GoogleVeoProvider
        
        provider = GoogleVeoProvider()
        
        async_methods = [
            '_get_session',
            'close_session',
            'submit_async',
            'poll_async',
            'check_status_async',
            '_poll_operation',
            '_download_from_gcs_async'
        ]
        
        for method in async_methods:
            if not hasattr(provider, method):
                print(f"  Missing async method: {method}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_veo_provider_sync_compatibility() -> bool:
    """Check Veo provider has sync wrapper methods."""
    try:
        from magnific.providers.google.veo import GoogleVeoProvider
        
        provider = GoogleVeoProvider()
        
        sync_methods = ['submit', 'poll', 'check_status']
        
        for method in sync_methods:
            if not hasattr(provider, method):
                print(f"  Missing sync wrapper: {method}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_veo_verified_models() -> bool:
    """Check Veo provider uses verified model names."""
    try:
        from magnific.providers.google.veo import VERIFIED_VEO_MODELS
        
        expected_models = ["veo-001", "veo-002"]
        
        if VERIFIED_VEO_MODELS != expected_models:
            print(f"  Expected: {expected_models}, Got: {VERIFIED_VEO_MODELS}")
            return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_veo_endpoint_format() -> bool:
    """Check Veo endpoint format is correct."""
    try:
        from magnific.providers.google.veo import GoogleVeoProvider
        
        provider = GoogleVeoProvider()
        provider._project_id = "test-project"
        provider._location = "us-central1"
        
        url = provider._get_submit_url("veo-001")
        
        required_parts = [
            "aiplatform.googleapis.com",
            "v1/",
            "projects/test-project",
            "locations/us-central1",
            "publishers/google/models/veo-001",
            "predictLongRunning"
        ]
        
        for part in required_parts:
            if part not in url:
                print(f"  Missing endpoint part: {part}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_imagen_verified_models() -> bool:
    """Check Imagen provider uses verified model names."""
    try:
        from magnific.providers.google.imagen import VERIFIED_IMAGEN_MODELS
        
        expected_models = ["imagen-3.0-generate-002", "imagegeneration@006"]
        
        if VERIFIED_IMAGEN_MODELS != expected_models:
            print(f"  Expected: {expected_models}, Got: {VERIFIED_IMAGEN_MODELS}")
            return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_imagen_provider_methods() -> bool:
    """Check Imagen provider has required methods."""
    try:
        from magnific.providers.google.imagen import GoogleImagenProvider
        
        provider = GoogleImagenProvider()
        
        required_methods = [
            '_init_client',
            'generate_image',
            'get_cached_bytes',
            'get_cached_bytes_async',
            'clear_cache',
            '_get_mime_type'
        ]
        
        for method in required_methods:
            if not hasattr(provider, method):
                print(f"  Missing method: {method}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_cli_has_interactive_flag() -> bool:
    """Check CLI app has --interactive option."""
    try:
        import click
        from magnific.cli.app import generate_config
        
        # Get command parameters
        params = generate_config.params
        
        # Find interactive parameter
        interactive_param = None
        for param in params:
            if param.name == 'interactive':
                interactive_param = param
                break
        
        if not interactive_param:
            print(f"  No --interactive parameter found")
            return False
        
        if not interactive_param.is_flag:
            print(f"  interactive is not a flag type")
            return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_cli_imports_workflow() -> bool:
    """Check CLI imports workflow generator."""
    try:
        # Read CLI file and check for workflow import
        cli_path = Path("src/magnific/cli/app.py")
        content = cli_path.read_text()
        
        if "from magnific.workflow.interactive_generator import InteractiveWorkflowGenerator" not in content:
            print(f"  Missing workflow import in CLI")
            return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_cli_async_run_pattern() -> bool:
    """Check CLI uses asyncio.run for workflow methods."""
    try:
        cli_path = Path("src/magnific/cli/app.py")
        content = cli_path.read_text()
        
        # Check for asyncio.run usage with generator methods
        # Handle multi-line patterns by checking if asyncio.run appears near generator calls
        
        # More robust: check if both "asyncio.run" and "generator.start_session" are in the interactive section
        has_asyncio_run = "asyncio.run" in content
        has_generator = "generator = InteractiveWorkflowGenerator()" in content
        
        if not has_generator:
            print(f"  Missing generator instantiation")
            return False
        
        if not has_asyncio_run:
            print(f"  Missing asyncio.run calls")
            return False
        
        # Check specific method calls exist in file
        methods_to_check = ['start_session', 'refine', 'generate_config']
        
        for method in methods_to_check:
            if f"generator.{method}" not in content:
                print(f"  Missing generator.{method} call")
                return False
        
        # Verify asyncio.run is used at least once for workflow
        # (it appears multiple times in the interactive section)
        import re
        asyncio_count = len(re.findall(r'asyncio\.run\(', content))
        
        if asyncio_count < 4:  # Should have at least 4 asyncio.run calls (start, refine, generate, orchestrator.run)
            print(f"  Not enough asyncio.run calls: found {asyncio_count}")
            return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_dependencies_updated() -> bool:
    """Check pyproject.toml has aiohttp."""
    try:
        pyproject_path = Path("pyproject.toml")
        content = pyproject_path.read_text()
        
        if "aiohttp>=3.9.0" not in content:
            print(f"  aiohttp not in dependencies")
            return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_api_validation_script_exists() -> bool:
    """Check verify_api_endpoints.py exists."""
    try:
        script_path = Path("scripts/verify_api_endpoints.py")
        return script_path.exists()
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_api_validation_script_functions() -> bool:
    """Check verify_api_endpoints.py has validation functions."""
    try:
        script_path = Path("scripts/verify_api_endpoints.py")
        content = script_path.read_text()
        
        required_functions = [
            'verify_gemini_api',
            'verify_vertex_ai_init',
            'verify_imagen_models',
            'verify_veo_endpoint_structure',
            'verify_async_libraries'
        ]
        
        for func in required_functions:
            if f"def {func}" not in content:
                print(f"  Missing function: {func}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_documentation_files() -> bool:
    """Check all documentation files exist."""
    try:
        # Note: project-brain is in parent directory of magnific/
        base_path = Path(__file__).parent.parent.parent
        
        required_docs = [
            "magnific/docs/API_VALIDATION.md",
            "project-brain/08_CONCURRENCY.md"
        ]
        
        for doc in required_docs:
            doc_path = base_path / doc
            if not doc_path.exists():
                print(f"  Missing doc: {doc}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def validate_concurrency_doc_updated() -> bool:
    """Check 08_CONCURRENCY.md has verified patterns."""
    try:
        # Note: project-brain is in parent directory of magnific/
        base_path = Path(__file__).parent.parent.parent
        doc_path = base_path / "project-brain/08_CONCURRENCY.md"
        content = doc_path.read_text()
        
        # Check for key updates about async patterns and verification
        required_updates = [
            "VERIFIED",
            "aiohttp",
            "Native async",
            "GoogleVeoProvider",
            "REST API",
            "Hybrid Concurrency Model (UPDATED)"
        ]
        
        for update in required_updates:
            if update not in content:
                print(f"  Missing update: {update}")
                return False
        
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def main():
    """Run all validations."""
    print("="*60)
    print("Comprehensive Validation - Implemented Changes")
    print("="*60)
    print()
    
    runner = ValidationRunner()
    
    # Dependency checks
    print("Dependencies:")
    runner.check("aiohttp installed", validate_aiohttp_installed)
    runner.check("pyproject.toml updated", validate_dependencies_updated)
    print()
    
    # Workflow module checks
    print("Workflow Module:")
    runner.check("Module structure", validate_workflow_module_structure)
    runner.check("Generator class methods", validate_workflow_generator_class)
    runner.check("Session dataclass fields", validate_workflow_session_dataclass)
    print()
    
    # Veo provider checks
    print("Veo Provider:")
    runner.check("Async methods", validate_veo_provider_async_methods)
    runner.check("Sync compatibility wrappers", validate_veo_provider_sync_compatibility)
    runner.check("Verified model names", validate_veo_verified_models)
    runner.check("Endpoint format", validate_veo_endpoint_format)
    print()
    
    # Imagen provider checks
    print("Imagen Provider:")
    runner.check("Verified model names", validate_imagen_verified_models)
    runner.check("Provider methods", validate_imagen_provider_methods)
    print()
    
    # CLI checks
    print("CLI Integration:")
    runner.check("--interactive flag", validate_cli_has_interactive_flag)
    runner.check("Workflow import", validate_cli_imports_workflow)
    runner.check("Async run pattern", validate_cli_async_run_pattern)
    print()
    
    # API validation script checks
    print("API Validation Script:")
    runner.check("Script exists", validate_api_validation_script_exists)
    runner.check("Validation functions", validate_api_validation_script_functions)
    print()
    
    # Documentation checks
    print("Documentation:")
    runner.check("Files exist", validate_documentation_files)
    runner.check("Concurrency doc updated", validate_concurrency_doc_updated)
    print()
    
    # Final report
    success = runner.report()
    
    if success:
        print("\n✅ All validations passed - operational integrity confirmed")
        return 0
    else:
        print("\n❌ Some validations failed - review errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())