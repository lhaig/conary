# Progress

## 2026-11-22 - norman initialized

- Cloned lhaig/conary (branch garnet, upstream 2.5.9, untouched) into this directory; created branch `py3`.
- Planned phase 1 (7 tasks) in TASKS.md. Handoff notes saved to research/handoff-2026-11-22.md.
- Measured: `PyFile_FromFile` has one call site (conary/lib/ext/file_utils.pyx:101);
  `conary/pysqlite3` is imported only by conary/dbstore/sqlite_drv.py.
- Host is macOS (arm64) with Docker 29.9; Conary is Linux-only, so all build/test runs in a Fedora container.

PATTERN: environment - Host Python is 3.15 with no lib2to3; use python3.11 inside the container for the 2to3 step only.
