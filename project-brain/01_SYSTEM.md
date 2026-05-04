# 🏗️ 01_SYSTEM.md: Core Architecture

## 1. Architecture Paradigm
Magnific uses a **State-Machine Driven Micro-Orchestration** pattern.
- The system is completely stateless in memory.
- All state is synchronized to disk via atomic JSON manifest writes.
- Operations are isolated into strict directories (Job UUIDs).

## 2. Core Components
- **`PipelineOrchestrator`**: The central loop controller. Manages state transitions, cost tracking, and graceful shutdown.
- **`WorkspaceManager`**: The security layer. Creates, validates, and locks down filesystem access per job via `JailedPath`.
- **`OperationTracker`**: The recovery layer. Logs Cloud API operations to an append-only JSONL to prevent orphaned infrastructure.
- **`CostTracker`**: The budget layer. Accumulates USD spend and raises `BudgetExceededError` to abort early.
- **`BaseStage`**: Abstract class enforcing a polymorphic `execute(input_context)` signature for all ML interactions.

## 3. Key Design Decisions
- **Disk over Memory**: By reading/writing manifests at every stage, the pipeline can be killed and restarted at the exact point of failure.
- **Providers as Pure API Wrappers**: Prompt enhancement (SAEST logic) is handled at the `Stage` layer, leaving the `Provider` layer strictly responsible for HTTP requests.
- **Fail Fast & Gracefully**: Signal handlers catch SIGINT/SIGTERM. If safety filters trigger (HTTP 403), the scene fails permanently without wasteful retries.
