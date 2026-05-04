"""Advanced prompt enhancement utilities for cinematic quality."""

import re
from typing import Optional


class CinematicPromptEnhancer:
    """
    Enhances prompts with additional technical specifications
    for cinematic-grade image and video generation.
    
    Based on SAEST framework research.
    """
    
    # Lighting physics terminology database
    LIGHTING_ENHANCEMENTS = {
        "golden hour": "warm 3200K amber tones with soft penumbra shadows",
        "blue hour": "cool 5600K blue-white tones with atmospheric haze",
        "midday": "harsh 10000K contrast lighting with deep contact shadows",
        "indoor": "tungsten 3200K warm artificial lighting with soft fill",
        "night": "low-key dramatic lighting with rim light accent",
        "studio": "professional three-point lighting key fill rim",
    }
    
    # Camera lens specifications database
    LENS_SPECS = {
        "wide": "24mm wide-angle with slight barrel distortion and deep focus",
        "normal": "50mm standard lens with natural perspective f/8 aperture",
        "portrait": "85mm portrait lens shallow depth f/1.4 bokeh background",
        "telephoto": "200mm telephoto compression effect shallow depth",
        "macro": "100mm macro lens extreme detail reproduction f/2.8",
    }
    
    # Motion physics database
    MOTION_PHYSICS = {
        "walking": "steady pace 1.5m/s with natural gait rhythm 2-second cycle",
        "running": "sprint velocity 8m/s with acceleration bursts",
        "slow": "deliberate movement 0.3m/s smooth trajectory",
        "fast": "rapid action 5m/s with motion blur trails",
        "rotation": "centrifugal physics with angular velocity °/s",
        "falling": "gravity acceleration 9.8m/s² downward trajectory",
    }
    
    # Quality boosters
    QUALITY_BOOSTERS = [
        "8K ultra-detailed",
        "photorealistic rendering",
        "Octane raytraced",
        "Unreal Engine 5 quality",
        "anti-aliasing sharp edges",
        "volumetric atmosphere",
        "subsurface scattering",
        "ambient occlusion",
        "global illumination",
        "HDR color depth",
    ]
    
    # Film stocks color science
    FILM_STOCKS = {
        "kodak": "Kodak Vision3 500T warm saturated color science",
        "fuji": "Fujifilm Velvia 50 vibrant greens blues",
        "digital": "ARRI ALEXA digital color science neutral",
        "cinematic": "35mm film grain 0.3 opacity cinematic texture",
    }
    
    def enhance_image_prompt(
        self,
        base_prompt: str,
        lighting_type: Optional[str] = None,
        lens_type: Optional[str] = None,
        film_stock: Optional[str] = None,
    ) -> str:
        """
        Enhance image generation prompt with technical specifications.
        
        Args:
            base_prompt: Original prompt from scene generation
            lighting_type: Optional lighting specification key
            lens_type: Optional lens specification key
            film_stock: Optional film stock key
            
        Returns:
            Enhanced prompt with added technical details
        """
        enhanced = base_prompt
        
        # Add lighting physics if not already specified
        if lighting_type and not self._has_lighting_physics(enhanced):
            lighting_spec = self.LIGHTING_ENHANCEMENTS.get(lighting_type, "")
            if lighting_spec:
                enhanced += f", {lighting_spec}"
        
        # Add lens specifications if not already detailed
        if lens_type and not self._has_lens_specs(enhanced):
            lens_spec = self.LENS_SPECS.get(lens_type, "")
            if lens_spec:
                enhanced += f", {lens_spec}"
        
        # Add film stock if not specified
        if film_stock and not self._has_film_stock(enhanced):
            film_spec = self.FILM_STOCKS.get(film_stock, "")
            if film_spec:
                enhanced += f", {film_spec}"
        
        # Add quality boosters if missing
        if not self._has_quality_markers(enhanced):
            # Add 2-3 quality boosters
            boosters = self.QUALITY_BOOSTERS[:3]
            enhanced += f", {', '.join(boosters)}"
        
        # Ensure character consistency note
        if not self._has_consistency_note(enhanced):
            enhanced += ", maintain exact character visual identity from references"
        
        return enhanced
    
    def enhance_video_prompt(
        self,
        base_prompt: str,
        motion_type: Optional[str] = None,
        camera_movement: Optional[str] = None,
    ) -> str:
        """
        Enhance video generation prompt with motion physics and camera dynamics.
        
        Args:
            base_prompt: Original video prompt from scene
            motion_type: Optional motion physics key
            camera_movement: Optional camera movement specification
            
        Returns:
            Enhanced prompt with added motion and camera details
        """
        enhanced = base_prompt
        
        # Add motion physics if not specified
        if motion_type and not self._has_motion_physics(enhanced):
            motion_spec = self.MOTION_PHYSICS.get(motion_type, "")
            if motion_spec:
                enhanced += f", {motion_spec}"
        
        # Add temporal consistency anchor
        if not self._has_temporal_anchor(enhanced):
            enhanced += ", maintain visual consistency throughout entire sequence"
        
        # Add frame rate effect if not specified
        if not self._has_frame_rate(enhanced):
            enhanced += ", smooth 60fps motion interpolation with cinematic blur on fast movements"
        
        # Add camera smoothness if not specified
        if not self._has_camera_smoothness(enhanced):
            enhanced += ", gimbal stabilized smooth camera operation"
        
        return enhanced
    
    def add_reference_context(self, prompt: str, ref_count: int) -> str:
        """
        Add reference image context to prompt.
        
        Args:
            prompt: Base prompt
            ref_count: Number of reference images
            
        Returns:
            Prompt with reference context
        """
        if not self._has_reference_note(prompt):
            prompt += f", preserve exact visual characteristics from {ref_count} reference images"
        return prompt
    
    def _has_lighting_physics(self, prompt: str) -> bool:
        """Check if prompt has lighting physics terminology."""
        physics_terms = ["volumetric", "raytraced", "subsurface", "caustic", "penumbra", 
                        "ambient occlusion", "specular", "diffuse", "kelvin", "lux"]
        return any(term in prompt.lower() for term in physics_terms)
    
    def _has_lens_specs(self, prompt: str) -> bool:
        """Check if prompt has lens specifications."""
        lens_terms = ["mm", "aperture", "f/", "focal", "depth of field", "bokeh", "distortion"]
        return any(term in prompt.lower() for term in lens_terms)
    
    def _has_film_stock(self, prompt: str) -> bool:
        """Check if prompt has film stock reference."""
        film_terms = ["kodak", "fuji", "film", "grain", "color science", "vision"]
        return any(term in prompt.lower() for term in film_terms)
    
    def _has_quality_markers(self, prompt: str) -> bool:
        """Check if prompt has quality specifications."""
        quality_terms = ["8k", "4k", "ultra-detailed", "photorealistic", "octane", 
                        "unreal", "anti-aliasing", "hdr"]
        return any(term in prompt.lower() for term in quality_terms)
    
    def _has_consistency_note(self, prompt: str) -> bool:
        """Check if prompt has character consistency note."""
        consistency_terms = ["maintain", "preserve", "exact", "consistency", "reference"]
        return any(term in prompt.lower() for term in consistency_terms)
    
    def _has_motion_physics(self, prompt: str) -> bool:
        """Check if prompt has motion physics."""
        motion_terms = ["velocity", "acceleration", "gravity", "trajectory", "pace", "m/s"]
        return any(term in prompt.lower() for term in motion_terms)
    
    def _has_temporal_anchor(self, prompt: str) -> bool:
        """Check if prompt has temporal consistency anchor."""
        temporal_terms = ["consistency", "throughout", "sequence", "maintain", "stable"]
        return any(term in prompt.lower() for term in temporal_terms)
    
    def _has_frame_rate(self, prompt: str) -> bool:
        """Check if prompt has frame rate specification."""
        frame_terms = ["fps", "frame rate", "24fps", "60fps", "120fps", "motion blur"]
        return any(term in prompt.lower() for term in frame_terms)
    
    def _has_camera_smoothness(self, prompt: str) -> bool:
        """Check if prompt has camera smoothness."""
        smoothness_terms = ["smooth", "gimbal", "stabilized", "steady", "fluid"]
        return any(term in prompt.lower() for term in smoothness_terms)
    
    def _has_reference_note(self, prompt: str) -> bool:
        """Check if prompt has reference image note."""
        ref_terms = ["reference", "ref", "preserve characteristics", "exact visual"]
        return any(term in prompt.lower() for term in ref_terms)


def extract_motion_type(video_prompt: str) -> Optional[str]:
    """
    Extract motion type from video prompt for physics enhancement.
    
    Args:
        video_prompt: Video direction prompt
        
    Returns:
        Motion type key or None
    """
    prompt_lower = video_prompt.lower()
    
    if "walk" in prompt_lower or "step" in prompt_lower:
        return "walking"
    elif "run" in prompt_lower or "sprint" in prompt_lower:
        return "running"
    elif "slow" in prompt_lower or "gradual" in prompt_lower:
        return "slow"
    elif "fast" in prompt_lower or "quick" in prompt_lower or "rapid" in prompt_lower:
        return "fast"
    elif "spin" in prompt_lower or "rotate" in prompt_lower or "turn" in prompt_lower:
        return "rotation"
    elif "fall" in prompt_lower or "drop" in prompt_lower or "descend" in prompt_lower:
        return "falling"
    
    return None


def extract_lighting_type(image_prompt: str) -> Optional[str]:
    """
    Extract lighting type from image prompt for physics enhancement.
    
    Args:
        image_prompt: Image generation prompt
        
    Returns:
        Lighting type key or None
    """
    prompt_lower = image_prompt.lower()
    
    if "golden hour" in prompt_lower or "sunset" in prompt_lower or "dusk" in prompt_lower:
        return "golden hour"
    elif "blue hour" in prompt_lower or "twilight" in prompt_lower or "dawn" in prompt_lower:
        return "blue hour"
    elif "midday" in prompt_lower or "noon" in prompt_lower or "harsh sun" in prompt_lower:
        return "midday"
    elif "indoor" in prompt_lower or "inside" in prompt_lower or "interior" in prompt_lower:
        return "indoor"
    elif "night" in prompt_lower or "dark" in prompt_lower or "moonlight" in prompt_lower:
        return "night"
    elif "studio" in prompt_lower or "professional lighting" in prompt_lower:
        return "studio"
    
    return None


def extract_lens_type(image_prompt: str) -> Optional[str]:
    """
    Extract lens type from image prompt for specs enhancement.
    
    Args:
        image_prompt: Image generation prompt
        
    Returns:
        Lens type key or None
    """
    # Check for explicit focal length
    if "24mm" in image_prompt or "wide-angle" in image_prompt.lower():
        return "wide"
    elif "50mm" in image_prompt or "normal" in image_prompt.lower():
        return "normal"
    elif "85mm" in image_prompt or "portrait" in image_prompt.lower():
        return "portrait"
    elif "200mm" in image_prompt or "telephoto" in image_prompt.lower():
        return "telephoto"
    elif "macro" in image_prompt.lower() or "extreme close" in image_prompt.lower():
        return "macro"
    
    # Infer from shot type
    prompt_lower = image_prompt.lower()
    if "wide shot" in prompt_lower or "establishing" in prompt_lower:
        return "wide"
    elif "close-up" in prompt_lower or "portrait" in prompt_lower:
        return "portrait"
    elif "extreme close" in prompt_lower:
        return "macro"
    
    # Default for cinematic shots
    return "portrait"