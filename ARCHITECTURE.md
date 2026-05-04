# Magnific Architecture

> [!TIP]
> For a deep-dive into the architectural mechanics, security audits, and memory profiling, please consult the [Project Brain](project-brain/00_INDEX.md).

## Overview

Magnific is a **resilient state machine** that transforms creative ideas into animated videos through a 3-stage pipeline. The architecture prioritizes:

1. **Security**: CWE-22 path traversal protection
2. **Resilience**: Crash recovery via atomic writes + operation tracking
3. **Extensibility**: Provider abstraction + config-driven design
4. **Observability**: Structured manifests + job status tracking

## System Diagram

```
User Input (images + idea)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          CLI Layer                                   │
│  generate-config | run [--from-stage] | status --job-id             │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Orchestrator                                   │
│  • Creates job UUID + workspace                                      │
│  • Runs pre-flight checks                                            │
│  • Determines execution plan (resume logic)                          │
│  • Coordinates stage execution                                       │
│  • Writes job_status.json                                            │
└───────────┬────────────────────┬────────────────────┬───────────────┘
            ▼                    ▼                    ▼
┌───────────────────┐  ┌───────────────────┐  ┌──────────────────────┐
│   Stage 1: Story  │  │   Stage 2:        │  │   Stage 3: Video     │
│   Generation      │─▶│   Preview Gen     │─▶│   Animation          │
│                   │  │                   │  │                      │
│  Provider: Gemini │  │  Provider: Imagen │  │  Provider: Veo       │
│  Concurrency: 1   │  │  Concurrency: N   │  │  Async polling       │
│  Output: scenes   │  │  Output: PNGs     │  │  Output: MP4s        │
└───────────────────┘  └───────────────────┘  └──────────────────────┘
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Core Layer                                      │
│                                                                      │
│  WorkspaceManager    OperationTracker    PreFlightChecker           │
│  (Path Jail)         (Ghost Job Defense) (Disk/Memory Gates)        │
│                                                                      │
│  Manifest I/O        RetryHandler       ErrorClassifier             │
│  (Atomic Writes)     (Backoff + Jitter) (Permanent vs Transient)    │
└─────────────────────────────────────────────────────────────────────┘
```

## Core Components

### WorkspaceManager (Security Jail)

Prevents **CWE-22 Path Traversal**:

```python
# All file operations jailed
workspace.resolve("subdir/file.txt")  # OK
workspace.resolve("../../etc/passwd")  # BLOCKED
```

Features:
- Double-resolve pattern to eliminate `..`
- Symlink escape detection
- External path validation (for reference images)

### OperationTracker (Ghost Job Defense)

Prevents **cloud resource leaks** after crashes:

```python
# Submit video → record ID immediately (crash-safe)
tracker.record_submission(scene_id, operation_id)

# Crash → Resume → recover pending operations
pending = tracker.get_pending_operations()
```

Format: JSONL (append-only, crash resilient)

### PreFlightChecker (Resource Gates)

Stops pipeline before wasting resources:

- Disk space check (before and during stages)
- Image validation (format, size)
- Image optimization (resize to 1024px, compress)
- Memory gates (max image size limits)

### ErrorClassifier

Critical distinction between **Transient** and **Permanent** errors:

| Error Type | Action | Retry? |
|------------|--------|--------|
| 429 Rate Limit | RETRY | Yes (backoff) |
| 503 Unavailable | RETRY | Yes |
| 400 Bad Request | FAIL_SCENE | No |
| 403 Safety Filter | FAIL_SCENE | No |
| 401 Invalid Key | ABORT_JOB | No |

**Key insight**: Safety filters are **permanent** errors. Retrying wastes API quota.

## Manifest Chain

Each stage writes an atomic manifest:

```
jobs/{job_id}/
├── job_status.json          # High-level state
├── story_manifest.json      # Stage 1: scene prompts
├── preview_manifest.json    # Stage 2: image paths
├── video_manifest.json      # Stage 3: video paths
└── pending_operations.jsonl # Veo operation tracking
```

Manifest structure:

```json
{
  "job_id": "uuid",
  "stage": "story",
  "scenes": [
    {
      "scene_id": "scene_001",
      "title": "Scene Title",
      "status": "success",
      "error": null
    }
  ]
}
```

## Concurrency Model

**Hybrid Async/Sync Pattern**:

- Google SDKs (Gemini, Imagen) are **synchronous**
- Video polling benefits from **async**
- Solution: Wrap sync SDKs in `run_in_executor`

```python
# Stage 2: Concurrent preview generation
semaphore = asyncio.Semaphore(max_concurrent)

for scene in scenes:
    async with semaphore:
        # Run blocking SDK in thread
        await run_sync_in_thread(imagen.generate, ...)
```

```python
# Stage 3: Concurrent video polling
tasks = [poll_video(op_id) for op_id in operation_ids]
results = await asyncio.gather(*tasks)

# Wall time ≈ slowest video (not sum)
```

## Resume Logic

Execution plan determination:

```python
def get_execution_plan(from_stage, only_stage):
    if only_stage:
        return [only_stage]
    
    if from_stage:
        return STAGE_ORDER[from_stage_index:]
    
    # Auto-detect: find last complete manifest
    for stage in STAGE_ORDER:
        if not manifest_exists(stage):
            return STAGE_ORDER[stage_index:]
    
    return []  # All complete
```

## Failure Matrix

| Scenario | Classification | Response |
|----------|----------------|----------|
| Path traversal | Security | Halt immediately |
| Disk full | System | Pre-flight block OR mark scene failed |
| Rate limit (429) | Transient | Backoff + retry |
| Safety filter | Permanent | Mark scene failed, continue |
| Invalid JSON from Gemini | Transient | Retry once with stricter prompt |
| Crash mid-poll | System | Resume from pending_operations.jsonl |
| Memory spike | Memory | Image cache + clear before Stage 3 |

## Configuration Strategy

**External vs Code**:

| External (YAML) | Code |
|------------------|------|
| Model names | Retry implementation |
| Prompts | Error classification |
| Concurrency caps | Provider interfaces |
| Paths | Validation logic |
| Retry policies | Manifest schemas |

**Hierarchy**:

1. CLI overrides (`--set key=value`)
2. Job config (`workflow.yaml`)
3. User defaults (`~/.magnific/config.yaml`)
4. System defaults (`config/default.yaml`)

## Extensibility

### Adding a Stage

1. Create stage class inheriting from `BaseStage`
2. Register in `STAGE_REGISTRY`
3. Add config section
4. Update `STAGE_ORDER`

### Swapping Providers

```python
# Abstract interface
class StoryProvider(ABC):
    def generate_scenes(...) -> StoryResult

# Implementations
class GoogleGeminiProvider(StoryProvider)
class OpenAIStoryProvider(StoryProvider)

# Factory
def get_story_provider(provider: str) -> StoryProvider
```

## Design Decisions

| Decision | Reasoning |
|----------|-----------|
| Async throughout | Video polling needs it; SDKs wrapped in threads |
| JSONL for tracking | Append-only is crash-safe |
| Atomic manifest writes | Prevent corruption on power loss |
| Pydantic validation | Strict config, clear error messages |
| Semaphore concurrency | Natural rate limiting without external libs |
| Fail-scene not fail-job | Partial results better than total failure |

## Trade-offs

- **Over-engineering**: Operation tracking adds complexity but enables crash recovery
- **Sync SDKs**: Google SDKs blocking; thread executor adds overhead but simpler than async wrappers
- **Local state**: Won't scale to distributed; acceptable for single-machine evaluation
- **Mock providers**: Real API calls would cost money in tests

## Limitations

- Single-machine only (no distributed execution)
- No content-addressable caching (re-run regenerates)
- Fixed polling intervals (not adaptive)
- No web UI (CLI only)