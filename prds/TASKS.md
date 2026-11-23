# Tasks

Goal: a working Python 3 Conary client. Background and the original scratch-port notes are in
[research/handoff-2026-11-22.md](research/handoff-2026-11-22.md).

Decisions (2026-11-22): Python 3.12+ minimum, Python 2 support dropped, build and test in a Fedora
container (Docker, source bind-mounted), work lands on the `py3` branch. OpenPGP crypto moves from pycrypto to pycryptodomex (2026-11-23).

## Phase 1: Import and version — 8 tasks completed 2026-11-23 (see [TASKS-archive.md](TASKS-archive.md))

## Later (not yet planned)

- bytes/str at the C boundary (from 1.3): pack and streams accept only bytes while the 2to3'd callers and .py fallbacks pass str (e.g. StringStream('abc'), pack.pack('!B...') raise TypeError). dep_freeze was settled in 1.7 (str throughout).
- C cleanups (from 1.3 review): LongLongStream_Hash leaks a PyLong; deprecated OpenSSL SHA1_* in digest_uncompress.c; stream rich compare across different types now returns NotImplemented (Py2 raised TypeError).
- sqlite (from 1.5 review): a SELECT that starts with a comment, or WITH/PRAGMA/EXPLAIN, takes BEGIN IMMEDIATE (same as the fork); PATHTYPE is TEXT so non-UTF-8 paths fail on bind; callers passing str to binary() now raise TypeError.
- OpenPGP (from 1.6): untested paths: AES/CAST5/Blowfish secret-key decryption, RIPEMD160/MD5 S2K, v3 signature creation, user attributes, trust graph, merging keys with differing UIDs/subkeys, partial body lengths. UIDs decode with errors='replace', so two non-UTF-8 UIDs can compare equal. parseAsciiArmor now reads the whole stream. sk1-sk7.gpg raise BadSelfSignature (expected per CNY-2047, not asserted). util.py still has pyflakes leftovers (`file`, `cmp`, `xmlrpclib` at ~1350, 1459, 1492, 1784).
- From 1.8: bare `conary --help` / `cvc --help` exit 1 (mainhandler.usage rc=1, upstream). Kept; change only by decision. streams.py compares `diff == '\0'` (str) while diffs may be bytes: always False, same as before.
- From 1.7: StreamSet subclasses cannot be defined (streams_set.c handles attribute names as bytes: `attribute name must be string, not 'bytes'`), so StreamSet-level behaviour and the str-to-UTF-8 concatStrings path are untested end to end. Streams whose freeze() returns str are encoded at the StreamSet boundary; their thaw side is not audited.
- From 1.7: undefined Py2 names per pyflakes: `file` x58 (e.g. build/packagepolicy.py:323), `cmp` x54 (build/loadrecipe.py:479, build/policy.py:892), `xmlrpclib` x1. epdb client/server bytes bugs (epdb_client.py:64,73; epdb_server.py:70,75-77).
- From 1.7: commitaction now loads only dir/name.py (imp.find_module also found packages and .so). Recipe/policy loading via SourceFileLoader writes __pycache__; build/recipe.py's path+'c' cleanup is a no-op. Non-UTF-8 file dependencies raise UnicodeDecodeError. lib/importer.py is ported but unused and untested.
- Follow-ups from 1.2: convert testsuite.py (repo root, still Py2); recipes embedded as strings in conary_test are Py2; rename the 8 `xxx_todo_changeme` tuple-param placeholders (e.g. conary/repository/changeset.py:979, conary/lib/ext/digest_uncompress.py:32).

- Phase 2 prerequisite: conary_test imports `testrunner` and `testutils` (sassoftware/testutils, not in this repo); fork and port them or replace the harness before triage.
- Phase 2: run `conary_test`, triage failures, bytes/str issues first.
- Then: install/query/rollback against a local repository, RPM encapsulation proof, build side (rMake replacement), distro decision.
