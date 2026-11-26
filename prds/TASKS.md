# Tasks

Goal: a working Python 3 Conary client. Background and the original scratch-port notes are in
[research/handoff-2026-11-22.md](research/handoff-2026-11-22.md).

Decisions (2026-11-22): Python 3.12+ minimum, Python 2 support dropped, build and test in a Fedora
container (Docker, source bind-mounted), work lands on the `py3` branch. OpenPGP crypto moves from pycrypto to pycryptodomex (2026-11-23).

## Phase 1: Import and version — 8 tasks completed 2026-11-23 (see [TASKS-archive.md](TASKS-archive.md))

## Phase 2: conary_test on Python 3 — 7 tasks completed 2026-11-26 (see [TASKS-archive.md](TASKS-archive.md))

## Phase 3: conary_test failures

Plan, counts and evidence: [research/conary_test-baseline.md](research/conary_test-baseline.md) ("doc #" is the task number
there). Tasks are listed in order of work. After each task, re-run the baseline (`devenv/conary_test_baseline.sh`, then
`python3 devenv/triage.py`) and record the new totals in its notes. Expected unlocks are ceilings: fixing a first error can expose
a second one.

| # | Task | PRD | Status | Notes |
|---|------|-----|--------|-------|
| 3.1 | Replace `os.path.walk` in `conary/lib/util.py` `rmtree` (doc #1). It raises in rephelp tearDown on nearly every test. Accept: unit test of rmtree (files, nested dirs, symlinks not followed, missing path behaviour as before); no `os.path.walk` left in conary/ or conary_test/ | - | TODO | Expect 2325 error elements cleared; 199 fail->pass and 113 fail->skip, measured in Run C |
| 3.2 | `rephelp.openRepository`: stop retrying on `SkipTestException` (doc #3). Narrow the bare `except:` in the `__openRepository` retry loop so a skip propagates at once. Accept: a test that a skipping sqlharness is called once with no sleep; baseline wall time drops from 81 min to a few minutes | - | TODO | Unlocks no tests; makes every later re-measurement fast |
| 3.3 | Container: run as x86_64 on demand and complete the toolset (doc #2). `devenv/run` honours `DEVENV_PLATFORM` (distinct image tag per platform); install cpio, rpm-build, patch, unzip, lzma (and python-unversioned-command if needed); pass `--user` on macOS so tests do not run as uid 0; decide whether to also add an aarch64 arch to `conary/build/use.py` (ask before doing it). Accept: check.sh lists the new binaries; the baseline runs under `DEVENV_PLATFORM=linux/amd64` from the committed tooling, with git HEAD in env.txt; new totals recorded | - | TODO | 2303 tests on arm64 hosts; about 7 on amd64 now, more once repository tests open |
| 3.4 | Hashing callers pass bytes (doc #5): `util.getId`, `util.copyfileobj`, `sha1helper.sha1String`/`md5String`, digestlib callers. Encode at one boundary and record the rule. Accept: unit tests per function with str and bytes input as the rule says | - | TODO | 68 (cmdlinetest 24, acltest, sigtest, filestest, ...) |
| 3.5 | `requireChroot` crash and `filestest` cwd (doc #4): set ctypes `restype`/`argtypes` for libcap in `conary_test/__init__.py`, decode bytes, skip cleanly without `cap_sys_chroot`; stop filestest device/symlink tests leaving a deleted cwd. Accept: the 94 not-run ids run to pass or skip in one pytest process per file | - | TODO | 94 not run plus 3 in filestest |
| 3.6 | Python 2 names and idioms inside conary_test (doc #8): `file()`, `cmp`, `cPickle`, `StringIO`, `xmlrpclib` (cpiostreamtest, artest, systemmodeltest, rpmhelpertest, ...). Mechanical. Accept: pyflakes reports none of these names in conary_test/ | - | TODO | 60; some then fall to 3.4/3.8/3.9 errors |
| 3.7 | sqlite3 connection subclass and dbstore under Python 3 (doc #9): `conary/local/sqldb.py` and the dbstore sqlite driver (`_BEGIN` on a `sqlite3.Connection` subclass, PEP 479 `StopIteration` in generators, `__next__` on `DictAsCsf`, `has_key`). Accept: py3tests for each behaviour; databasetest/sqldbtest failures in this class gone | - | TODO | About 50; gates 3.14 |
| 3.8 | File I/O bytes/str, including magic and javadeps (doc #7): convert signatures in `conary/lib/magic.py` and `javadeps.py` to bytes; `util.write`/`_writeImpl`, `rpmhelper.readSignatureHeader`, logger termios, `cpiostream`, `debhelper`. Accept: the 3 strict xfails in py3tests/test_file_open.py pass (remove the xfail marks); magictest and javadepstest pass | - | TODO | 65 plus the 3 xfails |
| 3.9 | Streams/trove layer: decode values read from StringStream (doc #6): `files.py` freeze/thaw, `trove.py`, `trovetup.fromString`, changelog, `rephelp.createMetadataItem`; `OptionalFlavorStream.diff` returns str. Accept: names/owner/group/changelog are str above the stream layer, wire data bytes; streamstest, trovetest and filestest failures in this class gone | - | TODO | About 90; precedes 3.14 |
| 3.10 | `defaultMacros` pointing at a directory (doc #10): rephelp.setUp includes `archive/site`; `util.loadSourceModule`/`recipe.loadMacros` must handle or skip directories as Py2 `imp.load_source` did. Read the Py2 behaviour first; may be a real bug. Accept: unit test for directory and file entries | - | TODO | 74 (expansiontest, packagepolicytest, destdirpolicytest, ...) |
| 3.11 | Small Python 3 semantics sweep (doc #11): `cml.iterFormat` None vs int compare, `UnboundLocalError` (`util.xmlrpcDump` io, conarycfgtest queue), `re.LOCALE` with str, unhashable `CMTroveSpec`, float indices in `tupleListBsearchInsert`/`TroveInfoMerge`, `isAlive`, `testDecompressStream`, harness kwarg `_returnException`. Accept: a py3tests case per item | - | TODO | About 35 |
| 3.12 | OpenPGP under conary_test (doc #14): `libtest/openpgptest.py` failures (bytes in `openpgpfile.py`, `base64.decodestring`) plus the untested paths listed under Later (signing, keyring cache, `xorStr`). Accept: openpgptest passes or each remaining failure is listed with a reason | - | TODO | 44; needs 3.4, 3.8 |
| 3.13 | Transport and SSL skip behaviour (doc #15): transporttest SSL tests skip without M2Crypto like the others; `xmlrpcDump` UnboundLocalError (if 3.11 did not fix it); `networking.format` bytes. Accept: transporttest has no failures from missing M2Crypto | - | TODO | 4 |
| 3.14 | SQLite-only `sqlharness.start` (doc #12): back repository tests with SQLite in testharness only, no PostgreSQL. Accept: repository-backed tests run past openRepository; a new baseline is recorded and replaces the old skip count | - | TODO | Up to 1585 tests reach real code; expect most to fail first on bytes/str and Py2 recipes. Needs 3.1, 3.2, 3.4, 3.7, 3.8, 3.9. Done together with 3.15 |
| 3.15 | Py2 recipe strings in conary_test (doc #13): 198 of 1018 embedded recipe strings fail `ast.parse` on Python 3. Mechanical conversion of the strings, then runtime fixes. Accept: a py3tests scan finds no embedded recipe string that fails to parse | - | TODO | Ceiling is the cvctest skips (802) plus top-level cook tests. Needs 3.14 |

Deferred (no measured count yet): epdb bytes bugs; sqlite PATHTYPE TEXT (decide after 3.14); nginx/gunicorn/uwsgi/memcache
stand-ins (size after 3.14); M2Crypto (no Fedora 45 package); triage.py harness-gap rule should match only the exception
message (from 2.7 review).

## Later (not yet planned)

- C cleanups (from 1.3 review): LongLongStream_Hash leaks a PyLong; deprecated OpenSSL SHA1_* in digest_uncompress.c; stream rich compare across different types now returns NotImplemented (Py2 raised TypeError).
- sqlite (from 1.5 review): a SELECT that starts with a comment, or WITH/PRAGMA/EXPLAIN, takes BEGIN IMMEDIATE (same as the fork); PATHTYPE is TEXT so non-UTF-8 paths fail on bind; callers passing str to binary() now raise TypeError.
- OpenPGP (from 1.6): untested paths: AES/CAST5/Blowfish secret-key decryption, RIPEMD160/MD5 S2K, v3 signature creation, user attributes, trust graph, merging keys with differing UIDs/subkeys, partial body lengths. UIDs decode with errors='replace', so two non-UTF-8 UIDs can compare equal. parseAsciiArmor now reads the whole stream. sk1-sk7.gpg raise BadSelfSignature (expected per CNY-2047, not asserted). util.py still has pyflakes leftovers (`file`, `cmp`, `xmlrpclib` at ~1350, 1459, 1492, 1784).
- From 1.8: bare `conary --help` / `cvc --help` exit 1 (mainhandler.usage rc=1, upstream). Kept; change only by decision. streams.py compares `diff == '\0'` (str) while diffs may be bytes: always False, same as before.
- From 1.7: epdb client/server bytes bugs (epdb_client.py:64,73; epdb_server.py:70,75-77).
- From 1.7: commitaction now loads only dir/name.py (imp.find_module also found packages and .so). Recipe/policy loading via SourceFileLoader writes __pycache__; build/recipe.py's path+'c' cleanup is a no-op. Non-UTF-8 file dependencies raise UnicodeDecodeError. lib/importer.py is ported but unused and untested.

- Then: install/query/rollback against a local repository, RPM encapsulation proof, build side (rMake replacement), distro decision.
