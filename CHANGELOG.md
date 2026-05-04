# Magnific Changelog

All notable design decisions and changes to Magnific.

## [1.0.0] - 2026-05-04

### Added

- **Security-First Architecture**
  - `WorkspaceManager` implements path traversal protection (CWE-22)
  - Symlink escape detection
  - External path validation for reference images
  - Decision: Security must be enforced at the lowest level, not sprinkled throughout

- **Crash Resilience System**
  - `OperationTracker` for ghost job defense
  - Atomic manifest writes using `os.replace()`
  - JSONL append-only format for operation tracking
  - Decision: Append-only is crash-safe; atomic rename prevents corruption

- **Pre-flight Validation**
  - Disk space gates (before start + before each stage)
  - Image optimization (resize to 1024px, compress to JPEG)
  - Memory spike prevention (image byte cache)
  - Decision: Check resources BEFORE spending API quota

- **Error Classification Matrix**
  - Transient vs Permanent error distinction
  - Safety filters marked as PERMANENT (no retry)
  - `ErrorClassifier` translates Google exceptions to actions
  - Decision: Retrying safety filters wastes quota; they're permanent failures

- **Hybrid Concurrency Model**
  - Sync Google SDKs wrapped in `run_in_executor`
  - Async for video polling (`asyncio.gather`)
  - Semaphore-based rate limiting
  - Decision: Kimi's hybrid approach is pragmatic; full async would require async SDK wrappers

- **Provider Abstraction**
  - `StoryProvider`, `ImageProvider`, `VideoProvider` interfaces
  - Mock providers for testing
  - Provider registry for dynamic selection
  - Decision: Mock-first design enables testing without API keys

- **Configuration System**
  - Pydantic models for strict validation
  - Config hierarchy (CLI > job > user > system)
  - Environment variable for API key (never in config)
  - Decision: Secrets NEVER in config files (committed to git)

- **Manifest Chain**
  - `StoryManifest`, `PreviewManifest`, `VideoManifest`
  - Per-scene status tracking
  - Parent manifest linking
  - Decision: Each stage is inspectable and resumable independently

- **CLI Commands**
  - `generate-config`: Create workflow from idea
  - `run`: Execute pipeline with resume support
  - `status`: Inspect job state
  - Decision: Click for mature subcommand support

### Design Philosophy

**Why these decisions were made:**

1. **Path Jail**: Without security at the foundation, any config file injection could overwrite system files. Security is not optional.

2. **Operation Tracking**: If Veo jobs cost $0.10 each, a crash during 10-scene polling = $1.00 ghost charges. The `.jsonl` tracker prevents this.

3. **Error Classification**: Spending API quota retrying safety filter blocks is wasteful. The distinction between transient and permanent errors saves real money.

4. **Atomic Writes**: A power pull mid-write produces corrupt JSON. The temp→rename pattern guarantees atomicity.

5. **Pre-flight Checks**: A disk-full crash during video download loses all prior work. Checking disk before each stage prevents this.

6. **Hybrid Async**: Google's Python SDKs are blocking. Pretending they're async would require complex wrappers. Thread executor is simpler.

### Trade-offs Acknowledged

- **Local filesystem**: Won't scale to distributed execution. For a single-machine evaluation, this is correct; for production multi-node, we'd add Redis/PostgreSQL.

- **No content caching**: Re-running with same inputs regenerates everything. Could add content-hash cache, but adds complexity for v1.

- **Fixed polling intervals**: Not adaptive to actual generation speed. Simple enough for now.

- **Mock providers in tests**: Real API calls would cost money. Mock-first is pragmatic.

### What We'd Improve With More Time

1. Add SQLite state store for job querying across sessions
2. Implement content-addressable cache to skip identical regeneration
3. Add structured JSON logging with correlation IDs
4. Add web dashboard for job monitoring
5. Adaptive polling intervals based on generation speed
6. Multi-provider support (OpenAI story, Stability images)
7. Pre-flight API key validation (test call before full pipeline)

### Security Considerations

- **CWE-22**: Path traversal blocked via double-resolve + relative_to check
- **CWE-200**: API keys in environment variables only
- **CWE-400**: Image size limits prevent memory exhaustion
- **CWE-770**: Disk space gates prevent resource exhaustion

### Influences

Architecture synthesized from:
- GLM: Error classification matrix, manifest design, provider registry
- Kimi: Hybrid sync/async model, pragmatic SDK handling
- DeepSeek: Self-critique process, retry policy design
- Qwen: Config structure, JSON schema validation

### Testing Strategy

- Unit tests: All modules with mocked providers
- Integration tests: Full pipeline orchestration
- Failure simulation: Safety filters, rate limits, crashes
- No API keys required: All tests use mock providers