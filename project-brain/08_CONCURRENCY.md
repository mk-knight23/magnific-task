# 🔄 08_CONCURRENCY.md: Threading & Async

## 1. Hybrid Concurrency Model
The Vertex AI Python SDK possesses both Synchronous (`generate_image`) and Asynchronous (`poll_async`) patterns. Magnific orchestrates a hybrid model to keep the event loop non-blocking.

## 2. Semaphore Limits (Imagen)
Generating 8 images concurrently often triggers HTTP 429 Rate Limits from GCP. 
- **Solution**: We use a `ThreadPoolExecutor(max_workers=4)` as a bounded semaphore. It throttles the burst of Imagen requests, ensuring we stay under quota while speeding up generation relative to sequential processing.
- The synchronous SDK calls are wrapped in `await self.run_sync_in_thread(provider.generate_image, ...)`.

## 3. Async Native Polling (Veo)
Veo video renders can take 10+ minutes.
- Blocking threads for 10 minutes causes resource starvation.
- **Solution**: Veo utilizes pure native asynchronous polling (`await asyncio.sleep(10)`). This immediately yields the thread back to the event loop, allowing thousands of simultaneous jobs to wait for cloud processing without crashing the local host.
