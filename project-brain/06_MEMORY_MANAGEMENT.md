# 🧠 06_MEMORY_MANAGEMENT.md: JailedPath Cache Bugs

## 1. The Pre-Production Bug
During the Phase 2 Failure Simulation audit, a critical memory leak was discovered in the Imagen generation stage. 

**Root Cause:**
The memory deduplication cache was keyed using `JailedPath` instances:
`self._byte_cache: dict[JailedPath, bytes] = {}`

Because `JailedPath` did not implement custom `__hash__` and `__eq__` methods, Python relied on object identity. Consequently, two identical paths resolved to different object hashes (`hash(jp1) != hash(jp2)`). Every concurrent task fetching the same image bypassed the cache, loading identical 5MB bytes from disk.

**Result:** A 10-scene concurrent generation spiked memory by 50MB instead of deduplicating to 5MB.

## 2. The Remediation
Implemented underlying path hashing:

```python
def __hash__(self) -> int:
    return hash(self._internal_path)

def __eq__(self, other: object) -> bool:
    if isinstance(other, JailedPath):
        return self._internal_path == other._internal_path
    return False
```

## 3. Current State
Memory scales completely flat regarding anchor frames. The memory reduction under maximum concurrent load is 90%.
