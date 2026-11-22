# Tasks

Goal: a working Python 3 Conary client. Background and the original scratch-port notes are in
[research/handoff-2026-11-22.md](research/handoff-2026-11-22.md).

Decisions (2026-11-22): Python 3.12+ minimum, Python 2 support dropped, build and test in a Fedora
container (Docker, source bind-mounted), work lands on the `py3` branch.

## Phase 1: Import and version

| # | Task | PRD | Status | Notes |
|---|------|-----|--------|-------|
| 1.1 | Fedora dev container: Dockerfile and helper script with Fedora python3, python3.11 (for 2to3), gcc, make, openssl/zlib/sqlite/elfutils-libelf devel headers, Cython. Source bind-mounted. Fill in the real build/test commands in config.md | - | DONE (2026-11-22) | devenv/ on fedora:45 (python3 3.15.2, python3.11 3.11.18, Cython 3.2.8). Review MINOR, Cython gate fixed |
| 1.2 | Mechanical 2to3 commit: `python3.11 -W ignore -m lib2to3 -w -n -j4 conary conary_test commands scripts` as one commit, plus the `conary/lib/magic.py` tab/space fix. Accept: `python3 -m compileall -q conary conary_test commands scripts` passes (excluding `conary/pysqlite3`) | - | DONE (2026-11-22) | 2to3 over 473 files (210 compile failures -> 0), shebangs to python3, 7 tab fixes. Review PASS. testsuite.py and embedded test recipes still Py2 |
| 1.3 | C build under Python 3: generate `conary/constants.py` from `constants.py.in` in the build, `#include <Python.h>` before `pycompat.h` in dep_freeze/digest_uncompress/pack/streams.c, regenerate Cython output with language_level 3, `PyString_*` to `PyBytes_*` in common.pxi, sha256_nonstandard.pyx, file_utils.pyx, point Make.rules at python3. Accept: `make` builds all 7 extensions in the container | - | DONE (2026-11-22) | All 7 build (make -C conary/lib/ext); py3tests/test_extensions.py 24 pass, 1 strict xfail. Includes 1.4. Review MINOR |
| 1.4 | file_utils without `PyFile_FromFile` (file_utils.pyx:101): rewrite around file descriptors / the `io` module, keeping callers' behaviour. Accept: unit test of the rewritten function | - | DONE (2026-11-22) | Done as part of 1.3 |
| 1.5 | Replace `conary/pysqlite3` with stdlib `sqlite3` in `conary/dbstore/sqlite_drv.py` (its only importer); drop pysqlite3 from the build. Check schema/migration code relying on pysqlite3 behaviour. Accept: sqlite dbstore tests pass | - | DONE (2026-11-22) | stdlib sqlite3, pysqlite3 removed; py3tests/test_sqlite_drv.py 17 pass. Review MINOR (execstmt test added by orchestrator) |
| 1.6 | Every module imports: fix import-time failures (epdb `_saferepr` -> `reprlib.repr`, others found). Accept: a test that imports every module under `conary/` | - | TODO | needs: 1.3, 1.4, 1.5 |
| 1.7 | `conary --version` works via `commands/conary`. Accept: CLI test | - | TODO | needs: 1.6 |

## Later (not yet planned)

- bytes/str at the C boundary (from 1.3): pack, dep_freeze and streams accept only bytes while the 2to3'd callers and .py fallbacks pass str (e.g. StringStream('abc'), pack.pack('!B...') raise TypeError); dep_freeze.depSetSplit returns str (strict xfail in py3tests). Expect this to surface in 1.6/1.7 and phase 2.
- C cleanups (from 1.3 review): LongLongStream_Hash leaks a PyLong; deprecated OpenSSL SHA1_* in digest_uncompress.c; stream rich compare across different types now returns NotImplemented (Py2 raised TypeError).
- sqlite (from 1.5 review): a SELECT that starts with a comment, or WITH/PRAGMA/EXPLAIN, takes BEGIN IMMEDIATE (same as the fork); PATHTYPE is TEXT so non-UTF-8 paths fail on bind; callers passing str to binary() now raise TypeError.
- conary/lib/cfg.py imports repository.transport lazily as a workaround: openpgpfile needs pycrypto (`Crypto.PublicKey.pubkey`, absent from pycryptodome). Port openpgpfile to a maintained crypto library, then decide whether to keep the lazy import.
- Follow-ups from 1.2: convert testsuite.py (repo root, still Py2); recipes embedded as strings in conary_test are Py2; rename the 8 `xxx_todo_changeme` tuple-param placeholders (e.g. conary/repository/changeset.py:979, conary/lib/ext/digest_uncompress.py:32).

- Phase 2 prerequisite: conary_test imports `testrunner` and `testutils` (sassoftware/testutils, not in this repo); fork and port them or replace the harness before triage.
- Phase 2: run `conary_test`, triage failures, bytes/str issues first.
- Then: install/query/rollback against a local repository, RPM encapsulation proof, build side (rMake replacement), distro decision.
