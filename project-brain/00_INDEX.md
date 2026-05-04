# 🧠 Project Brain: Magnific AI Pipeline

## 1. System Overview
**Magnific** is an enterprise-grade AI pipeline orchestrator that autonomously generates cinematic video narratives from a single textual idea and reference images. It acts as an abstraction layer above Google Cloud Vertex AI, handling model chaining, cost control, state management, and isolation.

## 2. Navigation Guide
This "Project Brain" contains the complete context of the application architecture, including hard-won lessons from production audits, security hardening, and memory profiling.

| File | Contains |
| :--- | :--- |
| **`01_SYSTEM.md`** | Core Architecture, State-Machine design |
| **`02_PIPELINE.md`** | Stage-by-Stage Logic, Polymorphic BaseStage |
| **`03_AI_SYSTEM.md`** | Prompts, Models, Token Estimation Guardrails |
| **`04_RUNTIME.md`** | Manifests, Ghost Job Defense, Checkpointing |
| **`05_FILESYSTEM_JAIL.md`** | CWE-22 mitigations, `WorkspaceManager`, `JailedPath` |
| **`06_MEMORY_MANAGEMENT.md`** | Cache deduplication, Hash/Equality implementation |
| **`07_COST_CONTROL.md`** | Budget enforcement, `CostTracker`, `max_scenes` limits |
| **`08_CONCURRENCY.md`** | Hybrid async/sync model, `asyncio.Lock` safety |
| **`09_QA_AND_SCALING.md`** | QA Metrics, Production Readiness scoring, Scaling Risks |

## 3. How to Read This Brain
- **AI Agents**: Read `00_INDEX.md` through `09_QA_AND_SCALING.md` sequentially to build a complete mental model of the codebase before writing patches.
- **Human Devs**: Treat this as the definitive architectural blueprint. Code must align with the constraints listed across these documents.
