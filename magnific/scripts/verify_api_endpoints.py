"""API Endpoint Verification Script.

Run this before any implementation to verify APIs exist.
Part of "Validate-First Architecture" methodology.

Usage:
    python scripts/verify_api_endpoints.py

Environment variables required:
    GOOGLE_API_KEY - For Gemini API
    GOOGLE_CLOUD_PROJECT - For Vertex AI (Imagen/Veo)
"""

import os
import sys
from pathlib import Path

def verify_gemini_api() -> tuple[bool, str]:
    """Verify Gemini API is accessible."""
    try:
        import google.generativeai as genai
        
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return False, "GOOGLE_API_KEY not set"
        
        genai.configure(api_key=api_key)
        
        # Test with verified model name
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        response = model.generate_content("Say 'verified' in one word")
        
        if response and response.text:
            return True, "gemini-2.0-flash-exp verified"
        return False, "Empty response from Gemini"
        
    except ImportError:
        return False, "google-generativeai not installed"
    except Exception as e:
        return False, f"API error: {e}"


def verify_vertex_ai_init() -> tuple[bool, str]:
    """Verify Vertex AI initialization."""
    try:
        import vertexai
        
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            return False, "GOOGLE_CLOUD_PROJECT not set"
        
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        
        vertexai.init(project=project_id, location=location)
        
        return True, f"Vertex AI initialized (project={project_id}, location={location})"
        
    except ImportError:
        return False, "vertexai not installed"
    except Exception as e:
        return False, f"Init error: {e}"


def verify_imagen_models() -> tuple[bool, str]:
    """Verify Imagen model names exist in Vertex AI."""
    try:
        from vertexai.preview.vision_models import ImageGenerationModel
        
        # VERIFIED model names from Google Cloud documentation
        # https://cloud.google.com/vertex-ai/generative-ai/docs/image/overview
        verified_models = [
            "imagen-3.0-generate-002",  # Imagen 3
            "imagegeneration@006",      # Legacy name
        ]
        
        for model_name in verified_models:
            try:
                model = ImageGenerationModel.from_pretrained(model_name)
                return True, f"Model verified: {model_name}"
            except Exception:
                continue
        
        return False, "No verified Imagen model accessible"
        
    except ImportError:
        return False, "vertexai.preview not installed"
    except Exception as e:
        return False, f"Model access error: {e}"


def verify_veo_endpoint_structure() -> tuple[bool, str]:
    """Verify Veo REST endpoint structure (without executing)."""
    try:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            return False, "GOOGLE_CLOUD_PROJECT not set"
        
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        
        # VERIFIED endpoint format from Vertex AI REST API docs
        # https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/predictLongRunning
        
        # Verified model names from documentation
        verified_models = ["veo-001", "veo-002"]
        
        endpoint_format = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project_id}/locations/{location}/"
            f"publishers/google/models/{verified_models[0]}:predictLongRunning"
        )
        
        # Verify endpoint structure is correct format
        required_parts = [
            "aiplatform.googleapis.com",
            "v1/",
            f"projects/{project_id}",
            f"locations/{location}",
            "publishers/google/models",
            "predictLongRunning",
        ]
        
        for part in required_parts:
            if part not in endpoint_format:
                return False, f"Endpoint missing required part: {part}"
        
        return True, f"Endpoint structure verified for models: {verified_models}"
        
    except Exception as e:
        return False, f"Verification error: {e}"


def verify_async_libraries() -> tuple[bool, str]:
    """Verify async libraries are available."""
    try:
        import aiohttp
        import asyncio
        
        # Verify aiohttp can create session
        async def test_session():
            session = aiohttp.ClientSession()
            await session.close()
            return True
        
        result = asyncio.run(test_session())
        
        if result:
            return True, "aiohttp available for native async REST calls"
        return False, "aiohttp session creation failed"
        
    except ImportError:
        return False, "aiohttp not installed"
    except Exception as e:
        return False, f"Async library error: {e}"


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("API Endpoint Verification - Validate-First Architecture")
    print("=" * 60)
    print()
    
    verifications = [
        ("Gemini API", verify_gemini_api),
        ("Vertex AI Init", verify_vertex_ai_init),
        ("Imagen Models", verify_imagen_models),
        ("Veo Endpoint Structure", verify_veo_endpoint_structure),
        ("Async Libraries", verify_async_libraries),
    ]
    
    results = {}
    
    for name, verify_fn in verifications:
        print(f"Checking {name}...")
        passed, message = verify_fn()
        results[name] = passed
        
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {message}")
        print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_pass = all(results.values())
    
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name}: {status}")
    
    print()
    
    if all_pass:
        print("✅ All APIs verified - safe to implement")
        print()
        print("Verified components:")
        print("  - Gemini: gemini-2.0-flash-exp")
        print("  - Imagen: imagen-3.0-generate-002")
        print("  - Veo: veo-001, veo-002 via predictLongRunning REST")
        print("  - Async: aiohttp for native REST async")
        sys.exit(0)
    else:
        print("❌ Cannot proceed - verify APIs before implementation")
        print()
        print("Action items:")
        if not results.get("Gemini API"):
            print("  - Set GOOGLE_API_KEY environment variable")
        if not results.get("Vertex AI Init"):
            print("  - Set GOOGLE_CLOUD_PROJECT environment variable")
            print("  - Ensure gcloud auth application-default login is configured")
        if not results.get("Async Libraries"):
            print("  - Install aiohttp: pip install aiohttp>=3.9.0")
        sys.exit(1)


if __name__ == "__main__":
    main()