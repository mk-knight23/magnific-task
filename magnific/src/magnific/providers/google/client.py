"""Shared Google client setup - supports both AI Studio and Vertex AI."""

import os
from typing import Optional

from magnific.core.errors import InvalidApiKeyError


class GoogleClient:
    """
    Shared Google API client setup.
    
    Handles:
    - API key validation (AI Studio)
    - Vertex AI initialization (for Imagen/Veo)
    - ADC authentication
    
    Authentication modes:
    1. AI Studio API key (GOOGLE_API_KEY) - Gemini only
    2. Vertex AI ADC - All services (Gemini, Imagen, Veo)
    3. Vertex AI API key + project - All services
    """
    
    _api_key: Optional[str] = None
    _project_id: Optional[str] = None
    _location: Optional[str] = None
    _initialized: bool = False
    _vertex_initialized: bool = False
    
    @classmethod
    def get_api_key(cls) -> str:
        """Get Google API key (for Gemini via AI Studio or Vertex AI)."""
        if cls._api_key is None:
            cls._api_key = os.environ.get("GOOGLE_API_KEY")
            if not cls._api_key:
                # Try ADC instead
                cls._api_key = "adc"  # Placeholder for ADC
        return cls._api_key
    
    @classmethod
    def get_project_id(cls) -> str:
        """Get GCP project ID (required for Vertex AI)."""
        if cls._project_id is None:
            cls._project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not cls._project_id:
                raise InvalidApiKeyError(
                    "GOOGLE_CLOUD_PROJECT not set. "
                    "Required for Imagen and Veo via Vertex AI.\n"
                    "Export it: export GOOGLE_CLOUD_PROJECT='your-project-id'\n"
                    "Or set in config: vertex_ai.project_id"
                )
        return cls._project_id
    
    @classmethod
    def get_location(cls) -> str:
        """Get Vertex AI location/region."""
        if cls._location is None:
            cls._location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        return cls._location
    
    @classmethod
    def init_vertex_ai(cls) -> None:
        """Initialize Vertex AI (required for Imagen and Veo)."""
        if cls._vertex_initialized:
            return
        
        try:
            import vertexai
            
            project_id = cls.get_project_id()
            location = cls.get_location()
            
            # ADC or API key authentication
            api_key = os.environ.get("GOOGLE_API_KEY")
            if api_key and api_key != "adc":
                # Use API key
                vertexai.init(
                    project=project_id,
                    location=location,
                    api_key=api_key
                )
            else:
                # Use ADC (Application Default Credentials)
                vertexai.init(
                    project=project_id,
                    location=location
                )
            
            cls._vertex_initialized = True
            
        except ImportError:
            raise InvalidApiKeyError(
                "vertexai not installed. "
                "Install with: pip install google-cloud-aiplatform"
            )
    
    @classmethod
    def init_gemini(cls) -> None:
        """Initialize Gemini SDK (for story generation via AI Studio)."""
        if cls._initialized:
            return
        
        try:
            import google.generativeai as genai
            
            api_key = cls.get_api_key()
            if api_key != "adc":
                genai.configure(api_key=api_key)
            
            cls._initialized = True
            
        except ImportError:
            raise InvalidApiKeyError(
                "google-generativeai not installed. "
                "Install with: pip install google-generativeai"
            )
    
    @classmethod
    def validate_key(cls) -> bool:
        """Validate that required credentials are set."""
        try:
            cls.get_api_key()
            # For Gemini-only, project not needed
            return True
        except InvalidApiKeyError:
            return False
    
    @classmethod
    def validate_vertex_ai(cls) -> bool:
        """Validate Vertex AI credentials (project + location)."""
        try:
            cls.get_project_id()
            cls.get_location()
            return True
        except InvalidApiKeyError:
            return False
    
    @classmethod
    def reset(cls) -> None:
        """Reset client state (for testing)."""
        cls._api_key = None
        cls._project_id = None
        cls._location = None
        cls._initialized = False
        cls._vertex_initialized = False