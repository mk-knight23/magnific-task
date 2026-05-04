# 🧠 03_AI_SYSTEM.md: Models & Intelligence

## 1. Prompting Framework (SAEST)
Magnific enforces the **SAEST** prompting protocol to guarantee stability from the LLM.
- **S**ubject: Detailed demographic and physical constraints.
- **A**ction: What the subject is actively doing.
- **E**nvironment: Background elements and lighting.
- **S**tyle: Cinematic, hyper-realistic, etc.
- **T**echnical: Camera angles and motion physics.

## 2. Model Usage Matrix
| Engine | Role | Limits |
| :--- | :--- | :--- |
| **Narrative (Gemini)** | Generates JSON Storyboard | Temp: 0.7, Output Token Cap |
| **Vision (Imagen)** | Renders static anchor frames | PersonGen: ALLOW_ALL |
| **Animation (Veo)** | Synthesizes 5s video clips | 16:9 Aspect Ratio |

## 3. Token & Limit Guardrails
**Input Token Guard:** Before executing Gemini, a rough calculation estimates input tokens:
`system_tokens + user_tokens + (image_tokens * 500)`
This estimate is checked against the budget to prevent surprising $100+ API calls.

**Output Constraints:** The system hard caps the LLM at 20 scenes (`max_scenes`). Even if the LLM hallucinates 100 scenes, the system truncates the list to prevent catastrophic downstream billing.
