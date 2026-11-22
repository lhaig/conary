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

## 2026-11-22 - task 1.2 DONE: mechanical 2to3

- Commit "refactor: convert Python sources to Python 3 with 2to3": 364 files. Default fixers, no -x.
  Covered the 43 extensionless scripts and conary/constants.py.in by passing explicit paths.
- devenv/compile_check.sh (host-side wrapper around devenv/run) compiles 473 sources in memory:
  210 failures before, 0 after. Orchestrator re-ran it and mutation-tested it with a Py2 print file.
- Advisor review: PASS. Left: testsuite.py (root) still Py2, recipes embedded as strings in conary_test
  are Py2, 8 `xxx_todo_changeme` tuple-param placeholders from fix_tuple_params.

PATTERN: tooling - Never run 2to3 twice over the tree: it double-wraps list(list(...)) and print((...)).
PATTERN: tooling - devenv/compile_check.sh is the compile gate; it covers extensionless scripts, which compileall skips.
PATTERN: environment - The scratchpad is not mounted in the container; only the repo is at /src.
PATTERN: bytes/str - fix_unicode/fix_basestring turned unicode/basestring into str (conary/versions.py, conary/deps/deps.py, conary/trovetup.py, conary/dbstore/base_drv.py, conary/lib/logger.py): callers passing bytes now fail isinstance(x, str). The Py2 originals are in the commit before the 2to3 commit.
PATTERN: bytes/str - StringIO/cStringIO became io.StringIO in 29 lines; wherever changesets or file contents pass through, it must be io.BytesIO.
PATTERN: bytes/str - fix_types turned types.StringType into bytes in isinstance checks (e.g. conary_test/cvctest/buildtest/cookrpmcapsuletest.py).
PATTERN: iterator - fix_next renamed `def next` to `__next__` and rewrote x.next() as next(x); check classes with a non-iterator next() and C extension objects.
PATTERN: runtime-only - string module functions (string.join, string.letters), buffer(), os.getcwdu are not fixed by default fixers and fail only at runtime.
