# 🛡️ 05_FILESYSTEM_JAIL.md: CWE-22 Security

## 1. The Vulnerability (CWE-22)
Without protection, maliciously crafted input paths could escape the temporary job directory and read/write arbitrary system files (Path Traversal).

## 2. WorkspaceManager & JailedPath
The system enforces a Zero-Trust File I/O architecture.

### JailedPath Sealed Type
- `JailedPath` cannot be instantiated directly. It requires a private `_WorkspaceToken`.
- Only `WorkspaceManager` can create `JailedPath` instances.
- All Provider interfaces are strictly type-hinted to accept `JailedPath` instead of standard `Path` strings.

### Resolution Logic
```python
def resolve(self, path: str) -> JailedPath:
    # 1. Resolve to absolute path
    # 2. Check relative_to(root)
    # 3. If it escapes root, raise SecurityError
```

### OS Compatibility
`JailedPath` explicitly implements Python's `os.PathLike` interface (`__fspath__`), allowing it to integrate cleanly with standard library tools while maintaining its security boundary.
