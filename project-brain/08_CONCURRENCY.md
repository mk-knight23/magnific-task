# 🔄 08_CONCURRENCY.md: Threading & Async (VERIFIED)

## 1. Hybrid Concurrency Model (UPDATED)

The concurrency model has been **VERIFIED** against actual SDK capabilities:

| Component | SDK | Async Native | Implementation | Verified |
|-----------|-----|--------------|----------------|----------|
| **Gemini** | vertexai.generative_models | NO | ThreadPoolExecutor ✓ | ✅ Correct |
| **Imagen** | vertexai.preview.vision_models | NO | ThreadPoolExecutor ✓ | ✅ Correct |
| **Veo** | REST API | YES | aiohttp.ClientSession ✓ | ✅ Correct (FIXED) |
| **Polling** | asyncio.sleep | YES | Direct async ✓ | ✅ Correct |

**Key Change**: Veo now uses **native aiohttp async** instead of thread executor.

## 2. Thread Executor Pattern (VERIFIED - Correct for Some SDKs)

**Only use ThreadPoolExecutor for TRULY blocking SDKs:**

### Gemini & Imagen (SDKs are synchronous)

The `vertexai` SDK provides NO native async methods:
- `GenerativeModel.generate_content()` - blocking
- `ImageGenerationModel.generate_images()` - blocking

**Solution**: Thread executor is CORRECT for these.

```python
# Stage 1: Story Generation (Gemini)
await self.run_sync_in_thread(
    provider.generate_scenes,
    reference_images,
    brief,
    config,
)

# Stage 2: Preview Generation (Imagen)
await self.run_sync_in_thread(
    provider.generate_image,
    prompt,
    reference_images,
    output_path,
    config,
)
```

### Why Thread Executor Here?

Vertex AI SDKs are **blocking synchronous**:
- No `async generate_content()` method exists
- Thread executor prevents blocking event loop
- This is the **correct pattern** for these SDKs

## 3. Native Async Pattern (VERIFIED - Correct for REST APIs)

### Veo (REST API - NOW NATIVE ASYNC)

**Previously**: Wrapped in thread executor (wrong)
**Now**: Native aiohttp async (correct)

```python
# Stage 3: Video Generation (Veo) - NATIVE ASYNC
provider = GoogleVeoProvider()

# Submit - no thread executor
result = await provider.submit_async(
    preview_image,
    prompt,
    config,
)

# Poll - no thread executor
result = await provider.poll_async(
    operation_id,
    output_path,
    poll_interval=10.0,
)
```

### Why Native Async for Veo?

Veo uses REST API (not SDK):
- REST calls can use `aiohttp.ClientSession`
- `asyncio.sleep()` for polling wait
- **NO thread overhead needed**

**Performance Impact**:
- Before: Thread executor for every REST call = overhead
- After: Native async = zero overhead, scales to thousands of concurrent polls

## 4. Semaphore Limits (Imagen - Rate Limiting)

Generating 8 images concurrently triggers HTTP 429 from GCP.

**Solution**: Semaphore throttles burst requests.

```python
# Stage 2: Preview Generation
semaphore = asyncio.Semaphore(max_concurrent)

tasks = [
    generate_preview_with_semaphore(scene, semaphore)
    for scene in scenes
]

results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Note**: Semaphore works with thread executor:
- Thread executor runs blocking SDK call
- Semaphore limits concurrent threads
- Together: rate limiting + non-blocking

## 5. Async Native Polling (Veo - No Blocking)

Veo video renders can take 10+ minutes.

**Pattern**: Pure async polling (no thread blocking).

```python
async def poll_video(operation_id, output_path):
    deadline = time.time() + max_poll_minutes * 60
    interval = 10.0
    
    while time.time() < deadline:
        # Check status - async HTTP
        result = await provider.poll_async(operation_id, output_path)
        
        if result.status == "complete":
            return result
        
        if result.status == "failed":
            return result
        
        # Async wait - yields to event loop
        await asyncio.sleep(interval)
        interval = min(interval * 1.5, 60.0)
    
    return VideoPollResult(success=False, status="timeout")
```

**Why this works**:
- `await asyncio.sleep(10)` immediately yields thread
- Thousands of jobs can wait simultaneously
- NO thread starvation
- NO blocking

## 6. Verified Concurrency Matrix

| Stage | Provider | SDK Type | Async Pattern | Threads | Verified |
|-------|----------|----------|---------------|---------|----------|
| Story | Gemini | Sync SDK | Thread executor | 1 | ✅ |
| Preview | Imagen | Sync SDK | Thread executor + Semaphore | N (max_concurrent) | ✅ |
| Video | Veo | REST API | Native aiohttp async | 0 | ✅ |
| Workflow Gen | Gemini | Sync SDK | Thread executor | 1 | ✅ |

## 7. Common Mistake (FIXED)

**Before (Wrong)**:
```python
# Veo wrapped in thread executor - unnecessary overhead
await self.run_sync_in_thread(
    requests.post,  # Sync library
    veo_url,
    headers=headers,
    json=request_body,
)
```

**After (Correct)**:
```python
# Veo with native async - zero overhead
session = await aiohttp.ClientSession()
async with session.post(veo_url, headers=headers, json=request_body) as response:
    result = await response.json()
```

## 8. Rule of Thumb

```
SDK/Library           | Async Pattern
----------------------|---------------
Blocking SDK (vertexai) | Thread executor ✓
REST API               | aiohttp native async ✓
Python asyncio.sleep   | Direct async ✓
```

**Never** use thread executor for APIs that support native async.
**Always** use thread executor for blocking SDKs without async methods.

## 9. Verification Script

Run before implementation:
```bash
python scripts/verify_api_endpoints.py
```

This verifies:
- Gemini API accessible
- Imagen models exist
- Veo endpoint structure correct
- Async libraries available