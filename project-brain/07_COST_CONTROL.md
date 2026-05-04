# 💰 07_COST_CONTROL.md: Budget Enforcement

## 1. Runaway Cost Risk
Without limits, a user could request 100 scenes, hit network retries, and rack up over $1600+ on Veo 3.0 diffusion costs.

## 2. The `CostTracker` Layer
A new tracking module prevents runaway spending.
- Uses `asyncio.Lock` to guarantee thread-safe counting during concurrent rendering.
- Before **ANY** cloud API is called, `tracker.check_before_[model]()` is invoked. If the projected cost exceeds `max_budget_usd`, a `BudgetExceededError` is raised, gracefully halting the pipeline immediately.

## 3. Strict Scene Truncation
The LLM prompt instructs Gemini to output 4-8 scenes. However, LLMs can hallucinate massive arrays.
- The `max_scenes` property hardcaps processing. 
- If the LLM generates 15 scenes, the pipeline forcibly truncates the array down to `max_scenes` before invoking any image or video diffusion models.

## 4. Input Token Validation Guard
Since users supply large reference images, they could accidentally exceed Gemini input limits.
- Before hitting Vertex AI, a rough formula: `system + user + (image_count * 500)` runs.
- It proactively fails the job if it exceeds cost/token buffers.
