# ⏱️ 04_RUNTIME.md: State & Ghost Job Defense

## 1. Manifest Design (Atomic Writes)
State is stored in `_manifest.json` files per stage.
- **Atomic Writes**: Manifests are written to a `.tmp` file, and then `os.replace()` is called. POSIX guarantees this rename is atomic, preventing partial JSON corruption if the power fails.

## 2. Ghost Job Defense
If the pipeline crashes during a 10-minute Veo render, the Cloud UI is still spinning.
- **Prevention**: `OperationTracker` uses an append-only `.jsonl` file. The instant a Veo job is submitted, its `operation_id` is written to disk *before* polling begins.
- **Recovery**: Upon reboot, Magnific parses `pending_operations.jsonl`. Instead of submitting a redundant request (Ghost Job), it *re-attaches* to the existing cloud operation.

## 3. Retry Matrix
Uses `tenacity` for exponential backoff:
- **Transient**: HTTP 429 / 503. Handled via exponential backoff with jitter (max 60s wait).
- **Permanent**: HTTP 400 / 403 (Safety Filter). Aborts immediately. Scene is marked `BLOCKED`.

## 4. PIL Compatibility
`PIL.Image.open()` requires `str()` conversion when passed custom `os.PathLike` objects like our `JailedPath`. The preflight phase handles this explicitly.
