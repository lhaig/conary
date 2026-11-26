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

## 2026-11-22 - task 1.3 DONE (includes 1.4): C extensions on Python 3

- Commit "feat(ext): build the C and Cython extensions against Python 3". Make.rules via sysconfig, PY_SSIZE_T_CLEAN,
  tp_richcompare for streams, fopenIfExists via open(), str paths via os.fsencode, Cython .c regenerated.
- py3tests/test_extensions.py: 24 failed before, 24 pass + 1 strict xfail after. Orchestrator re-ran a clean build
  (8 .so incl. helper), pytest and compile_check (474 files, 0 failures).
- Advisor review: MINOR (behaviour change on cross-type stream compare, pre-existing LongLongStream_Hash leak,
  OpenSSL SHA1 deprecations); logged under Later in TASKS.md.

PATTERN: build - Build extensions with `devenv/run make -C conary/lib/ext` (never the whole tree while pysqlite3 is in SUBDIRS). Regenerate Cython .c with `make -C conary/lib/ext ext`. constants.py: `make -C conary constants.py`.
PATTERN: c-api - Every hand-written .c needs PY_SSIZE_T_CLEAN before <Python.h> with Py_ssize_t lengths for s#/z#, or 3.10+ raises SystemError at runtime.
PATTERN: bytes/str - C extensions (pack, dep_freeze, streams) accept only bytes; 2to3'd callers and the .py fallbacks use str. `s#`/`z#` accept str silently and hide this.
PATTERN: imports - Plain .so names work: Python 3 lists .so in EXTENSION_SUFFIXES and FileFinder prefers extensions over the .py fallback in the same directory.
PATTERN: tooling - devenv/run passes -i; redirect stdin (</dev/null) when scripting it, or a stdin-reading command hangs.

## 2026-11-22 - task 1.5 DONE: stdlib sqlite3

- Commit "feat(dbstore): replace bundled pysqlite3 with stdlib sqlite3". py3tests/test_sqlite_drv.py: all 16 failed
  before (InvalidBackend), 16 pass after; orchestrator added a compile()/execstmt() test (17) and mutation-tested it.
  Full py3tests: 41 passed, 1 xfailed. compile_check 474 files, 0 failures.
- Import fixes outside dbstore (needed to import conary.dbstore): epdb _saferepr via reprlib; StreamCollection
  __slots__ '_items' clash; cfgtypes sre_constants -> re; cfg lazy-imports repository.transport (pycrypto missing).
- Advisor review: MINOR. Edits to scripts/, conary_test/ and testsuite.py are compile-checked only.

PATTERN: sqlite - isolation_level=None plus BEGIN IMMEDIATE emulation in Cursor keeps transactional DDL; use dbh.in_transaction, sqlite3.sqlite_version_info (attribute), and timeouts in seconds (dbstore API stays in ms).
PATTERN: bytes/str - sqlite binary() rejects str and frombinary() returns bytes; str binds as TEXT. Callers passing str to binary() fail loudly.
PATTERN: py3-port - 2to3 misses implicit relative imports via __import__ and removed modules (sre_constants); expect more in 1.6.
PATTERN: environment - No `Crypto` (pycrypto) in the container; conary.repository, changeset, rpmhelper and openpgpfile cannot import until openpgpfile is ported (Crypto.PublicKey.pubkey is gone in pycryptodome).
PATTERN: testing - `pytest -W error` fails at collection on existing invalid-escape SyntaxWarnings; use -W error::ResourceWarning for leak checks.

## 2026-11-23 - task 1.6 DONE: OpenPGP on pycryptodomex

- Decision (user, 2026-11-23): pycryptodomex, not cryptography. Task renumbering: crypto port is 1.6, imports 1.7, --version 1.8.
- Commit "feat(openpgp): port OpenPGP code from pycrypto to pycryptodomex". py3tests/test_openpgp.py: 65 tests
  (collection failed before: no module Crypto). Full py3tests 106 passed, 1 xfailed; compile_check 0 failures; check.sh passes.
- Advisor review: MINOR. Orchestrator narrowed a pytest.raises(Exception) negative test; it was hiding an AttributeError
  when an RSA signature was checked against a DSA key. Added a key-type guard in verifySignature, mutation-tested.

PATTERN: testing - Never use pytest.raises(Exception) for negative checks in the port; it hides TypeError/AttributeError from porting bugs (it hid one in 1.6).
PATTERN: generators - 2to3's next(x) inside a generator turns StopIteration into RuntimeError (PEP 479); use a None-returning helper.
PATTERN: crypto - pycryptodomex has no raw RSA/DSA; use pow() on ints and skip RSA/DSA.construct. Any len(hex(n)) arithmetic relied on Python 2's L suffix.
PATTERN: bytes/str - io.BytesIO.truncate(n) does not move the position (Py2 StringIO did); util.ExtendedStringIO restores the old behaviour.
PATTERN: testing - Legacy test constants in conary_test can be read with ast.literal_eval without importing testrunner; Py2 str literals -> .encode('latin-1').

## 2026-11-23 - task 1.7 DONE: every module imports

- Commit "feat: make every conary module import on Python 3". py3tests/test_imports.py (one subprocess per module):
  134 failed before, 0 after; 4 allow-listed modules assert the exact missing package (pgsql, kid).
- Decision: dependency names, flags, flavors and frozen deps are str in Python and in dep_freeze.c; bytes only on the wire.
- Advisor review: MINOR. Orchestrator fixed the hidden cgi dependency in repository/transport.py (cgi left the stdlib in
  3.13; webob installs a third-party cgi.py that masked it) with an email.message helper matching cgi.parse_header on
  five cases, plus a test that blocks cgi and imports transport (fails on the old code).
- Gates: 364 passed; compile_check 475 files, 0 failures; check.sh passes.

PATTERN: build - conary/lib/elf.so is built by `devenv/run make -C conary/lib elf.so`, separate from conary/lib/ext.
PATTERN: py3-port - Class-body comprehensions cannot see class variables in Python 3; use a plain loop.
PATTERN: py3-port - imp.load_module/load_source -> util.loadSourceModule(name, path).
PATTERN: testing - Import tests need one subprocess per module; in-process ordering hides failures.
PATTERN: container - Third-party packages can reinstate removed stdlib modules (webob brings cgi.py); test critical imports with the module blocked via sys.meta_path.
PATTERN: bytes/str - Dependency/flavor strings are text everywhere above the wire; dep_freeze.c rejects bytes.

## 2026-11-23 - task 1.8 DONE: conary --version with clean stderr; phase 1 complete

- Commit "fix: remove Python 3 SyntaxWarnings so the CLI runs with clean stderr": 92 warnings (81 escapes, 11 is-literal).
  py3tests/test_cli.py and test_syntax_warnings.py; full py3tests 369 passed; compile_check 0 failures.
- Orchestrator verified: conary/cvc --version rc 0 and 0 bytes stderr; a full AST comparison of the 38 changed files shows only
  the 9 is-literal files changed AST, so the escape rewrite kept every string value.
- Deviation logged: bare --help exits 1 by upstream design (mainhandler.usage rc=1); tests assert 1.
- Phase 1 collapsed into TASKS-archive.md.

PATTERN: verification - After a mechanical literal rewrite, compare ast.dump of HEAD vs working tree per file; only files with intended semantic edits may differ.
PATTERN: testing - conary/constants.py defines lowercase `version`.

## 2026-11-26 - task 2.1 DONE: testrunner harness rebuilt

- Phase 2 planned (commit b74d4a5c6). The SAS harness (testrunner, testutils) is not in any branch or tag of the fork or of
  sassoftware/conary, nor on GitHub or PyPI, so it is rebuilt in testharness/ from what conary_test uses.
- testharness/testrunner/{testhelp,testcase,decorators,runner,suite}.py. SkipTestException subclasses unittest.SkipTest and
  is one class in every module. context() appends to func._contexts. mock() saves the raw __dict__ entry, delattrs inherited
  attributes and keeps staticmethod/classmethod wrapping. captureOutput captures at fd 1 and sys.stdout. mimicRoot logs
  chown to self.chownLog and executes chmod while logging it to self.chmodLog.
- Advisor plan: REVISE. It added self.logFilter/testcase.LogFilter (34 files, about 600 calls) and TestCaseWithWorkDir, dropped
  assertContent (webunit's WebTestCase; webtest.py skips without webunit), and required descriptor-aware mock.
- Review: REJECT, then MINOR after one fix round. Fixed: ignore() before add(), a str expected value is one record, and
  compare(allowMissing=True). Orchestrator tightened the testhelptest subprocess check to assert returncode and the exact
  summary line.
- MINOR notes (not fixed): the resolve scan does not follow `testrunner.x.attr` after a plain `import testrunner.x` (no such
  imports today); compile_check.sh roots do not include testharness/ (py3tests imports cover it).
- Gates: py3tests 410 passed (41 new); compile_check 475 files, 0 failures; pyflakes clean on the new files.

PATTERN: testing - Harness semantics must be checked against real call-site order (ignore() before add(), multi-line single log records, allowMissing=), not just self-consistent unit tests.
PATTERN: testing - Subprocess pytest runs must assert returncode as well as the summary text.
PATTERN: tooling - devenv/compile_check.sh runs on the host (it needs shasum, which the container lacks).
PATTERN: harness - conary_test/__init__.py imports testrunner itself, so running any conary_test module needs testharness/ on PYTHONPATH before collection.

## 2026-11-26 - task 2.2 DONE: testutils.mock

- testharness/testutils/mock.py: MockObject, MockInstance, MockParams, mock, mockMethod, mockClass, unmockAll. The ast scan
  of `<expr>._mock.<attr>` found the real API: set, assertCalled (consumes the matched call; updatecmdtest 1071/1082),
  setDefaultReturn, setReturn, appendReturn (FIFO), enableMethod, assertNotCalled, raiseErrorOnAccess. The default return
  is one stable child MockObject. mockClass builds a real subclass whose __new__ returns a MockInstance, because packagepolicy
  isinstance-checks a patched magic.jar.
- The 2.1 save/restore logic moved into testutils.mock (patch/restore) and is shared by TestCase.mock. TestCase.tearDown
  also calls mock.unmockAll(), since rpmtest and updatecmdtest leak patches on failure paths. mock.py never imports testrunner.
- Ran as a parallel batch with 2.3 in worktrees. Advisor plan PROCEED; review MINOR.
- MINOR notes: test_testutils_mock.py has its own conary_test source walker, duplicating test_testharness_resolve._sources;
  MockInstance mocks properties unless enabled (SystemModelFile.contents would be a MockObject), deliberate and tested.
- Gates: py3tests 443 passed; compile_check 475 files, 0 failures; pyflakes clean.

PATTERN: environment - Workflow worktrees are cut from garnet, not py3: reset the scratch branch to py3 first and copy the gitignored build outputs (conary/constants.py, conary/**/*.so) from the main checkout. Tell workers this up front.
PATTERN: testing - Scan `<expr>._mock.<attr>` with ast to find the harness API a module-attribute scan cannot see; assert known names are found so the scan cannot pass vacuously.
PATTERN: harness - testutils.mock must not import testrunner; testrunner.testhelp imports testutils.mock.

## 2026-11-26 - task 2.3 DONE: rest of testutils

- testharness/testutils/: sock_utils.tryConnect(host, port, count=100, interval=0.1) retries create_connection and raises
  ConnectionRefusedError; os_utils.effectiveUser/effectiveGroup are strings (rephelp formats them into the squid config);
  base_server.BaseServer; sqlharness.start() and servers/ (SkippedServer base for Nginx, Gunicorn, Uwsgi, Memcache) raise
  SkipTestException on start/getUrl/getHostPort.
- Advisor plan PROCEED; review MINOR. Orchestrator follow-ups: SkippedServer.errorLog is os.devnull (None crashed
  ConaryServer.checkForTracebacks with TypeError), the resolve test now covers testutils.mock, the fd-count helper falls back
  to /dev/fd off Linux, and a task number was dropped from a comment in test_testutils_mock.py.
- Applied after 2.2 from a worktree patch, excluding the shared empty testutils/__init__.py.
- Gates: py3tests 468 passed; compile_check 475 files, 0 failures; pyflakes clean.
- For 2.7: sqlharness.start() skipping means every repository-backed and dbstore test skips (rephelp.openRepository,
  DBStoreTestBase.setUp). A SQLite-only sqlharness is likely the biggest unlock in Phase 3.

PATTERN: harness - Stand-ins that skip must still satisfy the teardown paths that touch them (errorLog is opened by checkForTracebacks); grep the callers of every attribute a stand-in sets.
