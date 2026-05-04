# ⚙️ 02_PIPELINE.md: Execution & Stages

## 1. Execution Flow

### Stage 1: Narrative Expansion (`StoryStage`)
- **Input**: Raw text prompt.
- **Logic**: Enforces strict Pydantic JSON parsing on the LLM to output a precise list of `Scene` objects. Truncates output if it exceeds `max_scenes` (default 8).
- **Output**: `story_manifest.json`.

### Stage 2: Vision Generation (`PreviewStage`)
- **Input**: `story_manifest.json` + User Reference Images.
- **Logic**: Iterates over each scene. Injects the reference images alongside the scene description to generate a static anchor frame. Images are cached in memory (deduplicated via `JailedPath`).
- **Output**: Writes individual `.jpg` files and records their paths in `preview_manifest.json`.

### Stage 3: Animation Rendering (`VideoStage`)
- **Input**: `preview_manifest.json`.
- **Logic**: Triggers the Veo Video Diffusion model using the generated `.jpg` as the starting frame. Dispatches all scenes in parallel asynchronously, then polls.
- **Output**: Downloads rendered `.mp4` files and updates `video_manifest.json`.

## 2. Orchestration Logic
The `PipelineOrchestrator` operates as a strict state machine with Checkpointing.
```python
# Pseudo-logic
def run():
    if not exists("story_manifest.json"):
        StoryStage.execute()
    
    if not exists("preview_manifest.json"):
        PreviewStage.execute()
    
    if not exists("video_manifest.json"):
        VideoStage.execute()
```
Idempotent behavior guarantees no double billing on crash recovery.
