# Progress

## 2026-11-22 - norman initialized

- Cloned lhaig/conary (branch garnet, upstream 2.5.9, untouched) into this directory; created branch `py3`.
- Planned phase 1 (7 tasks) in TASKS.md. Handoff notes saved to research/handoff-2026-11-22.md.
- Measured: `PyFile_FromFile` has one call site (conary/lib/ext/file_utils.pyx:101);
  `conary/pysqlite3` is imported only by conary/dbstore/sqlite_drv.py.
- Host is macOS (arm64) with Docker 29.9; Conary is Linux-only, so all build/test runs in a Fedora container.

PATTERN: environment - Host Python is 3.15 with no lib2to3; use python3.11 inside the container for the 2to3 step only.

## 2026-11-22 - task 1.1 DONE: Fedora dev container

- Added devenv/Dockerfile (fedora:45), devenv/run (image tagged by Dockerfile hash, TTY only on a terminal,
  --user on Linux hosts), devenv/check.sh (toolchain check), devenv/README.md.
- check.sh failed on the bare host (no python3.11) and passes in the container. Bind-mount writes show as
  the macOS user, not root.
- Advisor review: MINOR. Fixed in orchestrator: the Cython version check could pass with a broken CLI
  (it ran only inside an OK message); now gated, plus a pyflakes check. Mutation-tested the Cython gate.
  Untested: the Linux --user path in devenv/run.

PATTERN: environment - Fedora 45's python3 is 3.15.2, newer than the 3.12 minimum; 3.12/3.13-only regressions will not show up here.
PATTERN: build - Make.rules computes PYVER as sys.version[0:3], which gives "3.1" on 3.15, and hardcodes /usr/bin/cython (Fedora ships cython/cython3). Fix in task 1.3.
PATTERN: environment - No 2to3-3.11 binary on Fedora; use `python3.11 -W ignore -m lib2to3`.
PATTERN: environment - Test tools such as cpio, rpm-build, xz, bzip2 and perl are not in the image yet; add them as conary_test needs them.
