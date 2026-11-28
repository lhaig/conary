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

## 2026-11-26 - task 2.4 DONE: pytest runner for conary_test

- Repo-root pytest.ini: `pythonpath = . testharness`, `python_files = test_*.py *test.py`, and markers for each CONTEXTS name.
  conary_test/conftest.py pops the proxy env vars, warns on old sqlite, loads _norpmlock.so through norpmlock.open, and maps
  `_contexts` on the function and class to markers, registered dynamically.
- Collection: 112 module errors -> 0, and 2810 tests collect. Causes: rephelp `import new` (111 modules; new.instancemethod
  became setattr); M2Crypto and conary.server.server.SecureHTTPServer imported unguarded (M2Crypto has no Fedora 45 /
  Python 3.15 package, so both are guarded and HTTPServerController skips SSL); a genuine conary bug in versions.py, where
  ThawVersion/VersionFromString encoded str to bytes (a 2to3 unicode->str inversion), which broke every str version parse.
- C: conary_test/pycompat.h was missing the `&` on PyModule_Create; norpmlockmodule.c needed PY_SSIZE_T_CLEAN. The Makefile
  builds norpmlock.so (Python 3 cannot import `<name>module.so`) and no longer links libpython.
- testsuite.py is now a thin `pytest conary_test` wrapper anchored to its own directory. The setupPaths logic lives in
  conary_test/conftest.py.
- Review MINOR. Orchestrator added the rpm/installed_conarydb wrapper marker test and anchored the wrapper path.
  Not fixed: the synthetic marker test writes a temporary file into conary_test/ (removed in finally); transporttest SSL
  tests fail rather than skip without M2Crypto (for 2.7 triage).
- For 2.6, other encode-str spots to review: trovetup.py:284, lib/pydeps.py:207, dbstore/psycopg2_drv.py:391,
  dbstore/base_drv.py:113, lib/openpgpkey.py:119, lib/openpgpfile.py:272, lib/http/request.py:204, lib/util.py:1753.
- Gates: py3tests 477 passed; collect-only 2810, 0 errors; compile_check 476 files, 0 failures; pyflakes clean on new files.

PATTERN: harness - pytest.ini `pythonpath` is the only reliable place for sys.path; conary_test/conftest.py is imported after conary_test/__init__.py already needs testrunner.
PATTERN: py3-port - 2to3 left `isinstance(x, str): x.encode(...)` inversions (from unicode); they break str callers. Check each hit.
PATTERN: c-api - Python 3 cannot import `<name>module.so`; build `<name>.so`, and extension modules must not link libpython.
PATTERN: environment - M2Crypto has no Fedora 45 / Python 3.15 package; SSL test paths skip or fail.
PATTERN: build - Build conary_test C extensions explicitly with `make -C conary_test`, never from a conftest.
PATTERN: testing - Re-measure any count an advisor gives before asserting it (acltest has 9 entitlements tests, not 4).

## 2026-11-26 - task 2.6 DONE: bytes/str at the C boundary

- Ran as a parallel batch with 2.5 in worktrees and was applied first. Advisor plan REVISE; review MINOR.
- Rule (conary/streams.py docstring plus comment blocks in pack.c, streams_set.c, streams_string.c, streams_numeric.c):
  frozen/wire data is bytes, so freeze()/diff() return bytes and thaw()/twm()/StreamSet() take bytes via y# only. StreamSet
  tag names are interned str. pack formats are str and S/D data is bytes. StringStream holds bytes (str is UTF-8 encoded on
  set). The Sha1/Md5/Sha256 streams are bytes only. Deps/flavor streams keep text freeze() (1.7). Version and strings
  streams hold str and freeze to UTF-8.
- Extra fixes: StreamSet equality called member.__eq__(other, skipSet), which raises TypeError on compiled streams (now
  rich compare); Md5Stream.set called StringStream.set without self; StreamCollection dropped sys.intern on bytes and its
  hasattr('__cmp__') check.
- MINOR notes: OptionalFlavorStream.diff() still returns str when both sides have flavors (the C bridge encodes it); the
  memberEq TypeError fallback could swallow a real TypeError; StringsStream.thaw(str) raises AttributeError.
- Ripple for 2.7/Phase 3: StringStream values (trove names, owner/group, changelog fields) are now bytes and need decoding
  at the trove.py/files.py layer. conary_test/streamstest.py went from 17 failed/6 passed to 18 failed/5 passed; its tests
  use str literals.

PATTERN: c-api - Compiled streams' __eq__ is the tp_richcompare slot wrapper (one argument); compare via PyObject_RichCompare from C.
PATTERN: c-api - There is no bytes-only 'z#'; use 'O' plus a None-or-bytes check so str is rejected.
PATTERN: py3-port - sys.intern() rejects bytes; do not intern wire data.

## 2026-11-26 - task 2.5 DONE: undefined Python 2 names

- conary/lib/compat.py gains cmp (None sorts first) and CmpMixin (__lt__/__le__/__gt__/__ge__ from __cmp__, NotImplemented
  passed through, __slots__ = ()). It is used by SerialNumber, Revision, VersionSequence, the deps classes, 10 trove.py classes,
  _ValueStream and sqllib.DBversion. DBversion gets __eq__.
- Sorts: single-field sorts use key=. Multi-key, None-safe and public comparator APIs use cmp_to_key. graph.NodeData.sort,
  NodeDataByHash.sort and sortSubset raised TypeError even with no comparator, so every graph walk was broken.
  local/update.py cmpLine and cmds/queryrep.py were also missed by pyflakes. cache._shrink had a float slice.
- file() became open(), mode checked against the Py2 original and the consumer. Binary: magic, javadeps, capsulepolicy,
  source (RPM/signatures), packagepolicy _markConfig, checkin, netserver pickle, logger syncFile. xmlrpclib became
  xmlrpc.client. 22 xxx_todo_changeme placeholders renamed.
- Review MINOR. Not fixed: magic.py and javadeps.py now read bytes but compare against str signatures, so file-type
  detection silently finds nothing (before, it raised NameError). Orchestrator replaced the test that pinned that behaviour
  with 3 strict xfails (gzip, script, java class magic). compat.cmp does not order None nested inside tuples. The trove
  classes' __cmp__ was tested on stand-ins (real instances could not be built before 2.6).
- versionstest went from 3 failed to 1 failed (that test uses builtin cmp itself).
- Gates after both: py3tests 651 passed, 3 xfailed; collect-only 2810, 0 errors; pyflakes 0 file/cmp/xmlrpclib;
  compile_check 476 files, 0 failures.

PATTERN: py3-port - Fixing cmp inside __cmp__ silences pyflakes but Python 3 never calls __cmp__; the class needs CmpMixin, plus __eq__ where it has none.
PATTERN: py3-port - Positional comparators (sorted(x, f), x.sort(f)) are invisible to pyflakes; find them with an AST scan.
PATTERN: bytes/str - Switching a reader to 'rb' without converting its literal comparisons to bytes turns a loud failure into silent wrong results; convert both together or add a strict xfail.
PATTERN: py3-port - Removing the builtin `file` name surfaced real Py2 bugs (display.getBuildLog returned the file type).

## 2026-11-26 - task 2.7 DONE: conary_test baseline and Phase 3 triage plan

- prds/research/conary_test-baseline.md. On Apple silicon the container is aarch64 and conary/build/use.py has no aarch64
  arch: 2303 of 2481 failures in the native run. The baseline (Run B) was made on linux/amd64 in a throwaway copy of the tree
  (no .git, so env.txt has no HEAD); it can only be reproduced with committed tooling once Phase 3 task 2 adds a platform switch.
- Run B: 2810 collected; 242 pass, 821 fail, 1653 skip, 0 xfail, 94 not run (91 requireChroot segfaults, 3 filestest leaving a
  deleted cwd), 1 timeout. 81 minutes, nearly all openRepository retries on SkipTestException.
- Classes (2819 failure/error elements): removed stdlib 2341 (util.rmtree os.path.walk in teardown, 2325), py3 semantics
  110, bytes/str streams/trove 69, hashing 67, file I/O 64; unknown 42. Skips: sqlharness 1585, other 60, missing binary 6,
  servers 1, M2Crypto 1. Run C (os.walk patched in the throwaway copy only): 199 fail->pass, 113 fail->skip.
- Static scan: 198 of 1018 embedded recipe strings do not parse on Python 3.
- Added python3-pytest-timeout (Dockerfile, check.sh), devenv/conary_test_baseline.sh, devenv/triage.py and py3tests/test_triage.py.
- Review MINOR. Orchestrator fixed the doc's task cross-references, explained table order vs order of work, and made the
  baseline script reject absolute or unsafe outdirs. Not changed: triage's harness-gap rule matches skip text anywhere in the
  traceback tail and captured output (9 elements now); narrow it to the exception message once repository tests run.

PATTERN: environment - On Apple-silicon Docker the devenv container is aarch64 and conary/build/use.py has no aarch64 Arch; conary_test needs linux/amd64 (or an aarch64 arch) to give meaningful results.
PATTERN: environment - devenv/run only passes --user on Linux, so on macOS the tests run as uid 0 in the container.
PATTERN: harness - util.rmtree still calls os.path.walk; rephelp tearDown raises on every test, so pytest records a skip plus an error for one id.
PATTERN: harness - conary_test requireChroot segfaults (ctypes libcap without restype/argtypes) and kills the pytest process; run per file and fall back to per id.
PATTERN: harness - rephelp.openRepository retries SkipTestException 4 times with sleeps, about 3 s per repository-backed test.
PATTERN: bytes/str - hashlib callers (util.getId, util.copyfileobj, sha1helper.sha1String/md5String) still pass str.

## 2026-11-26 - tasks 3.1 and 3.2 DONE

- 3.1: os.path.walk replaced by os.walk in util.rmtree, util.copytree and Policy.do (the only three sites). Topdown walking
  chmods children before os.walk lists them; followlinks stays False. py3tests/test_util_rmtree.py (11 cases). utiltest.py:
  31 failed/18 passed/2 errors -> 24 failed/25 passed, os.path.walk errors 501 -> 0. Review MINOR. The orchestrator changed the
  policy test so it runs Policy.do itself, and a mutation check now fails it. The permission cases skip as root (devenv on macOS); the reviewer
  ran them as uid 65534 and they passed.
- 3.2: rephelp.openRepository re-raises unittest.SkipTest before the bare except, so a skip costs no retries. acltest.py
  on amd64: 103 s -> 5.6 s, with identical per-id outcomes. Review PASS.
- py3tests 686 passed, 3 skipped, 3 xfailed; compile gate 476 files, 0 failures. Full re-baseline deferred to after 3.3.

PATTERN: testing - A test that copies the production loop into its own body does not guard the change; call the changed function.
PATTERN: testing - Permission-mode tests skip as root; until the container runs non-root, verify by dropping privileges (os.setuid in a wrapper).
PATTERN: harness - Put a narrow `except unittest.SkipTest: raise` in front of a bare except so retry behaviour stays otherwise unchanged.

## 2026-11-26 - task 3.3 DONE: platform switch, toolset, non-root, aarch64 arch

- devenv/run: DEVENV_PLATFORM (for example linux/amd64) gives a separate image tag per platform. It always passes --user uid:gid with HOME=/tmp;
  DEVENV_ROOT=1 opts out. Dockerfile: cpio, rpm-build, patch, unzip, xz-lzma-compat, python-unversioned-command (cmdlinetest
  execs a bare python). check.sh verifies them.
- aarch64: the arch is defined by data, not by use.py. Added config/arch/aarch64 and conary_test/archive/arch/aarch64 (LE, bits64, lib64)
  and the Makefile entry. py3tests/test_use_arch.py includes a negative case: without the file, 'No Such Arch aarch64' comes back.
- Re-baseline at HEAD b609b1f78 as uid 501:
  - native aarch64: 450 pass, 514 fail, 1755 skip, 91 not run, 7 min
  - amd64: 450 pass, 513 fail, 1756 skip, 91 not run, 12 min
  - Run B was 242 pass, 821 fail, 1653 skip, 94 not run, 81 min
  - Top classes: py3 semantics other 111, bytes/str streams 70, hashing 68, file I/O 64, py2 in tests 60.
- Review MINOR. Follow-up logged under Later: guard against stale .so files from the other arch.
- py3tests 702 passed, 3 xfailed as uid 501 (the rmtree permission tests now run); compile gate clean.

PATTERN: environment - Build outputs (.so) are arch specific in the shared checkout; after switching DEVENV_PLATFORM run make clean in conary/lib, conary/lib/ext and conary_test. A stale foreign-arch .so fails import with 'cannot open shared object file' although the file exists.
PATTERN: environment - Arches come from arch data files (config/arch, conary_test/archive/arch), not from use.py.
PATTERN: testing - Hardcoded x86 expectations in conary_test hide behind sqlharness skips; expect an arch-specific class to grow after 3.14.
PATTERN: tooling - devenv/conary_test_baseline.sh overwrites its outdir; use a dated outdir per run.

## 2026-11-26 - tasks 3.4 and 3.5 DONE

- 3.4 hashing: the rule lives in the sha1helper docstring and in sha1helper.toBytes: str becomes utf-8/surrogateescape bytes, bytes-like passes through, and
  anything else raises TypeError. Most text callers hash persisted identities (pathIds from md5String(path), fingerprints), so
  encoding at the helper boundary reproduces Py2 digests. Fixed getId (str in both branches), filetypes devnull 'wb' and RegularFile
  bytes, FromString (stores bytes, BytesIO), fingerprints (bytes join, decodebytes of str or bytes), build.sha1sum, proxy
  memcache keys, and netauth keys and passwords. copyfileobj is unchanged: the openers used the wrong mode.
  'Strings must be encoded' went to 0 in the measured modules (cmdlinetest 29 failed/28 passed -> 6 failed/51 passed). Most of the remaining
  failures there are streams class (files.py:419 str + bytes) or file I/O (util.py:908).
- 3.5: requireChroot uses typed ctypes and frees its pointers; _hasChrootCap parses bytes. files.UserGroupIdCache restores
  the chroot and cwd in nested finally blocks (_chrootTo), which was the real cause of the "deleted cwd" crash. All 91 not-run ids now report.
- Review MINOR on both. Orchestrator fixed: FromString encoding str (production trovecache passes str), fingerprint blocks
  arriving as str, a known vector for nonstandardSha256String, a memoryview case, printf in place of echo -n, and a public toBytes.
- py3tests 763 passed, 3 xfailed; compile gate clean; pyflakes clean on the touched files.

PATTERN: bytes/str - One encode rule, one helper: sha1helper.toBytes (utf-8, surrogateescape). Reuse it instead of local copies.
PATTERN: bytes/str - When a shared helper changes its return type (FromString.get to BytesIO), audit every caller, production and test.
PATTERN: harness - ctypes pointers that must be freed need restype c_void_p, never c_char_p; check for NULL before string_at.
PATTERN: harness - A "deleted cwd" crash can come from production code that chroots or chdirs without try/finally (files.UserGroupIdCache).

## 2026-11-26 - checkpoint baseline after 3.5 (native aarch64, uid 501, HEAD e39a4f7, tmp/baseline-20261126-e39a4f7)

- 2808 ids: 488 pass, 467 fail, 1 error, 1852 skip, 0 not run (was 450/514/1755/91 after 3.3).
- Classes (469): py3 semantics other 117, bytes/str streams/trove 83, file I/O 63, py2 code in tests 61, bytes/str other 43,
  unknown 56, removed stdlib 16, iterator 10, harness gap 8, sort/compare 6, integer division 2, network 2, arch 1, timeout 1,
  hashing 0.

## 2026-11-26 - tasks 3.7 and 3.8 DONE

- 3.7: The task text was wrong on three points: nothing subclassed sqlite3.Connection, DictAsCsf was not missing __next__ (2to3
  renamed the attribute read `self.next` to `self.__next__`), and has_key was in sqllib.CaselessDict. Fixes: a Connection subclass
  via factory= so dbh._BEGIN works; next(cu); self-recursive 2to3 methods; PEP 479; CaselessDict. The 7 target modules went from
  37F/17P to 27F/27P; the rest is streams/trove (files.py:419, troveinfo.py:43), removed stdlib (Marshaller.dump_string)
  and py2-in-tests.
- 3.8: Bytes signatures plus os.fsdecode for metadata, across magic, javadeps, rpmhelper, cpiostream, ar, logger, xmllog,
  filecontainer and util readers. The 3 strict xfails in py3tests are gone. Large module gains (magictest, cpiostreamtest,
  rpmhelpertest, artest, rpmtest).
- The two ran concurrently in one tree and overlapped in util.py, changeset.py and filecontainer.py. They were committed as two
  commits, with the overlap carried in the db commit and noted in its message.
- py3tests 819 passed; compile gate clean.

PATTERN: testing - A lock or transaction test that uses a statement exempt from the code path (SELECT) passes vacuously; assert the SQL actually sent with set_trace_callback.
PATTERN: py3-port - 2to3 turned attribute reads `self.next` into `self.__next__` and `items()` bodies into `list(self.items())` (infinite recursion); grep for both.
PATTERN: tooling - Parallel tasks in one tree must own disjoint files in practice, not just on paper: shared helpers (util.py) get touched by both.

## 2026-11-26 - tasks 3.9 and 3.6 DONE

- 3.9: Mechanism is a TextStream subclass of StringStream, so the wire format is unchanged and the str API is decided once per field.
  The rule table is in the conary/streams.py docstring. One decode helper: sha1helper.toStr (utf-8, surrogateescape), the inverse of toBytes.
  Files use bytes type tags with slice comparisons (bytes[0] is an int). trove.py had py2 '/' division and ord/chr in its
  freeze/thaw code. The ten target modules went from 100 failures to 43.
- 3.6: About 45 conary_test modules converted, with a pyflakes and AST guard in py3tests. 88 assertRaises-return uses are left for the harness.
- py3tests 880 passed; compile gate clean.

PATTERN: bytes/str - Decide str vs bytes per stream field with a TextStream subclass, not per call site; the wire bytes stay identical.
PATTERN: bytes/str - Indexing bytes gives an int, so compare single-byte tags with a slice (frz[0:1] == b'd'); an index comparison silently fails.
PATTERN: review - Run pyflakes on new py3tests files too, and compute "before" counts from the checkpoint junit.

## 2026-11-26 - checkpoint after 3.9/3.6 (native, HEAD 8fcd721, tmp/baseline-20261126-8fcd721)

- 2810 ids: 637 pass, 298 fail, 1875 skip, 0 not run (was 488/467/1852 after 3.5).
- Classes: py3 semantics other 83 (74 of them are IsADirectoryError in util.loadSourceModule = 3.10), unknown 61, file I/O 41,
  bytes/str other 41, streams/trove 25, removed stdlib 16, harness gap 11, sort/compare 10 (cml.iterFormat 8), py2 in tests 0.
- Skips: sqlharness 1719, rpm/chroot 91 (no cap_sys_chroot in the container), other 61.

## 2026-11-26 - tasks 3.10 and 3.12 DONE

- 3.10: Py2 behaviour reconstructed from imp.c: fopen of a directory succeeds, the read fails as EOF, and the result is an empty module, so no
  macros and no error. loadMacros now skips directories; loadSourceModule keeps raising for explicit files. The 74
  IsADirectoryError failures moved on to recipe.py:197 `__func__` (76 tests), which went to the front of 3.11.
- 3.12: openpgptest has 0 failures, from test-side bytes fixes only. Harness captureOutput gained _returnException and logLevel.
- py3tests 921 passed; compile gate clean.

PATTERN: py3-port - To reproduce Py2 behaviour, trace the C implementation (imp.c, fopen) and confirm with garnet history when python2 is unavailable.
PATTERN: tooling - Never git stash in a tree shared with a concurrent task; compare against `git show HEAD:<file>`.

## 2026-11-26 - tasks 3.11 and 3.13 DONE

- 3.11: Recipe.__init__ compares plain functions (getattr(x, '__func__', x)); that cleared the 76-test signature, and expansiontest,
  grouppolicytest, grouprecipetest, policytest, cmltest, xmllogtest and trovetuptest now pass fully. Harness assertRaises returns
  the exception. XML-RPC send side uses toBytes; the receive side is open (Later).
- 3.13: HTTP client bytes on the wire, with one basicAuth helper. The SSL tests were already skipping.
- py3tests 1027 passed; compile gate clean.

PATTERN: py3-port - Recipe-style method introspection: Py3 class attributes are plain functions; use getattr(x, '__func__', x).
PATTERN: bytes/str - Text bound for the wire (XML-RPC base64, HTTP auth) goes through sha1helper.toBytes so surrogate-escaped input reproduces the Py2 bytes.

## 2026-11-26 - checkpoint after 3.11/3.13 (native, HEAD f96366f, tmp/baseline-20261126-f96366f)

- 2810 ids: 757 pass, 177 fail, 1876 skip, 0 not run (was 637/298/1875 after 3.9/3.6; 242/821/1653/94 at the 2.7 baseline).
- Classes: unknown 94 (38 are PolicyError at policy.loadPolicy: 'missing required policy SharedLibrary'), bytes/str other 32,
  streams/trove 26, network/xmlrpc 7, harness gap 7, file I/O 0, hashing 0, py2 in tests 0.
- Skips: sqlharness 1720, rpm/chroot 91, other 61. Tasks 3.14 and 3.15 remain (repository milestone).

## 2026-11-26 - tasks 3.14 and 3.15 DONE

- 3.14 (scope extended by user decision: SQLite plus a stdlib app server instead of gunicorn/nginx): repository tests now open a
  live repository. Getting requests through took server-side bytes fixes in netclient, netserver, netauth, reposlog, wsgi_hooks,
  xmlshims and the sqlite driver. Commit is blocked in changeset/filecontainer text-mode I/O; that is new task 3.16, guarded by
  a strict xfail. 17 measured modules: 12/11/306 -> 76/236/18 (pass/fail/skip).
- 3.15: every embedded recipe string parses on Python 3 (scan of 1044 candidates, mutation-checked). Runtime gain waits on 3.16.
- py3tests 1071 passed, 1 xfailed; compile gate clean; pyflakes no new warnings (8 netserver undefined-name warnings fixed).

PATTERN: py3-port - `except X as e` unbinds e at the end of the block; code that inspects or re-raises e afterwards must save it first (raise err, not bare raise).
PATTERN: harness - Opening a skip gate moves tests to the next gate; check what sits behind it (here the app server) before sizing the gain.
PATTERN: testing - A scan test that skips inputs it cannot parse must report them, or a broken file silently drops out of coverage.

## 2026-11-26 - new baseline after 3.14/3.15 (native, HEAD 7c01d5e, tmp/baseline-20261126-7c01d5e, 15 min)

- 2810 ids: 856 pass, 1791 fail, 163 skip (was 757/177/1876). The sqlharness skip is gone; this replaces the old skip count.
- Skips: rpm/chroot 91, other 65, SSL/memcache stand-ins 4, missing binary 2, M2Crypto 1.
- Top signatures: filecontainer.py:__init__ text-mode write 977 (task 3.16), state.py CONARYFileMissing 432,
  sha1helper.sha1ToString str 149, PolicyError SharedLibrary 39, conarycfg append 16, versionops 12.
- 5 duplicate ids across files (new with this run); check before the next checkpoint.

## 2026-11-26 - task 3.16 DONE

- The repository commit path works: rephelp.addComponent commits and getTrove reads it back. FileContainer is strict bytes and
  changeset tags go through four helpers. filecontainer.py:__init__ 977 -> 0. Run tmp/baseline-20261126-07ef2067a-t316:
  1037 pass / 1606 fail / 167 skip (was 856/1791/163).
- CONARYFileMissing (596) is a case-insensitive macOS bind mount artifact, not downstream of commits: new task 3.17.
- py3tests 1113 passed; compile gate clean; pyflakes no new warnings.

PATTERN: bytes/str - Run new bytes tests under `python3 -bb`; a silent bytes == str comparison returns False and hides empty results.
PATTERN: tooling - The macOS bind mount is case-insensitive: os.path.exists('CONARY') is true for the repo's conary/ directory.
PATTERN: py3-port - tempfile.NamedTemporaryFile: setting `.delete = False` on the wrapper does nothing since 3.12; pass delete=False.
PATTERN: bytes/str - Wire base64 goes through sha1helper.toBase64/fromBase64; base64.encodestring/decodestring are gone.
PATTERN: testing - A driver hook used only by explicit callers (cu.encode) is not exercised by plain execute(); test it through the caller's path.
PATTERN: tooling - Do not edit source while devenv/conary_test_baseline.sh runs; the container bind-mounts the live tree.

## 2026-11-26 - task 3.17 DONE

- conary/state.py stateFileExists: exact-case listdir check plus isfile, shared with ConaryStateFromFile. Used at cook.guessSourceVersion,
  checkin.setContext and the cvc cook command. CONARYFileMissing 596 -> 0 in tmp/baseline-20261126-t317 (1038 pass / 1605 fail / 167 skip).
- The unblocked tests fail one step later: captureOutput passes `_printOnError` to cook.cookObject (626, new task 3.18). Next after that:
  sqlite CursorError bindings, sha1ToString 159, py3 semantics 71 (modelupdatetest UnboundLocalError `exception`).
- py3tests 1125 passed; compile gate clean; pyflakes no new warnings. Review MINOR (per-module counts: only buildtest moved, 0/56 -> 1/55).

PATTERN: testing - A guard test for a case-insensitive-filesystem fix must fold case itself (monkeypatch os.path.exists/isfile), or it passes vacuously on Linux.
PATTERN: testing - Removing a top failure signature can leave the pass count flat; check what the same tests hit next before sizing the gain.

## 2026-11-27 - task 3.18 DONE

- testhelp.captureOutput consumes `_printOnError` and `_removeBokenPipeErrors`; on error it echoes the capture to the real stdout
  (flag set) after restoring fd 1, then re-raises the original exception. `_printOnError` signature 626 -> 0.
- Run tmp/baseline-20261127-t318: 1041 pass / 1602 fail / 167 skip. Top signatures: 623 SystemExit at cook.cookObject (no conary
  policy directory; conary-policy is not in the container), 397 sqlite CursorError bindings, 159 sha1ToString, 49 streams.diff,
  41 PolicyError, 27 util.copyfileobj, 21 http OpenError, 20 sigprotect UnboundLocalError.
- py3tests 1132 passed; compile gate clean; pyflakes clean. Review PASS; orchestrator removed an unused assignment.

PATTERN: testing - When a harness helper must print after restoring redirected stdout, store the exception, restore, then print and re-raise the original object.
PATTERN: tooling - A full baseline leaves testcase.recipe, testcase/ and a CONARY entry in the repo root; on the case-insensitive mount never rm -rf CONARY (it is conary/), check git status instead.
PATTERN: harness - The cook tests need conary-policy on CONARY_POLICY_PATH; without it cook.cookObject calls sys.exit(1).

## 2026-11-27 - task 3.19 DONE

- User decision: conary-policy comes from the fork lhaig/conary-policy, cloned next to this repo, ported on its own py3 branch
  (commit 47638e8, pushed). devenv/run mounts it read-only at /policy and sets CONARY_POLICY_PATH; the baseline records its describe.
- 22 policy modules (not 23) parse and import on Python 3; policy.loadPolicy loads them with SharedLibrary.
- Run tmp/baseline-20261127-t319: 1134 pass / 1509 fail + 13 errors / 167 skip (t318 1041/1602/167). SystemExit 623 -> 0,
  PolicyError 41 -> 0. Top signatures, all in conary/: sqlite CursorError 491, cook._cookPackageObjWrap UnsupportedOperation 471,
  sha1ToString 159, streams.diff 49, util.copyfileobj 27, sigprotect UnboundLocalError 21, http OpenError 21.
- py3tests 1186 passed; compile gate clean; pyflakes clean. Review MINOR; orchestrator added the pyflakes undefined-name test.

PATTERN: py3-port - On Python 3.14+ (PEP 758) `except X, e:` parses as a tuple of types; parse/import tests miss it, pyflakes undefined-name catches it.
PATTERN: tooling - Commit a sibling repo before a baseline that depends on it, so env.txt records a clean hash.

## 2026-11-27 - task 3.21 DONE

- cook._cookPackageObjWrap and logger.Logger._becomeLogSlave dup fd 0 directly instead of sys.stdin.fileno() (pytest's captured stdin
  has no fileno). UnsupportedOperation 471 -> 0. Run tmp/baseline-20261127-t321: 1163 pass / 1480 fail + 12 errors / 167 skip.
- Those tests now fail at /policy/policy/libraries.py:301 dict changed size during iteration (296, task 3.20) and cook._callSetup
  CookError (107: recipe-level AttributeErrors such as 'Run'/'Make' object has no attribute 'args' in build.py).
- Top signatures t321: CursorError 491, policy doProcess RuntimeError 297, sha1ToString 159, CookError _callSetup 107, streams.diff 49.
- py3tests 1192 passed; compile gate clean; pyflakes no new warnings. Review MINOR.

PATTERN: py3-port - Save and restore the literal fds (os.dup(0)), not sys.stdin.fileno(): sys.std* may be a pseudofile under pytest or embedding.
PATTERN: testing - A fd 0 redirect test under pytest must point fd 0 at a pipe first; capture already makes it /dev/null, so a devnull check is vacuous.

## 2026-11-27 - task 3.22 DONE

- sqlite_drv.Cursor.executemany normalizes rows lazily (scalar -> 1-tuple, Row -> tuple, ':key' dicts stripped), as the old
  pysqlite3 driver did. CursorError bindings 491 -> 0. Run tmp/baseline-20261127-t322: 1270 pass / 1373 fail + 12 errors / 167 skip.
- Top signatures now: sigprotect.call UnboundLocalError 388, policy.doProcess RuntimeError 297 (conary-policy libraries.py:301,
  task 3.20), sha1ToString 159, cook._callSetup CookError 107, streams.diff 49, util.copyfileobj 27.
- py3tests 1215 passed; compile gate clean; pyflakes no new warnings. Review MINOR.

PATTERN: testing - stdlib sqlite3 binds a sqllib.Row and a plain dict without help, so those cases do not guard a row-normalization fix; str, int and ':'-dict rows do.
PATTERN: testing - A mutation check can monkeypatch the module attribute inside one pytest run instead of editing source.

## 2026-11-27 - task 3.23 DONE

- sigprotect.call saves the caught exception and re-raises the original; handlers restored in finally. UnboundLocalError 388 -> 0.
  Totals unchanged (t323 1270 / 1373 + 12 / 167): the same tests now show their real error, TypeError str + bytes at
  conary/local/journal.py:revert (388, task 3.25).
- py3tests 1224 passed; compile gate clean; pyflakes clean. Review PASS.

PATTERN: testing - A fix that stops hiding exceptions moves tests to a new signature with a flat pass count; report where they went.
PATTERN: py3-port - signal.__dict__ scans break on Python 3 (enum members compare equal to ints); use signal.Signals(num).name.
PATTERN: testing - Signal tests use SIGUSR1/SIGUSR2 with a recording handler, never SIGTERM/SIGINT under pytest.
PATTERN: tooling - A baseline started while Docker Desktop restarts dies after one file; check for rc.txt and rerun.

## 2026-11-27 - task 3.20 DONE

- conary-policy aacdc08: dict-view snapshots (libraries, enforcebuildreqs, badpathnames), normalize rewrites in binary, `_walk`
  for the removed os.path.walk. Dict-size RuntimeError 297 -> 0. Run tmp/baseline-20261127-t320: 1270 / 1373 + 12 / 167 (flat).
- The same 297 tests now fail on `0111` in config/components/base/config.py (py2 octal, SyntaxError 313, task 3.26).
- Top signatures t320: str+bytes concat 395 (journal.py:revert, 3.25), octal SyntaxError 313, bytes-like required 211
  (sha1ToString among them, 3.24), 'Run' has no attribute 'args' 86, unhashable StringVersionStream 49.
- py3tests 1236 passed; compile gate clean; pyflakes no new warnings. Review MINOR; orchestrator fixed the sys.path restore.

PATTERN: py3-port - os.path.walk is gone on Python 3; policy and build code that calls it raises AttributeError at runtime only.
PATTERN: testing - `saved = sys.path` then `sys.path[0:0] = ...` saves nothing; copy the list (list(sys.path)) and restore with sys.path[:] = saved.
PATTERN: py3-port - The ported tree's own data files (config/components/*.py) can still hold py2 syntax; parse them too, not just the packages.

## 2026-11-27 - task 3.24 DONE

- checkin.py placeholder fileIds are b"0" * 20 (4 sites). sha1ToString 159 -> 0. Run tmp/baseline-20261127-t324: 1292 pass /
  1351 fail + 48 errors / 167 skip (+22 pass). The worker was stopped before the baseline ended; the run finished on its own and
  the orchestrator triaged it and had the fix reviewed separately (PASS).
- Side effect: cook tests now reach cook.cookCommand's fork; the child runs the harness atexit cleanups and deletes the shared
  SQLite dir, so later tests in cooktest/factorytest error in teardown (48) and 4 cooktest passes regressed. Task 3.27.
- Top signatures t324: journal.revert str+bytes 388 (3.25), octal SyntaxError 313 (3.26), CookError _callSetup 132,
  util.copyfileobj 71, sqlite connect DatabaseError 53 (3.27), streams.diff 50, http_error.splitSocketError 47.

PATTERN: harness - atexit cleanups registered in the test process also run in forked children that exit through Python; guard them with the creating pid.
PATTERN: tooling - A baseline container keeps running when the client that started it is killed; wait for it to exit before editing source.

## 2026-11-28 - task 3.27 DONE

- Forked cook children no longer run the rest of the test module: testhelp.TestCase._callTestMethod _exits them with their status;
  harness cleanups are pid-guarded. Run tmp/baseline-20261128-t327full: 1296 pass / 1347 fail / 0 errors / 167 skip (t324
  1292 / 1351 + 48 errors). Duplicate ids 47 -> 0.
- Top signatures: journal.revert str+bytes 388 (3.25), octal SyntaxError 323 (3.26), CookError _callSetup 134, util.copyfileobj 93,
  streams.diff 50.
- py3tests 1249 passed; compile gate clean; pyflakes no new warnings. Review MINOR.

PATTERN: testing - A forked child that leaves a test method by SystemExit is caught by unittest/pytest and runs tearDown and every later test; _exit it from the test-method wrapper, and guard atexit too.
PATTERN: testing - More than one pytest summary line in a module log, or duplicate ids across files, means a forked child ran its own copy of the session.

## 2026-11-28 - task 3.26 DONE

- config/components/base/config.py 0111 -> 0o111. Octal SyntaxError 323 -> 0. Run tmp/baseline-20261128-t326: 1300 pass / 1343 fail /
  167 skip. The same tests now fail at conary/build/policy.py walkDir: 'str' object has no attribute 'decode' (286).
- Top signatures: journal.revert 388 (3.25), policy.walkDir .decode 286, CookError _callSetup 135, util.copyfileobj 93, streams.diff 50.
- py3tests 1254 passed; compile gate clean. Review PASS.

PATTERN: testing - The compile gate only covers conary/, conary_test/, commands/, scripts/; data files loaded with loadSourceModule (config/components, macros) need their own parse test.
PATTERN: testing - Loading component files with loadSourceModule registers bare names (test, locale) in sys.modules; restore sys.modules in tests.

## 2026-11-28 - task 3.25 DONE

- Journal entry paths are TextStream; rollback status/count/system-model writes are bytes. journal revert 388 -> 0. Run
  tmp/baseline-20261128-t325: 1307 pass / 1336 fail / 167 skip.
- Top signatures: conaryclient/update.py recordManifest str write 344, policy.walkDir .decode 286, CookError _callSetup 135,
  util.copyfileobj 93, streams.diff 50, localrep.openFile 19, files.restore 15.
- py3tests 1262 passed; compile gate clean. Review PASS.

PATTERN: bytes/str - Fix path fields at the stream type (TextStream), not with fsdecode at each call site; pin the on-disk bytes with a test built independently of freeze().
PATTERN: testing - Error-path code (revert, rollback) hides the original failure; after fixing it, expect the same tests to move to the next write on the main path.
