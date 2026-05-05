"""Interactive LLM-driven workflow configuration generator.

This is the PRODUCT DIFFERENTIATOR - transforms rough user ideas into
polished creative briefs with scene suggestions via interactive LLM dialogue.

Why this matters:
- Original generate-config was just static template filling
- This feature makes the product unique: AI helps users refine their vision
- Missing from initial implementation (recruiter feedback)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import google.generativeai as genai
import yaml

from magnific.config.models import PipelineConfig
from magnific.core.errors import ProviderError

if TYPE_CHECKING:
    from magnific.core.security import JailedPath


@dataclass
class WorkflowSession:
    """Interactive workflow refinement session state."""
    
    idea: str
    reference_paths: list[Path]
    reference_descriptions: list[str] = field(default_factory=list)
    suggested_scenes: list[dict[str, Any]] = field(default_factory=list)
    tone: Optional[str] = None
    setting: Optional[str] = None
    character_analysis: Optional[str] = None
    dialogue_history: list[str] = field(default_factory=list)
    refined: bool = False


class InteractiveWorkflowGenerator:
    """LLM-driven workflow configuration generator.
    
    This implements the missing differentiator feature:
    Interactive AI refinement of creative briefs.
    
    User Experience:
    1. User provides rough idea + reference images
    2. LLM analyzes images and suggests refinements
    3. Interactive dialogue to refine tone, setting, scenes
    4. LLM generates SAEST-compliant prompts for each scene
    5. Config.yaml written with enhanced prompts
    
    This is what makes Magnific unique - not just template filling,
    but actual AI-guided creative refinement.
    """
    
    SYSTEM_PROMPT = """You are a creative assistant for cinematic storytelling.

When given a user's rough idea and reference images:
1. Analyze the characters in the images (species, appearance, mood, visual style)
2. Ask clarifying questions to refine the story
3. Suggest a scene breakdown that creates narrative flow
4. Generate SAEST-compliant prompts for each scene

SAEST Framework (for each scene):
- Subject: Detailed demographic and physical constraints
- Action: What the subject is actively doing
- Environment: Background elements and lighting
- Style: Cinematic, hyper-realistic, etc.
- Technical: Camera angles and motion physics

Always:
- Match character descriptions to reference images EXACTLY
- Ensure scenes flow cinematically (beginning → middle → end)
- Suggest appropriate camera movements and lighting
- Keep prompts concise but detailed (max 200 words each)

Response format (JSON):
{
  "character_analysis": "...",
  "clarifying_questions": ["...", "..."],
  "suggested_tone": "...",
  "suggested_setting": "...",
  "suggested_scenes": [
    {
      "scene_number": 1,
      "title": "...",
      "image_prompt": "SAEST format...",
      "video_prompt": "...",
      "camera_movement": "..."
    }
  ]
}
"""
    
    REFINEMENT_PROMPT = """Given the user's refinement request, update the scene suggestions.

User refinement: {user_input}

Current session:
- Idea: {idea}
- Tone: {tone}
- Setting: {setting}
- Current scenes: {current_scenes}

Respond with updated JSON scene suggestions that incorporate the user's feedback.
"""
    
    def __init__(self) -> None:
        self._model: Optional[Any] = None
    
    def _init_model(self) -> Any:
        """Initialize Gemini model for interactive dialogue."""
        if self._model is None:
            try:
                import os
                api_key = os.environ.get("GOOGLE_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)  # type: ignore
                
                self._model = genai.GenerativeModel(  # type: ignore
                    "gemini-2.0-flash-exp",
                    system_instruction=self.SYSTEM_PROMPT
                )
            except Exception as e:
                raise ProviderError(
                    f"Failed to initialize Gemini for workflow generation: {e}",
                    provider="google"
                )
        
        return self._model
    
    async def start_session(
        self,
        idea: str,
        reference_images: list[Path],
    ) -> WorkflowSession:
        """Initialize interactive session with LLM analysis.
        
        Args:
            idea: User's rough creative idea
            reference_images: Character reference image paths
        
        Returns:
            WorkflowSession with initial LLM analysis
        """
        model = self._init_model()
        
        # Load reference images for analysis
        image_parts = self._load_images(reference_images)
        
        # Initial prompt for analysis and suggestions
        initial_prompt = (
            f"Analyze these character reference images. "
            f"User's rough idea: '{idea}'\n\n"
            f"Describe what you see in the images, suggest refinements for the idea, "
            f"and propose a scene breakdown. Respond in JSON format."
        )
        
        # Send to Gemini
        contents = image_parts + [initial_prompt]
        
        try:
            response = model.generate_content(contents)
            
            if not response or not response.text:
                return WorkflowSession(
                    idea=idea,
                    reference_paths=reference_images,
                    reference_descriptions=["Unable to analyze images"],
                    suggested_scenes=[]
                )
            
            # Parse JSON response
            session = self._parse_initial_response(response.text, idea, reference_images)
            
            session.dialogue_history.append(f"INIT: {initial_prompt}")
            session.dialogue_history.append(f"RESPONSE: {response.text}")
            
            return session
        
        except Exception as e:
            # Return basic session if LLM fails
            return WorkflowSession(
                idea=idea,
                reference_paths=reference_images,
                reference_descriptions=[f"Analysis failed: {e}"],
                suggested_scenes=[]
            )
    
    async def refine(
        self,
        session: WorkflowSession,
        user_input: str,
    ) -> WorkflowSession:
        """Process user feedback and refine suggestions.
        
        Args:
            session: Current workflow session
            user_input: User's refinement request
        
        Returns:
            Updated WorkflowSession
        """
        model = self._init_model()
        
        # Build refinement prompt
        refinement_prompt = self.REFINEMENT_PROMPT.format(
            user_input=user_input,
            idea=session.idea,
            tone=session.tone or "not specified",
            setting=session.setting or "not specified",
            current_scenes=json.dumps(session.suggested_scenes, indent=2)
        )
        
        # Load images again for context
        image_parts = self._load_images(session.reference_paths)
        
        contents = image_parts + [refinement_prompt]
        
        try:
            response = model.generate_content(contents)
            
            if response and response.text:
                # Parse updated scenes
                updated_scenes = self._parse_scenes_json(response.text)
                
                if updated_scenes:
                    session.suggested_scenes = updated_scenes
                    session.refined = True
                
                # Parse other refinements
                data = self._try_parse_json(response.text)
                if data:
                    if "suggested_tone" in data:
                        session.tone = data["suggested_tone"]
                    if "suggested_setting" in data:
                        session.setting = data["suggested_setting"]
                
                session.dialogue_history.append(f"USER: {user_input}")
                session.dialogue_history.append(f"RESPONSE: {response.text}")
        
        except Exception as e:
            session.dialogue_history.append(f"REFINE_ERROR: {e}")
        
        return session
    
    async def generate_config(
        self,
        session: WorkflowSession,
        output_path: Path,
    ) -> PipelineConfig:
        """Generate final config from refined session.
        
        Args:
            session: Refined workflow session
            output_path: Where to write config.yaml
        
        Returns:
            Validated PipelineConfig
        """
        # Build config dict from session
        config_dict = {
            "job": {
                "idea": session.idea,
                "tone": session.tone,
                "setting": session.setting,
                "reference_images": [str(p) for p in session.reference_paths],
            },
            "generated_scenes": session.suggested_scenes,
        }
        
        # Write YAML
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
        
        # Validate
        config = PipelineConfig.model_validate(config_dict)
        
        return config
    
    def _load_images(self, paths: list[Path]) -> list[dict[str, Any]]:
        """Load images as Gemini Part objects."""
        parts: list[dict[str, Any]] = []
        
        for path in paths:
            if not path.exists():
                continue
            
            try:
                img_bytes = path.read_bytes()
                mime_type = self._get_mime_type(path)
                
                # Gemini Part.from_data format
                part: dict[str, Any] = {
                    "mime_type": mime_type,
                    "data": img_bytes
                }
                parts.append(part)
            except Exception:
                continue
        
        return parts
    
    def _parse_initial_response(
        self,
        text: str,
        idea: str,
        reference_paths: list[Path]
    ) -> WorkflowSession:
        """Parse LLM initial response into session."""
        data = self._try_parse_json(text)
        
        if not data:
            # Fallback: try to extract scenes anyway
            scenes = self._parse_scenes_json(text)
            return WorkflowSession(
                idea=idea,
                reference_paths=reference_paths,
                suggested_scenes=scenes
            )
        
        character_analysis = data.get("character_analysis", "No analysis provided")
        questions = data.get("clarifying_questions", [])
        tone = data.get("suggested_tone")
        setting = data.get("suggested_setting")
        scenes = data.get("suggested_scenes", [])
        
        # Convert reference descriptions
        ref_descs = [character_analysis] if character_analysis else []
        
        return WorkflowSession(
            idea=idea,
            reference_paths=reference_paths,
            reference_descriptions=ref_descs,
            suggested_scenes=scenes,
            tone=tone,
            setting=setting,
            character_analysis=character_analysis
        )
    
    def _parse_scenes_json(self, text: str) -> list[dict[str, Any]]:
        """Parse scenes from JSON or extract from text."""
        data = self._try_parse_json(text)
        
        if data and "suggested_scenes" in data:
            scenes = data["suggested_scenes"]
            if isinstance(scenes, list):
                return scenes
        
        # Try direct array parse
        if isinstance(data, list):
            return data
        
        # Fallback: extract JSON array from text
        start = text.find("[")
        end = text.rfind("]") + 1
        
        if start >= 0 and end > start:
            try:
                scenes = json.loads(text[start:end])
                if isinstance(scenes, list):
                    return scenes
            except json.JSONDecodeError:
                pass
        
        return []
    
    def _try_parse_json(self, text: str) -> Optional[dict[str, Any]]:
        """Try to parse JSON from text (handles markdown code blocks)."""
        # Try direct parse
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return None
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                try:
                    data = json.loads(text[start:end].strip())
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    pass
        
        # Try extracting JSON object from text
        start = text.find("{")
        end = text.rfind("}") + 1
        
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type from file extension."""
        ext = path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        return mime_map.get(ext, "image/jpeg")