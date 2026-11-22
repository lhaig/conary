# Tasks

Goal: a working Python 3 Conary client. Background and the original scratch-port notes are in
[research/handoff-2026-11-22.md](research/handoff-2026-11-22.md).

Decisions (2026-11-22): Python 3.12+ minimum, Python 2 support dropped, build and test in a Fedora
container (Docker, source bind-mounted), work lands on the `py3` branch.

## Phase 1: Import and version

| # | Task | PRD | Status | Notes |
|---|------|-----|--------|-------|
| 1.1 | Fedora dev container: Dockerfile and helper script with Fedora python3, python3.11 (for 2to3), gcc, make, openssl/zlib/sqlite/elfutils-libelf devel headers, Cython. Source bind-mounted. Fill in the real build/test commands in config.md | - | TODO | First: everything else builds in it |
| 1.2 | Mechanical 2to3 commit: `python3.11 -W ignore -m lib2to3 -w -n -j4 conary conary_test commands scripts` as one commit, plus the `conary/lib/magic.py` tab/space fix. Accept: `python3 -m compileall -q conary conary_test commands scripts` passes (excluding `conary/pysqlite3`) | - | TODO | needs: 1.1 |
| 1.3 | C build under Python 3: generate `conary/constants.py` from `constants.py.in` in the build, `#include <Python.h>` before `pycompat.h` in dep_freeze/digest_uncompress/pack/streams.c, regenerate Cython output with language_level 3, `PyString_*` to `PyBytes_*` in common.pxi, sha256_nonstandard.pyx, file_utils.pyx, point Make.rules at python3. Accept: `make` builds all 7 extensions in the container | - | TODO | needs: 1.1, 1.2 |
| 1.4 | file_utils without `PyFile_FromFile` (file_utils.pyx:101): rewrite around file descriptors / the `io` module, keeping callers' behaviour. Accept: unit test of the rewritten function | - | TODO | needs: 1.3 |
| 1.5 | Replace `conary/pysqlite3` with stdlib `sqlite3` in `conary/dbstore/sqlite_drv.py` (its only importer); drop pysqlite3 from the build. Check schema/migration code relying on pysqlite3 behaviour. Accept: sqlite dbstore tests pass | - | TODO | needs: 1.2 |
| 1.6 | Every module imports: fix import-time failures (epdb `_saferepr` -> `reprlib.repr`, others found). Accept: a test that imports every module under `conary/` | - | TODO | needs: 1.3, 1.4, 1.5 |
| 1.7 | `conary --version` works via `commands/conary`. Accept: CLI test | - | TODO | needs: 1.6 |

## Later (not yet planned)

- Phase 2: run `conary_test`, triage failures, bytes/str issues first.
- Then: install/query/rollback against a local repository, RPM encapsulation proof, build side (rMake replacement), distro decision.
