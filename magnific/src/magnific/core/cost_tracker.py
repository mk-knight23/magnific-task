"""Cost tracking and budget enforcement - prevents runaway spending."""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from magnific.core.errors import BudgetExceededError


@dataclass
class CostAccumulator:
    """Tracks estimated API costs per job."""
    
    gemini_input_tokens: int = 0
    gemini_output_tokens: int = 0
    imagen_calls: int = 0
    veo_calls: int = 0
    veo_duration_seconds: int = 0
    
    # Cost rates (based on Google Cloud pricing May 2026)
    GEMINI_INPUT_RATE = 0.00125 / 1000  # $0.00125 per 1K input tokens
    GEMINI_OUTPUT_RATE = 0.005 / 1000   # $0.005 per 1K output tokens
    IMAGEN_RATE = 0.04                   # $0.04 per image (Imagen 4.0 Ultra)
    VEO_RATE = 0.25                      # $0.25 per second (Veo 3.0)
    
    @property
    def estimated_cost_usd(self) -> float:
        """Calculate total estimated cost."""
        gemini_cost = (
            self.gemini_input_tokens * self.GEMINI_INPUT_RATE +
            self.gemini_output_tokens * self.GEMINI_OUTPUT_RATE
        )
        imagen_cost = self.imagen_calls * self.IMAGEN_RATE
        veo_cost = self.veo_calls * self.veo_duration_seconds * self.VEO_RATE
        
        return gemini_cost + imagen_cost + veo_cost
    
    def to_dict(self) -> dict:
        """Serialize to dict for manifest metadata."""
        return {
            "gemini_input_tokens": self.gemini_input_tokens,
            "gemini_output_tokens": self.gemini_output_tokens,
            "imagen_calls": self.imagen_calls,
            "veo_calls": self.veo_calls,
            "veo_duration_seconds": self.veo_duration_seconds,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
        }


class CostTracker:
    """
    Enforces budget limits and tracks API usage.
    
    Prevents runaway costs by:
    1. Accumulating estimated costs per API call
    2. Checking budget threshold before each API call
    3. Aborting pipeline when budget exceeded
    
    Thread-safe via asyncio.Lock for concurrent stage execution.
    """
    
    def __init__(self, max_budget_usd: float):
        self._max_budget = max_budget_usd
        self._accumulator = CostAccumulator()
        self._lock = asyncio.Lock()
    
    async def check_before_gemini(
        self,
        estimated_input_tokens: int,
        estimated_output_tokens: int = 8192,
    ) -> None:
        """
        Check budget before Gemini call.
        
        Raises:
            BudgetExceededError: If estimated cost would exceed budget
        """
        async with self._lock:
            # Estimate additional cost
            additional_cost = (
                estimated_input_tokens * CostAccumulator.GEMINI_INPUT_RATE +
                estimated_output_tokens * CostAccumulator.GEMINI_OUTPUT_RATE
            )
            
            projected_cost = self._accumulator.estimated_cost_usd + additional_cost
            
            if projected_cost > self._max_budget:
                raise BudgetExceededError(
                    f"Budget exceeded. "
                    f"Current: ${self._accumulator.estimated_cost_usd:.2f}, "
                    f"Projected: ${projected_cost:.2f}, "
                    f"Limit: ${self._max_budget:.2f}"
                )
    
    async def record_gemini_usage(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record actual Gemini token usage."""
        async with self._lock:
            self._accumulator.gemini_input_tokens += input_tokens
            self._accumulator.gemini_output_tokens += output_tokens
            
            # Check if exceeded after actual usage
            if self._accumulator.estimated_cost_usd > self._max_budget:
                raise BudgetExceededError(
                    f"Budget exceeded after Gemini call. "
                    f"Total: ${self._accumulator.estimated_cost_usd:.2f}, "
                    f"Limit: ${self._max_budget:.2f}"
                )
    
    async def check_before_imagen(self) -> None:
        """Check budget before Imagen call."""
        async with self._lock:
            projected_cost = (
                self._accumulator.estimated_cost_usd + 
                CostAccumulator.IMAGEN_RATE
            )
            
            if projected_cost > self._max_budget:
                raise BudgetExceededError(
                    f"Budget exceeded. "
                    f"Current: ${self._accumulator.estimated_cost_usd:.2f}, "
                    f"Projected: ${projected_cost:.2f}, "
                    f"Limit: ${self._max_budget:.2f}"
                )
    
    async def record_imagen_call(self) -> None:
        """Record Imagen image generation."""
        async with self._lock:
            self._accumulator.imagen_calls += 1
            
            if self._accumulator.estimated_cost_usd > self._max_budget:
                raise BudgetExceededError(
                    f"Budget exceeded after Imagen call. "
                    f"Total: ${self._accumulator.estimated_cost_usd:.2f}, "
                    f"Limit: ${self._max_budget:.2f}"
                )
    
    async def check_before_veo(self, duration_seconds: int) -> None:
        """Check budget before Veo video generation."""
        async with self._lock:
            projected_cost = (
                self._accumulator.estimated_cost_usd +
                duration_seconds * CostAccumulator.VEO_RATE
            )
            
            if projected_cost > self._max_budget:
                raise BudgetExceededError(
                    f"Budget exceeded. "
                    f"Current: ${self._accumulator.estimated_cost_usd:.2f}, "
                    f"Projected: ${projected_cost:.2f}, "
                    f"Limit: ${self._max_budget:.2f}"
                )
    
    async def record_veo_call(self, duration_seconds: int) -> None:
        """Record Veo video generation."""
        async with self._lock:
            self._accumulator.veo_calls += 1
            self._accumulator.veo_duration_seconds += duration_seconds
            
            if self._accumulator.estimated_cost_usd > self._max_budget:
                raise BudgetExceededError(
                    f"Budget exceeded after Veo call. "
                    f"Total: ${self._accumulator.estimated_cost_usd:.2f}, "
                    f"Limit: ${self._max_budget:.2f}"
                )
    
    def get_summary(self) -> dict:
        """Get cost summary for manifest metadata."""
        return self._accumulator.to_dict()
    
    def get_current_cost(self) -> float:
        """Get current estimated cost."""
        return self._accumulator.estimated_cost_usd
    
    def get_budget_remaining(self) -> float:
        """Get remaining budget."""
        return max(0.0, self._max_budget - self._accumulator.estimated_cost_usd)