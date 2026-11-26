# Tasks

Goal: a working Python 3 Conary client. Background and the original scratch-port notes are in
[research/handoff-2026-11-22.md](research/handoff-2026-11-22.md).

Decisions (2026-11-22): Python 3.12+ minimum, Python 2 support dropped, build and test in a Fedora
container (Docker, source bind-mounted), work lands on the `py3` branch. OpenPGP crypto moves from pycrypto to pycryptodomex (2026-11-23).

## Phase 1: Import and version — 8 tasks completed 2026-11-23 (see [TASKS-archive.md](TASKS-archive.md))

## Phase 2: conary_test on Python 3

The SAS harness that conary_test imports (`testrunner`, `testutils`) was never published and is not in any branch or tag of
this fork or of sassoftware/conary (checked 2026-11-26), so it is rebuilt from what the suite uses. The new packages live in
`testharness/testrunner/` and `testharness/testutils/` at the repo root (put on sys.path by the runner). `conary_test/testhelptest.py`
tests the old harness's own behaviour and serves as its spec. Harness unit tests go in `py3tests/`.

| # | Task | PRD | Status | Notes |
|---|------|-----|--------|-------|
| 2.1 | Rebuild `testrunner`: `testhelp` (`TestCase` on unittest.TestCase, `context` tag decorator, `SkipTestException`, `findPorts`, `getTempDir`), `testcase.safe_repr`, `decorators.requireBinary`, `runner.SkipTestException`, `suite` (minimal, for testsuite.py). TestCase helpers conary_test calls that it does not define itself: at least `captureOutput`, `discardOutput`, `writeFile`, `logCheck`, `logCheck2`, `assertContent`, `mimicRoot`, `realRoot`, `mock`/`unmock` (delegating to 2.2's module once it exists; a simple setattr/restore is fine for now). Accept: every symbol conary_test imports from `testrunner` resolves; unit tests per helper in py3tests/; `conary_test/testhelptest.py` cases that do not need testutils pass | - | DONE (2026-11-26) | testharness/testrunner: testhelp, testcase (LogFilter, TestCaseWithWorkDir), decorators, runner, suite. self.logFilter added (about 600 calls; missing from the task text). assertContent left out: it is webunit\'s, webtest skips. testhelptest has 8 cases, not 12, all pass. Review MINOR |
| 2.2 | Rebuild `testutils.mock` (needs: 2.1): `MockObject`, `MockInstance`, `MockParams`, `mock`, `mockMethod`, `mockClass`, `unmockAll`, and wire TestCase `mock`/`unmock` to it. Infer semantics from the call sites (28 MockObject uses, 203 self.mock). Accept: unit tests covering attribute auto-creation, call recording and assertions, return values, mockMethod/mockClass restore via unmockAll; the mock cases in testhelptest.py pass | - | DONE (2026-11-26) | testharness/testutils/mock.py from every call site, including the full `_mock` API (set, assertCalled, which consumes the call, setDefaultReturn, setReturn, appendReturn, enableMethod, assertNotCalled, raiseErrorOnAccess). mockClass returns a real subclass, so isinstance holds. TestCase.mock now shares the patch/restore helpers, and tearDown also calls unmockAll. Review MINOR |
| 2.3 | Rest of `testutils` (needs: 2.1): real `sock_utils` (`tryConnect`), `os_utils` (`effectiveUser`, `effectiveGroup`), `base_server.BaseServer`; `sqlharness` and `servers` (nginx, gunicorn, uwsgi, memcache) importable but raising SkipTest with a clear reason when started. Accept: every symbol conary_test imports from `testutils` resolves; unit tests for the real helpers and for the skip behaviour | - | DONE (2026-11-26) | Real sock_utils.tryConnect (retries, then ConnectionRefusedError), os_utils.effectiveUser and effectiveGroup (plain strings, not context managers), and BaseServer. sqlharness.start and the nginx/gunicorn/uwsgi/memcache servers raise SkipTestException. Review MINOR; orchestrator fixed errorLog (os.devnull) and dropped the mock exclusion from the resolve test |
| 2.4 | pytest runner for conary_test (needs: 2.1-2.3): conftest that puts testharness/ on sys.path, maps `context` tags to pytest markers, and builds/loads the test C extensions (`_norpmlock.c`, `norpmlockmodule.c`); replace or port the Py2 root `testsuite.py`; record the command in config.md. Accept: `pytest --collect-only conary_test` collects every module with zero collection errors (or each remaining one listed with a reason) | - | TODO | |
| 2.5 | Undefined Python 2 names (needs: 2.4): `file` x58, `cmp` x54, `xmlrpclib` x1 from pyflakes, plus the 8 `xxx_todo_changeme` tuple-param placeholders (e.g. repository/changeset.py:979, lib/ext/digest_uncompress.py:32). Accept: pyflakes reports none of these names in conary/; tests for any changed behaviour (cmp-based sorts in particular) | - | TODO | |
| 2.6 | bytes/str at the C boundary (needs: 2.4): pack and streams accept only bytes while 2to3'd callers and .py fallbacks pass str (StringStream('abc'), pack.pack('!B...') raise TypeError); streams_set.c handles attribute names as bytes so StreamSet subclasses cannot be defined; audit the thaw side of streams whose freeze() returns str. Decide and record the rule per stream type (as 1.7 did for deps). Accept: a StreamSet subclass can be defined, frozen and thawed round-trip; tests for the pack/stream str-vs-bytes cases | - | TODO | |
| 2.7 | Baseline run and triage plan (needs: 2.5, 2.6): run the full conary_test, classify every failure (bytes/str, harness gap, missing binary or service, Py2 recipe strings in tests, real bug), write `prds/research/conary_test-baseline.md` with counts and examples per class, and propose Phase 3 fix tasks. No code fixes in this task (spike) | - | TODO | |

## Later (not yet planned)

- C cleanups (from 1.3 review): LongLongStream_Hash leaks a PyLong; deprecated OpenSSL SHA1_* in digest_uncompress.c; stream rich compare across different types now returns NotImplemented (Py2 raised TypeError).
- sqlite (from 1.5 review): a SELECT that starts with a comment, or WITH/PRAGMA/EXPLAIN, takes BEGIN IMMEDIATE (same as the fork); PATHTYPE is TEXT so non-UTF-8 paths fail on bind; callers passing str to binary() now raise TypeError.
- OpenPGP (from 1.6): untested paths: AES/CAST5/Blowfish secret-key decryption, RIPEMD160/MD5 S2K, v3 signature creation, user attributes, trust graph, merging keys with differing UIDs/subkeys, partial body lengths. UIDs decode with errors='replace', so two non-UTF-8 UIDs can compare equal. parseAsciiArmor now reads the whole stream. sk1-sk7.gpg raise BadSelfSignature (expected per CNY-2047, not asserted). util.py still has pyflakes leftovers (`file`, `cmp`, `xmlrpclib` at ~1350, 1459, 1492, 1784).
- From 1.8: bare `conary --help` / `cvc --help` exit 1 (mainhandler.usage rc=1, upstream). Kept; change only by decision. streams.py compares `diff == '\0'` (str) while diffs may be bytes: always False, same as before.
- From 1.7: epdb client/server bytes bugs (epdb_client.py:64,73; epdb_server.py:70,75-77).
- From 1.7: commitaction now loads only dir/name.py (imp.find_module also found packages and .so). Recipe/policy loading via SourceFileLoader writes __pycache__; build/recipe.py's path+'c' cleanup is a no-op. Non-UTF-8 file dependencies raise UnicodeDecodeError. lib/importer.py is ported but unused and untested.
- Follow-ups from 1.2: recipes embedded as strings in conary_test are Py2 (sized in 2.7).

- Phase 3: fix conary_test failures per the 2.7 triage plan.
- Then: install/query/rollback against a local repository, RPM encapsulation proof, build side (rMake replacement), distro decision.
