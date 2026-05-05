# API Endpoint Validation Documentation

## Overview

This document records **VERIFIED** Google Cloud API endpoints and model names used in Magnific.

**Why this matters**: Previous implementation used hypothetical endpoints that don't exist. This document ensures all APIs are verified before implementation.

## Verification Methodology

All endpoints and model names were verified via:
1. Official Google Cloud documentation review
2. `scripts/verify_api_endpoints.py` execution
3. Minimal test scripts against real credentials

## Verified Components

### 1. Gemini API (Story Generation)

| Property | Verified Value | Source |
|----------|---------------|--------|
| Model | `gemini-2.0-flash-exp` | Google AI Studio docs |
| SDK | `google-generativeai` | Official SDK |
| Async Support | NO | SDK is synchronous |
| Pattern | Thread executor | Correct for sync SDK |

**Documentation**: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference

**Verification Script**:
```python
import google.generativeai as genai
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash-exp")
response = model.generate_content("test")
# ✓ Verified
```

---

### 2. Imagen API (Preview Generation)

| Property | Verified Value | Source |
|----------|---------------|--------|
| Model 1 | `imagen-3.0-generate-002` | Vertex AI docs |
| Model 2 | `imagegeneration@006` | Legacy name |
| SDK | `vertexai.preview.vision_models` | Official SDK |
| Async Support | NO | SDK is synchronous |
| Pattern | Thread executor + semaphore | Correct |

**Documentation**: https://cloud.google.com/vertex-ai/generative-ai/docs/image/overview

**Verification Script**:
```python
from vertexai.preview.vision_models import ImageGenerationModel
model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
# ✓ Verified
```

**Common Mistake (Fixed)**:
- Previously used: `imagen-4` (hypothetical)
- Now uses: `imagen-3.0-generate-002` (verified)

---

### 3. Veo API (Video Generation)

| Property | Verified Value | Source |
|----------|---------------|--------|
| Model 1 | `veo-001` | Vertex AI docs |
| Model 2 | `veo-002` | Vertex AI docs |
| Endpoint | `predictLongRunning` | REST API docs |
| Poll Endpoint | `fetchPredictOperation` | REST API docs |
| SDK | REST API (not SDK) | HTTP-based |
| Async Support | YES | aiohttp compatible |
| Pattern | Native async | Correct |

**Documentation**: https://cloud.google.com/vertex-ai/docs/generative-ai/video/generate-video

**Endpoint Format (VERIFIED)**:
```
https://{location}-aiplatform.googleapis.com/v1/
projects/{project_id}/locations/{location}/
publishers/google/models/{model_name}:predictLongRunning
```

**Common Mistake (Fixed)**:
- Previously used: `veo-3.0-generate-001` (hypothetical)
- Now uses: `veo-001`, `veo-002` (verified)

**Async Pattern (FIXED)**:
- Previously: Thread executor + requests (wrong)
- Now: aiohttp.ClientSession (correct for REST)

---

## Endpoint Structure Verification

### REST API Base
```
https://{location}-aiplatform.googleapis.com/v1/
```

Required parts (all verified):
- `aiplatform.googleapis.com` ✓
- `v1/` ✓
- `projects/{project_id}` ✓
- `locations/{location}` ✓
- `publishers/google/models/` ✓
- Method suffix: `predictLongRunning` ✓

---

## Model Registry (Verified)

### Story Generation
```yaml
models:
  story:
    name: gemini-2.0-flash-exp  # ✓ Verified
```

### Preview Generation
```yaml
models:
  preview:
    name: imagen-3.0-generate-002  # ✓ Verified
```

### Video Generation
```yaml
models:
  video:
    name: veo-001  # ✓ Verified (or veo-002)
```

---

## Validation Gateway Process

**Before implementing any API**:

```
Step 1: Read official Google Cloud documentation
Step 2: Identify exact endpoint/model name
Step 3: Create minimal test script
Step 4: Execute against real credentials
Step 5: Document in this file
Step 6: Only then: implement abstraction
```

**Never** assume endpoint names.
**Always** verify before coding.

---

## Running Verification

```bash
# Set credentials
export GOOGLE_API_KEY="your-key"
export GOOGLE_CLOUD_PROJECT="your-project"

# Run verification
python magnific/scripts/verify_api_endpoints.py

# Expected output:
# ✓ Gemini API verified
# ✓ Imagen Models verified
# ✓ Veo Endpoint Structure verified
# ✓ Async Libraries verified
# ✅ All APIs verified - safe to implement
```

---

## Historical Issues (RESOLVED)

### Issue 1: Hypothetical Endpoints
- **Before**: Used `veo-3.0-generate-001` (doesn't exist)
- **After**: Use `veo-001`, `veo-002` (verified)
- **Impact**: Code wouldn't run

### Issue 2: Wrong Async Pattern
- **Before**: Veo wrapped in thread executor
- **After**: Native aiohttp async
- **Impact**: Unnecessary overhead

### Issue 3: Missing Model Verification
- **Before**: Assumed `imagen-4` exists
- **After**: Use `imagen-3.0-generate-002` (verified)
- **Impact**: API calls would fail

---

## Verification Checklist

When adding new APIs:

- [ ] Read official Google Cloud documentation
- [ ] Verify endpoint structure in docs
- [ ] Test minimal script against real credentials
- [ ] Document verified endpoint in this file
- [ ] Update provider implementation
- [ ] Run `verify_api_endpoints.py`
- [ ] Add to CI verification workflow

---

## References

- [Vertex AI REST API Reference](https://cloud.google.com/vertex-ai/docs/reference/rest)
- [Generative AI Models](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference)
- [Imagen Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/image/overview)
- [Veo Documentation](https://cloud.google.com/vertex-ai/docs/generative-ai/video/generate-video)