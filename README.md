# Magnific

Magnific is a highly resilient, production-grade creative automation pipeline. It takes character reference images and a story idea, and orchestrates a multimodal AI pipeline to generate structured cinematic scene descriptions, high-quality preview images, and ultimately, animated video clips. 

## Key Features

- **3-Stage Orchestration**: Story generation (Gemini) → Preview Images (Imagen) → Video Animation (Veo).
- **SAEST Prompting Framework**: Enforces Hollywood-grade cinematic standards (Subject-Action-Environment-Style-Technical).
- **Security-First Architecture**: Features a `WorkspaceManager` that prevents CWE-22 path traversal vulnerabilities.
- **Crash Resilience**: Implements atomic manifest writes and an append-only `OperationTracker` to prevent ghost jobs and enable safe resumption.
- **Resource Gating**: Uses `PreFlightChecker` to enforce disk space and memory limits before wasting cloud resources.
- **Intelligent Error Handling**: Automatically differentiates between transient errors (retries with backoff) and permanent errors (fails specific scenes gracefully).

---

## Tech Stack

- **Language**: Python 3.11+
- **Configuration**: Pydantic & YAML
- **LLM Integration**: Google Vertex AI (`google-generativeai`, `google-cloud-aiplatform`)
- **Core Models**:
  - Gemini 2.5 Pro (Story Generation)
  - Imagen 4.0 Ultra (Preview Generation)
  - Veo 3.0 (Video Animation)

---

## Prerequisites

- **Python 3.11 or higher**
- A **Google Cloud Project** with Vertex AI enabled.
- A **Google Gemini API Key** with access to the required models.
- At least **1GB of free disk space** per job.

---

## Getting Started

Follow these steps to get Magnific running locally on your machine.

### 1. Clone the Repository

```bash
git clone https://github.com/mkazi/magnific-task.git
cd "magnific-task"
```

### 2. Install Dependencies

Install the package and its Google Cloud integrations in editable mode:

```bash
cd magnific
pip install -e ".[google,dev]"
```

Alternatively, using standard pip:

```bash
pip install pydantic pydantic-settings pyyaml click rich tenacity pillow httpx aiofiles python-dotenv google-generativeai google-cloud-aiplatform google-api-core
```

### 3. Environment Setup

Create an environment variables file to store your credentials:

```bash
cp .env.example .env
```
*(If `.env.example` does not exist, manually create `.env`)*

Configure the following variables in your `.env` file or export them directly in your shell:

| Variable | Description | Example |
| -------- | ----------- | ------- |
| `GOOGLE_API_KEY` | Your Google API Key for Gemini/Vertex | `AIzaSyD...` |
| `GOOGLE_CLOUD_PROJECT`| Your Google Cloud Project ID | `my-magnific-project-123` |

```bash
export GOOGLE_API_KEY="your-api-key"
export GOOGLE_CLOUD_PROJECT="your-project-id"
```

### 4. Configure Your Job

The pipeline is driven by a single canonical configuration file: `magnific/config/default.yaml`.

Edit this file to define your creative brief and reference images:

```yaml
job:
  idea: "two animal friends on an adventure through a magical forest"
  reference_images:
    - "../reference_images/animal_0.jpg"
    - "../reference_images/animal_1.jpg"
```

### 5. Run the Pipeline

Execute the main CLI command to start the orchestrator:

```bash
python3 -m magnific run --config config/default.yaml
```

To run a specific stage only (e.g., test the story generation without incurring image/video generation costs):

```bash
python3 -m magnific run --config config/default.yaml --only-stage story
```

---

## Architecture

Magnific is designed as a resilient state machine that processes data through three distinct stages.

### Directory Structure

```
Magnific Task/
├── Prompts/                 # Architectural and prompt templates research
├── reference_images/        # User-supplied character reference images
├── jobs/                    # Pipeline output directory (Job UUIDs)
└── magnific/                # Main application package
    ├── config/              # YAML configuration files (default.yaml)
    ├── docs/                # Extended documentation and audit reports
    ├── src/magnific/        # Source code
    │   ├── cli/             # Click-based CLI entry points
    │   ├── core/            # Resiliency, tracking, and security modules
    │   ├── providers/       # Google API Wrappers
    │   └── stages/          # Pipeline Stage logics (Story, Preview, Video)
    └── tests/               # Pytest suite
```

### Request Lifecycle & Data Flow

1. **CLI Invocation**: User runs `magnific run` with a config file.
2. **Orchestrator Initialization**: Creates a unique Job UUID inside the `jobs/` directory.
3. **Pre-flight Checks**: `WorkspaceManager` jails file I/O. `PreFlightChecker` asserts memory/disk availability.
4. **Stage 1 (Story)**: Prompts Gemini using the SAEST framework. Output saved to `story_manifest.json` atomically.
5. **Stage 2 (Preview)**: Concurrently runs Imagen to generate images based on `story_manifest.json`. Output saved to `preview_manifest.json`.
6. **Stage 3 (Video)**: Submits images to Veo 3.0. Logs pending operations to `pending_operations.jsonl`. Polls for completion. Output saved to `video_manifest.json`.
7. **Completion**: Updates `job_status.json` with final metrics.

---

## Environment Variables

### Required

| Variable | Description | How to Get |
| -------- | ----------- | ---------- |
| `GOOGLE_API_KEY` | Authenticats requests to Google Gemini and Vertex AI. | Google Cloud Console > APIs & Services > Credentials |
| `GOOGLE_CLOUD_PROJECT` | Defines the specific GCP project billing the API calls. | Google Cloud Console |

---

## Available Scripts

The application is bundled with a powerful CLI via the `magnific` entry point.

| Command | Description |
| ------- | ----------- |
| `python3 -m magnific run --config config/default.yaml` | Start the full pipeline end-to-end. |
| `python3 -m magnific run --config config/default.yaml --only-stage story` | Run a single stage to save costs. |
| `python3 -m magnific run --config config/default.yaml --from-stage preview --job-id <uuid>` | Resume a crashed job from a specific stage. |
| `python3 -m magnific status --job-id <uuid>` | Check the status of a specific job. |
| `pytest tests/` | Run the test suite. |
| `mypy src/magnific` | Run the static type checker. |

---

## Testing

The project uses `pytest` for unit and integration testing.

### Running Tests

```bash
cd magnific

# Run all tests
pytest tests/

# Run with verbose output
pytest -v tests/

# Run tests with coverage
pytest --cov=magnific tests/

# Run specific test file
pytest tests/test_core_security.py
```

---

## Deployment (Local Usage)

Magnific is currently designed as a local CLI tool that communicates with Cloud APIs. There is no server to deploy. However, you can run it in a containerized environment if preferred.

### Docker (Optional)

You can containerize the application for isolated execution:

```bash
# Build the image
docker build -t magnific .

# Run the container (mounting the jobs and references directories)
docker run -v $(pwd)/jobs:/app/jobs \
           -v $(pwd)/reference_images:/app/reference_images \
           -e GOOGLE_API_KEY="your-api-key" \
           -e GOOGLE_CLOUD_PROJECT="your-project-id" \
           magnific run --config config/default.yaml
```

---

## Troubleshooting

### API Quota Exceeded / Rate Limits

**Error:** `429 Too Many Requests`

**Solution:**
The pipeline's `ErrorClassifier` handles this automatically using exponential backoff. However, if the error persists across all retries, you may need to decrease concurrency in `config/default.yaml`:
```yaml
preview_concurrency:
  max_concurrent: 1
```

### Safety Filter Blocks

**Error:** `403 Forbidden - Content blocked by safety filter`

**Solution:**
This is treated as a permanent error. The specific scene will be marked as `failed` in the manifest, but the job will continue processing other scenes. Adjust your `job.idea` if your prompts repeatedly trigger safety filters.

### Ghost Jobs / Application Crash

**Error:** The pipeline was killed (e.g., via `Ctrl+C` or a power outage) while waiting for Veo videos to generate.

**Solution:**
Thanks to the `OperationTracker`, no cloud resources are leaked. Simply resume the pipeline:
```bash
python3 -m magnific run --config config/default.yaml --from-stage video --job-id <YOUR-CRASHED-JOB-ID>
```
The system will read `pending_operations.jsonl` and resume polling the existing cloud jobs instead of submitting new ones.

### Security Jail Errors

**Error:** `PathTraversalError: Attempted to access path outside workspace`

**Solution:**
Ensure that your `reference_images` in `default.yaml` are located within an allowed directory and do not attempt to use `../../` to escape the predefined allowed scopes.

---

## License

MIT License.