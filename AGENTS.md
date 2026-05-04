# Agent Instructions

## Package Manager
Use **pip**: `pip install -e .`

## Commit Attribution
AI commits MUST include:
```
Co-Authored-By: Claude Sonnet 4 <noreply@example.com>
```

## File-Scoped Commands
| Task | Command |
|------|---------|
| Test | `pytest path/to/test.py` |
| Run  | `python -m magnific.cli` |

## Key Conventions
- **Source of Truth**: Read `project-brain/00_INDEX.md` and subsequent brain files before writing or modifying architecture.
- **Security Constraint**: NEVER bypass `WorkspaceManager`. All file I/O operations must be strictly typed and routed through `JailedPath`.
- **Resilience**: State is managed via atomic JSON manifest writes. Never hold long-running job state purely in memory.
