# conary_test baseline (task 2.7)

Measured 2026-11-26 on branch `py3` at `2cfa8b033884f7f2146bc23f3bc019e4c1bbc5b0`
(plus the uncommitted changes listed under "Repository changes"). Nothing under
`conary/`, `conary_test/` or `testharness/` was changed. All numbers come from
JUnit XML written by pytest; tracebacks are `--tb=native`. Re-measure with
`devenv/conary_test_baseline.sh` and `python3 devenv/triage.py <outdir>`.

## Summary

- 2810 tests collect (0 errors). **242 pass, 821 fail, 1653 skip, 94 not run** (crash).
  No xfail in conary_test. 1 test hit the 120 s per-test timeout. No module hit the
  1800 s outer timeout. Wall time 81 min, of which about 79 min is the repository
  skip path (see "Time" below).
- The container on an Apple-silicon host is aarch64. On aarch64, 2303 of 2481 failures
  are one error, `AttributeError: No Such Arch aarch64` in `conary/build/use.py:_setArch`
  (raised from `rephelp.initializeFlavor` in setUp). That run is recorded as Run A
  but is not usable as a baseline. **Run B (linux/amd64 container) is the baseline.**
- In Run B, 2325 of the 2819 failure/error elements are one error: `util.rmtree` calls the
  removed `os.path.walk` in `rephelp.tearDown`. It is a teardown `error` on 1544 skipped and
  454 failed tests, and the only problem (a `failure`) on 327 failed tests; it hides the real
  result of those failed ids. A throwaway one-line patch in an out-of-tree copy (Run C,
  below) shows the real picture: 441 pass, 504 fail, 1766 skip.
- Top 5 classes in Run B by failure/error element count: removed stdlib module/API
  (2341, of which 2325 are the `rmtree` signature), py3 semantics other (110),
  bytes/str: streams/trove (69), bytes/str: hashing (67), bytes/str: file I/O (64).
  Next: py2 code in tests (60), unknown (42), bytes/str: other (35).
- py3tests: 651 passed, 3 xfailed before the Dockerfile change (old image); 651 passed,
  3 xfailed after; 674 passed, 3 xfailed after adding `py3tests/test_triage.py`.
  `devenv/check.sh` passes with the new `pytest-timeout` check. `devenv/compile_check.sh`:
  476 files, 0 failures.

## Command

Runner (committed as `devenv/conary_test_baseline.sh`; one pytest process per test
file, whole loop inside one container start). Build step first:

```
devenv/run sh -c 'make -C conary/lib/ext && make -C conary_test' </dev/null
devenv/conary_test_baseline.sh tmp/baseline          # writes tmp/baseline/*.xml, *.log, rc.txt, crashed.txt, env.txt
python3 devenv/triage.py tmp/baseline                # classes, top signatures, skips (Markdown on stdout)
```

Loop body (verbatim from the script):

```
#!/bin/bash
# Baseline run of conary_test: one pytest process per test file, bounded by
# an outer timeout, JUnit XML per file in <outdir> (default tmp/baseline,
# gitignored). A file whose process dies without writing XML (segfault,
# outer timeout, test that removes the cwd) is re-run one test id per process
# so the survivors are still measured; ids that die are recorded in crashed.txt.
# Usage: devenv/conary_test_baseline.sh [outdir]   (run on the host)
set -u
cd "$(dirname "$0")/.."
OUT=${1:-tmp/baseline}
mkdir -p "$OUT"
rm -f "$OUT"/*.xml "$OUT"/*.log "$OUT"/rc.txt "$OUT"/crashed.txt
exec devenv/run bash -c '
OUT=/src/'"$OUT"'
cd /src
{ date -u +%FT%TZ; python3 -VV; git rev-parse HEAD; uname -m; id -u; } > $OUT/env.txt 2>&1
run() { # run <name> <timeout> <pytest target...>
  local n=$1 t=$2; shift 2
  (cd /src && timeout -k 10 $t python3 -m pytest "$@" -p no:cacheprovider -q -rA --tb=native \
      --timeout=120 --timeout-method=signal --junitxml=$OUT/$n.xml </dev/null > $OUT/$n.log 2>&1)
}
python3 -m pytest conary_test --collect-only -q -p no:cacheprovider </dev/null > $OUT/collect.txt 2>&1
for f in $(grep "::" $OUT/collect.txt | cut -d: -f1 | sort -u); do
  n=$(echo $f | tr / _ | sed "s/\.py$//")
  start=$(date +%s)
  run $n 1800 $f
  rc=$?
  echo "$f rc=$rc secs=$(( $(date +%s) - start ))" >> $OUT/rc.txt
  if [ ! -f $OUT/$n.xml ]; then
    i=0
    for id in $(grep "^$f::" $OUT/collect.txt); do
      i=$((i+1))
      run ${n}__$i 300 $id
      irc=$?
      [ -f $OUT/${n}__$i.xml ] || echo "$id rc=$irc" >> $OUT/crashed.txt
    done
  fi
done
echo DONE >> $OUT/rc.txt
'
```

Per-test flags: `-p no:cacheprovider -q -rA --tb=native --timeout=120 --timeout-method=signal
--junitxml=...`, stdin from /dev/null, outer `timeout -k 10 1800` per file. A file whose
process dies without XML is re-run one test id per process (`timeout 300`); ids that still
die are listed in `crashed.txt` and counted "not run".

Run B needs an amd64 image. `devenv/run` has no platform switch and the image tag is the
Dockerfile hash, so Run B used a copy of the tree (`conary-amd64/`, outside the repo, without
`.git`, with a comment appended to its Dockerfile to get a separate tag) and
`DOCKER_DEFAULT_PLATFORM=linux/amd64`, then `make -C conary/lib` (builds `elf.so`) plus the
usual build step. Phase 3 task 2 makes this a first-class option.

## Environment

| | Run A (native) | Run B (baseline) | Run C (supplementary) |
|---|---|---|---|
| Date (UTC) | 2026-11-26 10:23 | 2026-11-26 10:32 to about 11:55 | same day, after B |
| Python | 3.15.2 (fc45.aarch64, GCC 16.2.1) | 3.15.2 (fc45.x86_64) | as B |
| Container | `conary-devenv:c92117fb07d8` | `conary-devenv:8575967ac67b` (amd64 copy) | as B |
| Host | Docker Desktop on macOS, arm64 | same, amd64 emulation | same |
| uid in container | 0 (devenv/run only passes `--user` on Linux) | 0 | 0 |
| Git HEAD | 2cfa8b033884 | same tree (copy has no .git) | same, util.rmtree patched in the copy only |
| pytest | 9.1.1, pytest-timeout installed | same | same |

Python is 3.15, so 3.12-only behaviour is not covered. Running as root probably changes some
results (`testDoNotCookAsRoot`, `testUnreadableEntitlementsDirectory` assume non-root);
not verified. Tools present: xz, bzip2, perl, tar, gzip, zstd, file, diff. Absent on purpose:
cpio, rpmbuild, patch, unzip, lzma (not installed in this task; see Phase 3 task 2). `python`
(no `python3` suffix) is also absent.

Runs:

- **Run A**: `tmp/baseline` in the repo (aarch64). 2805 ids reported, 5 not run. 2481 failed,
  242 passed, 82 skipped.
- **Run B**: `tmp/baseline-amd64` (gitignored). Everything below unless stated.
- **Run C**: `tmp/rmfix-amd64`. The 78 modules that contained a `util.rmtree` failure, re-run
  with `os.path.walk(path, _permsVisit, None)` replaced by an `os.walk` loop in the throwaway copy.
  Not a fix; it measures what the teardown error hides.

## Totals (Run B)

| | count |
|---|---|
| collected (re-measured; matches the 2810 in the 2.4 notes) | 2810 |
| passed | 242 |
| failed (primary outcome) | 821 |
| skipped (primary outcome) | 1653 |
| xfail | 0 |
| errors | 0 as a primary outcome (see note) |
| timeouts | 1 (`libtest/utiltest.py::UtilTest::testLazyFileCache`, 120 s) |
| not run | 94 |
| reported | 2716 (= 242 + 821 + 1653) |
| collected = reported + not run | 2810 = 2716 + 94 |

Reading the counts:

- unittest `tearDown` failures are reported by pytest as failures, and a skip followed by a
  teardown error is one `skipped` entry plus one `error` entry. Problem elements: 821 `failure`
  and 1998 `error` (sum 2819). The 1998 errors all belong to ids whose primary outcome is
  skipped (1544) or failed (454). The class table counts elements, so it sums to 2819, not 821.
  Ids are counted once by primary outcome (failed > skipped > error > passed). 454 ids appear
  twice in the XML for this reason.
- Not run (94): all are segfaults or interpreter crashes, no outer timeouts.
  - 91 ids in 11 modules segfault in `conary_test/__init__.py:requireChroot` (likely cause: ctypes `libcap`
    calls without `restype`/`argtypes` so the pointer is truncated, then `'cap_sys_chroot' in cap`
    compares str to bytes; the `@rpm` decorator calls it):
    capsuletest 34, cookrpmcapsuletest 23, capsulepolicytest 21, derivedcapsuletest 4,
    scripttest/rpmtest 2, repairtest 2, plus 1 each in changesettest, cvctest/clonetest,
    cvctest/buildtest/derivedtest, localtest/updatetest, prelinktest.
  - 3 ids in `filestest.py` (`testBlock`, `testChar`, `testSymbolicLink`) leave the process in a
    deleted cwd; pytest then dies writing its report (`FileNotFoundError: '/src'`), so they
    never produce XML even alone.
  - No stray `defunct` processes remained afterwards; no duplicate ids across files.

## Per-subpackage totals (Run B)

| subpackage | collected | passed | failed | skipped | not run |
|---|---|---|---|---|---|
| cvctest | 1132 | 5 | 275 | 802 | 50 |
| top-level | 782 | 93 | 207 | 441 | 41 |
| libtest | 275 | 90 | 180 | 5 | 0 |
| clienttest | 246 | 7 | 54 | 185 | 0 |
| repositorytest | 216 | 3 | 48 | 165 | 0 |
| localtest | 90 | 9 | 47 | 33 | 1 |
| depstest | 37 | 35 | 2 | 0 | 0 |
| scripttest | 32 | 0 | 8 | 22 | 2 |
| TOTAL | 2810 | 242 | 821 | 1653 | 94 |

## Per-module totals (Run B)

`rc` is the pytest exit code of the module run (139 = segfault, re-run per id); `secs` is wall time.

| module | collected | passed | failed | skipped | not run | rc | secs |
|---|---|---|---|---|---|---|---|
| acltest.py | 35 | 0 | 3 | 32 | 0 | 1 | 99 |
| callbackstest.py | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| capsuletest.py | 34 | 0 | 0 | 0 | 34 | 139 | 1 |
| changelogtest.py | 1 | 0 | 1 | 0 | 0 | 1 | 0 |
| changesettest.py | 15 | 0 | 4 | 10 | 1 | 139 | 23 |
| clienttest/cmdlinetest.py | 2 | 0 | 2 | 0 | 0 | 1 | 1 |
| clienttest/cmltest.py | 28 | 0 | 28 | 0 | 0 | 1 | 2 |
| clienttest/conaryclienttest.py | 20 | 0 | 8 | 12 | 0 | 1 | 38 |
| clienttest/filetypestest.py | 12 | 7 | 5 | 0 | 0 | 1 | 1 |
| clienttest/modelupdatetest.py | 28 | 0 | 1 | 27 | 0 | 1 | 83 |
| clienttest/passwordtest.py | 1 | 0 | 1 | 0 | 0 | 1 | 1 |
| clienttest/resolvetest.py | 19 | 0 | 0 | 19 | 0 | 1 | 56 |
| clienttest/systemmodeltest.py | 6 | 0 | 6 | 0 | 0 | 1 | 2 |
| clienttest/updatetest.py | 130 | 0 | 3 | 127 | 0 | 1 | 383 |
| cmdlinetest.py | 61 | 0 | 57 | 4 | 0 | 1 | 11 |
| conarycfgtest.py | 36 | 8 | 26 | 2 | 0 | 1 | 2 |
| cvctest/buildtest/buildinfotest.py | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| cvctest/buildtest/buildpackagetest.py | 1 | 0 | 1 | 0 | 0 | 1 | 1 |
| cvctest/buildtest/buildtest.py | 61 | 0 | 15 | 46 | 0 | 1 | 127 |
| cvctest/buildtest/capsulepolicytest.py | 21 | 0 | 0 | 0 | 21 | 139 | 1 |
| cvctest/buildtest/cookmsicapsuletest.py | 1 | 0 | 0 | 1 | 0 | 1 | 4 |
| cvctest/buildtest/cookrpmcapsuletest.py | 26 | 0 | 0 | 3 | 23 | 139 | 11 |
| cvctest/buildtest/cooktest.py | 63 | 0 | 5 | 58 | 0 | 1 | 177 |
| cvctest/buildtest/cookwimcapsuletest.py | 1 | 0 | 0 | 1 | 0 | 1 | 4 |
| cvctest/buildtest/crosscompiletest.py | 3 | 0 | 1 | 2 | 0 | 1 | 7 |
| cvctest/buildtest/derivedcapsuletest.py | 4 | 0 | 0 | 0 | 4 | 139 | 2 |
| cvctest/buildtest/derivedtest.py | 34 | 0 | 1 | 32 | 1 | 139 | 101 |
| cvctest/buildtest/destdirpolicytest.py | 56 | 0 | 33 | 23 | 0 | 1 | 63 |
| cvctest/buildtest/expansiontest.py | 24 | 0 | 20 | 4 | 0 | 1 | 14 |
| cvctest/buildtest/explaintest.py | 17 | 0 | 17 | 0 | 0 | 1 | 1 |
| cvctest/buildtest/factorytest.py | 13 | 0 | 1 | 12 | 0 | 1 | 41 |
| cvctest/buildtest/filesettest.py | 4 | 0 | 0 | 4 | 0 | 1 | 13 |
| cvctest/buildtest/grouppolicytest.py | 26 | 0 | 3 | 23 | 0 | 1 | 72 |
| cvctest/buildtest/grouprecipetest.py | 3 | 0 | 3 | 0 | 0 | 1 | 1 |
| cvctest/buildtest/groupsettest.py | 31 | 0 | 0 | 31 | 0 | 1 | 95 |
| cvctest/buildtest/grouptest.py | 117 | 0 | 2 | 115 | 0 | 1 | 350 |
| cvctest/buildtest/loadrecipetest.py | 20 | 0 | 1 | 19 | 0 | 1 | 60 |
| cvctest/buildtest/lookasidetest.py | 11 | 0 | 5 | 6 | 0 | 1 | 18 |
| cvctest/buildtest/macrostest.py | 5 | 0 | 5 | 0 | 0 | 1 | 2 |
| cvctest/buildtest/manifesttest.py | 34 | 0 | 25 | 9 | 0 | 1 | 31 |
| cvctest/buildtest/nextversiontest.py | 5 | 0 | 0 | 5 | 0 | 1 | 17 |
| cvctest/buildtest/packagepolicytest.py | 209 | 0 | 60 | 149 | 0 | 1 | 434 |
| cvctest/buildtest/packagerecipetest.py | 16 | 0 | 0 | 16 | 0 | 1 | 50 |
| cvctest/buildtest/policytest.py | 1 | 0 | 1 | 0 | 0 | 1 | 2 |
| cvctest/buildtest/sourcetest.py | 54 | 0 | 26 | 28 | 0 | 1 | 85 |
| cvctest/buildtest/testcomptest.py | 7 | 0 | 7 | 0 | 0 | 1 | 1 |
| cvctest/buildtest/usetest.py | 9 | 0 | 9 | 0 | 0 | 1 | 2 |
| cvctest/buildtest/windowsactiontest.py | 6 | 0 | 0 | 6 | 0 | 1 | 14 |
| cvctest/clonetest.py | 70 | 0 | 5 | 64 | 1 | 139 | 20 |
| cvctest/derivetest.py | 1 | 0 | 0 | 1 | 0 | 1 | 4 |
| cvctest/newtrovetest.py | 17 | 0 | 3 | 14 | 0 | 1 | 44 |
| cvctest/recipetest.py | 10 | 3 | 3 | 4 | 0 | 1 | 14 |
| cvctest/shadowtest.py | 30 | 0 | 0 | 30 | 0 | 1 | 93 |
| cvctest/sigtest.py | 34 | 0 | 4 | 30 | 0 | 1 | 93 |
| cvctest/sourcetest.py | 66 | 0 | 9 | 57 | 0 | 1 | 184 |
| cvctest/usergrouptest.py | 14 | 0 | 7 | 7 | 0 | 1 | 23 |
| cvctest/vercontroltest.py | 5 | 0 | 3 | 2 | 0 | 1 | 7 |
| dbstoretest.py | 31 | 4 | 1 | 26 | 0 | 1 | 1 |
| depstest/archtest.py | 3 | 3 | 0 | 0 | 0 | 0 | 1 |
| depstest/depstest.py | 34 | 32 | 2 | 0 | 0 | 1 | 1 |
| deptest.py | 27 | 0 | 1 | 26 | 0 | 1 | 81 |
| dirstest.py | 2 | 0 | 0 | 2 | 0 | 0 | 8 |
| displaytest.py | 17 | 0 | 2 | 15 | 0 | 1 | 48 |
| entitlementtest.py | 1 | 0 | 0 | 1 | 0 | 1 | 4 |
| enumtest.py | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| filestest.py | 16 | 1 | 12 | 0 | 3 | 1 | 2 |
| flavorcfgtest.py | 2 | 0 | 2 | 0 | 0 | 1 | 2 |
| flavortest.py | 7 | 0 | 0 | 7 | 0 | 1 | 23 |
| harnesstest.py | 1 | 0 | 0 | 1 | 0 | 1 | 6 |
| integritytest.py | 5 | 0 | 3 | 2 | 0 | 1 | 9 |
| journaltest.py | 10 | 0 | 0 | 10 | 0 | 1 | 32 |
| libtest/apitest.py | 1 | 0 | 1 | 0 | 0 | 1 | 2 |
| libtest/artest.py | 6 | 0 | 6 | 0 | 0 | 1 | 2 |
| libtest/cfgtest.py | 27 | 24 | 3 | 0 | 0 | 1 | 2 |
| libtest/copytest.py | 1 | 0 | 1 | 0 | 0 | 1 | 1 |
| libtest/cpiostreamtest.py | 7 | 0 | 7 | 0 | 0 | 1 | 1 |
| libtest/debhelpertest.py | 2 | 0 | 2 | 0 | 0 | 1 | 0 |
| libtest/dirsettest.py | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| libtest/elftest.py | 4 | 2 | 2 | 0 | 0 | 1 | 2 |
| libtest/fixeddifflibtest.py | 2 | 0 | 2 | 0 | 0 | 1 | 2 |
| libtest/formattracetest.py | 1 | 0 | 1 | 0 | 0 | 1 | 1 |
| libtest/graphtest.py | 8 | 7 | 1 | 0 | 0 | 1 | 1 |
| libtest/httptest/openertest.py | 3 | 0 | 3 | 0 | 0 | 1 | 0 |
| libtest/httptest/proxymaptest.py | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| libtest/httptest/requesttest.py | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| libtest/javadepstest.py | 2 | 1 | 1 | 0 | 0 | 1 | 2 |
| libtest/loggertest.py | 24 | 17 | 7 | 0 | 0 | 1 | 1 |
| libtest/logparsetest.py | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| libtest/magictest.py | 19 | 0 | 19 | 0 | 0 | 1 | 3 |
| libtest/misctest.py | 2 | 0 | 2 | 0 | 0 | 1 | 1 |
| libtest/networkingtest.py | 1 | 0 | 1 | 0 | 0 | 1 | 1 |
| libtest/openpgptest.py | 88 | 0 | 83 | 5 | 0 | 1 | 14 |
| libtest/optiontest.py | 5 | 5 | 0 | 0 | 0 | 0 | 1 |
| libtest/pydepstest.py | 1 | 1 | 0 | 0 | 0 | 0 | 2 |
| libtest/utiltest.py | 49 | 16 | 33 | 0 | 0 | 1 | 121 |
| libtest/xmllogtest.py | 14 | 9 | 5 | 0 | 0 | 1 | 1 |
| localcstest.py | 3 | 0 | 0 | 3 | 0 | 1 | 8 |
| localtest/databasetest.py | 19 | 8 | 11 | 0 | 0 | 1 | 1 |
| localtest/deptabletest.py | 9 | 0 | 9 | 0 | 0 | 1 | 2 |
| localtest/errorstest.py | 1 | 0 | 1 | 0 | 0 | 1 | 2 |
| localtest/idtabletest.py | 5 | 0 | 0 | 5 | 0 | 0 | 1 |
| localtest/rpmcapsuletest.py | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| localtest/sqldbtest.py | 20 | 0 | 18 | 2 | 0 | 1 | 8 |
| localtest/troveinfotest.py | 1 | 0 | 1 | 0 | 0 | 1 | 2 |
| localtest/updatetest.py | 34 | 0 | 7 | 26 | 1 | 139 | 76 |
| logtest.py | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| metadatatest.py | 3 | 0 | 0 | 3 | 0 | 0 | 12 |
| multirepostest.py | 12 | 0 | 2 | 10 | 0 | 1 | 37 |
| optionstest.py | 5 | 0 | 5 | 0 | 0 | 1 | 3 |
| patchtest.py | 16 | 16 | 0 | 0 | 0 | 0 | 4 |
| prelinktest.py | 1 | 0 | 0 | 0 | 1 | 139 | 2 |
| queryreptest.py | 22 | 0 | 2 | 20 | 0 | 1 | 60 |
| querytest.py | 3 | 0 | 0 | 3 | 0 | 1 | 11 |
| redirecttest.py | 23 | 0 | 0 | 23 | 0 | 1 | 73 |
| removetest.py | 7 | 0 | 0 | 7 | 0 | 1 | 23 |
| repairtest.py | 5 | 0 | 0 | 3 | 2 | 139 | 11 |
| repositorytest/calllogtest.py | 2 | 0 | 2 | 0 | 0 | 1 | 3 |
| repositorytest/changesettest.py | 8 | 0 | 6 | 2 | 0 | 1 | 9 |
| repositorytest/datastoretest.py | 6 | 1 | 5 | 0 | 0 | 1 | 3 |
| repositorytest/errorstest.py | 7 | 0 | 4 | 3 | 0 | 1 | 12 |
| repositorytest/filecontainertest.py | 2 | 0 | 2 | 0 | 0 | 1 | 1 |
| repositorytest/filecontentstest.py | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| repositorytest/findtrovetest.py | 29 | 0 | 2 | 27 | 0 | 1 | 75 |
| repositorytest/netclienttest.py | 44 | 0 | 5 | 39 | 0 | 1 | 121 |
| repositorytest/netrepostest/changelogtest.py | 1 | 0 | 0 | 1 | 0 | 0 | 2 |
| repositorytest/netrepostest/geoiptest.py | 2 | 1 | 1 | 0 | 0 | 1 | 1 |
| repositorytest/netrepostest/instancestest.py | 1 | 0 | 0 | 1 | 0 | 0 | 2 |
| repositorytest/netrepostest/netauthtest.py | 14 | 0 | 0 | 14 | 0 | 1 | 6 |
| repositorytest/netrepostest/netservertest.py | 37 | 0 | 5 | 32 | 0 | 1 | 97 |
| repositorytest/netrepostest/proxytest.py | 6 | 0 | 4 | 2 | 0 | 1 | 6 |
| repositorytest/netrepostest/reposlogtest.py | 3 | 0 | 3 | 0 | 0 | 1 | 2 |
| repositorytest/netrepostest/trovestoretest.py | 17 | 0 | 0 | 17 | 0 | 1 | 11 |
| repositorytest/netrepostest/versionopstest.py | 4 | 0 | 0 | 4 | 0 | 0 | 2 |
| repositorytest/searchsourcetest.py | 6 | 0 | 0 | 6 | 0 | 1 | 21 |
| repositorytest/transporttest.py | 14 | 0 | 4 | 10 | 0 | 1 | 21 |
| repositorytest/trovesourcetest.py | 12 | 0 | 5 | 7 | 0 | 1 | 24 |
| rollbacktest.py | 30 | 0 | 4 | 26 | 0 | 1 | 81 |
| rpmhelpertest.py | 12 | 1 | 11 | 0 | 0 | 1 | 1 |
| scripttest/ccs2tartest.py | 1 | 0 | 1 | 0 | 0 | 1 | 2 |
| scripttest/changemailtest.py | 1 | 0 | 1 | 0 | 0 | 1 | 1 |
| scripttest/mirrortest.py | 19 | 0 | 0 | 19 | 0 | 0 | 60 |
| scripttest/rpmtest.py | 11 | 0 | 6 | 3 | 2 | 139 | 1 |
| servertest.py | 4 | 0 | 0 | 4 | 0 | 1 | 5 |
| sharedfiletest.py | 7 | 0 | 0 | 7 | 0 | 1 | 23 |
| shimtest.py | 4 | 0 | 0 | 4 | 0 | 1 | 14 |
| showchangesettest.py | 7 | 0 | 0 | 7 | 0 | 1 | 23 |
| streamstest.py | 23 | 5 | 18 | 0 | 0 | 1 | 1 |
| tagtest.py | 9 | 0 | 0 | 9 | 0 | 1 | 29 |
| testhelptest.py | 8 | 8 | 0 | 0 | 0 | 0 | 1 |
| trovetest.py | 41 | 10 | 31 | 0 | 0 | 1 | 3 |
| trovetuptest.py | 9 | 6 | 3 | 0 | 0 | 1 | 1 |
| updatecmdtest.py | 46 | 6 | 9 | 31 | 0 | 1 | 100 |
| updatetest.py | 125 | 0 | 3 | 122 | 0 | 1 | 370 |
| verifytest.py | 8 | 0 | 0 | 8 | 0 | 1 | 26 |
| versionstest.py | 21 | 20 | 1 | 0 | 0 | 1 | 1 |
| webfieldstest.py | 6 | 0 | 6 | 0 | 0 | 1 | 2 |
| webtest.py | 13 | 0 | 0 | 13 | 0 | 0 | 2 |

## Classes (Run B, unpatched)

Rules were applied in the order given; first match wins, so each of the 2819 failure/error
elements is in exactly one class (`devenv/triage.py`, function `classify`). Signature =
final exception type plus the innermost frame under `/src/conary/`, falling back to
`conary_test/` then `testharness/`; the tag in brackets shows which. Class matching also
looks at the whole text (chained causes) for removed-API messages, and at captured
stdout/stderr. The unit test `py3tests/test_triage.py` pins the rules.

| class | elements | share |
|---|---|---|
| removed stdlib module/API | 2341 | 83.1% |
| py3 semantics: other | 110 | 3.9% |
| bytes/str: streams/trove | 69 | 2.4% |
| bytes/str: hashing | 67 | 2.4% |
| bytes/str: file I/O | 64 | 2.3% |
| py2 code in tests | 60 | 2.1% |
| unknown | 42 | 1.5% |
| bytes/str: other | 35 | 1.2% |
| iterator/dict-view | 10 | 0.4% |
| harness gap | 9 | 0.3% |
| sort/compare | 6 | 0.2% |
| bytes/str: network/xmlrpc | 2 | 0.1% |
| integer division | 2 | 0.1% |
| missing binary | 1 | 0.0% |
| timeout | 1 | 0.0% |
| unsupported arch | 0 (2303 in Run A) | |
| real bug | 0 (needs manual reading; none claimed) | |
| **total** | **2819** | |

`py3 semantics: other` and `timeout` and `unsupported arch` are classes added to the required
list. "Real bug" stays empty: nothing was confirmed as a non-porting bug. 42 unknown is 1.5%
of all elements and 8.5% of the 494 elements that are not the `rmtree` signature, under the
10% target. Unknown are single assertion failures in `cmdlinetest`, `cmltest`, `conarycfgtest`,
`cooktest`, `magictest`/`openpgptest` tails, `utiltest` and similar; most need the real repository
or a subprocess to read properly.

Examples (test id, one-line error):

- **removed stdlib module/API** (2341):
  - `acltest.AclTest::testAclChanges` (teardown, skipped test): `AttributeError: module 'posixpath' has no attribute 'walk'`
  - `cvctest.buildtest.destdirpolicytest...::testNormalizePythonInterpreterVersionNoConfig`: `ModuleNotFoundError: No module named 'normalize'`
  - `cvctest.recipetest.RecipeTest::testNoClass` (chained cause): `module 'types' has no attribute 'UnboundMethodType'` (conary/build/loadrecipe.py:_copyReusedRecipes)
- **py3 semantics: other** (110):
  - `cvctest.buildtest.expansiontest.PackageRecipeTest::testExpandGlobsWithDirs`: `IsADirectoryError: '/src/conary_test/archive/site'` (loadSourceModule over a directory in `cfg.defaultMacros`; 73 tests)
  - `localtest.databasetest.Database::testDbTimeout`: `'sqlite3.Connection' object has no attribute '_BEGIN' and no __dict__ for setting new attributes` (conary/local/sqldb.py; 29)
  - `clienttest.cmltest.CMTest::testRefreshVersionSnapshots`: `cannot use 'CMTroveSpec' as a set element (unhashable type)`
- **bytes/str: streams/trove** (69):
  - `clienttest.filetypestest.ClientNewTroveTest::testPathIdParam`: `can only concatenate str (not "bytes") to str` (conary/files.py:freeze; 15)
  - `cvctest.buildtest.cooktest.MultipleMainPackageTest::testCookPromotesMetadata`: `assert(type(val) is bytes)` (conary/streams.py:set)
  - `repositorytest.datastoretest...::testAddFile`: `AttributeError` in `datastoretest.addFile` on a bytes digest
- **bytes/str: hashing** (67):
  - `acltest.AclTest::testEntitlementAutoRetry`: `Strings must be encoded before hashing` (conary/lib/util.py:getId; 51)
  - `filestest.FilesTest::testContentsChanged`: same, `conary/lib/sha1helper.py:sha1String` (6)
  - `cvctest.sigtest.SigTest::testFileUpdateMissingKey`: same, `sha1helper.md5String`
- **bytes/str: file I/O** (64):
  - `integritytest.IntegrityTest::testFileContentsMissing`: `a bytes-like object is required, not 'str'`
  - `libtest.magictest.MagicTest::testTarArchives`: `'NoneType' object has no attribute 'name'` (magic() returns None; signatures are bytes vs str; 19 tests in the module)
  - `rpmhelpertest...`: `UnicodeDecodeError` in `conary/rpmhelper.py:readSignatureHeader` (5)
  - `libtest.loggertest.WritersTest::testSubscriptionLog`: `tcsetattr: elements of attributes must be bytes objects` (conary/lib/logger.py)
- **py2 code in tests** (60):
  - `clienttest.systemmodeltest.SystemModelFileTest::testInit`: `NameError: name 'file' is not defined`
  - `libtest.cpiostreamtest.CpioStreamTest::testIterate`: `NameError: name 'file'` (`_createCpio`; 7)
  - `libtest.cfgtest.ConfigTest::testPickle`: `NameError: name 'cPickle'`
- **unknown** (42):
  - `clienttest.cmltest.CMLTest::testParseFail`: `AssertionError: 'None' != '/foo:1: Unrecognized command "badverb"'`
  - `cmdlinetest.CmdLineTest::testBuildLogError`: `assert '' == 'Error: can n...specify one'`
  - `libtest.utiltest.UtilTest::testCountOpenFileDescriptors`: `AssertionError: N != N`
- **bytes/str: other** (35):
  - `clienttest.filetypestest...::testLinkGroup`: `AssertionError: b'12345' != '12345'`
  - `changesettest.ChangeSetTest::testReset`: `write() argument must be str, not bytes`
  - `libtest.networkingtest.NetworkingTest::testPickling`: `sequence item 0: expected str instance, bytes found` (conary/lib/networking.py:format)
- **iterator/dict-view** (10):
  - `changesettest.ChangeSetTest::testConfigFileMerges`: `'DictAsCsf' object has no attribute '__next__'` (conary/repository/changeset.py:getNextFile)
  - `dbstoretest.DBStoreCodeTest::testCaselessDict`: `type object 'dict' has no attribute 'has_key'`
  - `libtest.utiltest.UtilTest::testPeekIterator`: `RuntimeError: generator raised StopIteration` (PEP 479)
- **harness gap** (9):
  - `cvctest.buildtest.sourcetest.SourceTest::testAddBadPatch`: `RepositoryHelper.buildRecipe() got an unexpected keyword argument '_returnException'`
  - `cvctest.buildtest.factorytest.FactoryTest::testFactoryNames`: an `AssertionError` whose message is the sqlharness skip text (skip swallowed by a broad `except`)
  - `filestest.FilesTest::testSocket`: `'FilesTest' object has no attribute 'owner'`
- **sort/compare** (6): `clienttest.cmltest.CMLTest::testParseWrite`: `'>' not supported between 'NoneType' and 'int'` (conary/conaryclient/cml.py:iterFormat)
- **bytes/str: network/xmlrpc** (2): `cvctest.buildtest.lookasidetest.LookAsideTest::testAuth`; `repositorytest.netrepostest.proxytest.ProxyTest::testInjectedEntitlementsNonSSL`: `a bytes-like object is required, not 'str'`
- **integer division** (2): `libtest.utiltest.UtilTest::testTupleListBsearchInsert`: `list indices must be integers or slices, not float`; `trovetest.TroveTest::testTroveInfoMerge`: `can't multiply sequence by non-int of type 'float'`
- **missing binary** (1): `cmdlinetest.CmdLineTest::testCvcImportNoSysArgv`: `FileNotFoundError: 'python'`
- **timeout** (1): `libtest.utiltest.UtilTest::testLazyFileCache`: pytest-timeout after 120 s in `util.countOpenFileDescriptors`

The missing-binary class is nearly empty only because the tests that need cpio, rpmbuild, patch,
unzip or lzma are hidden behind the sqlharness skip or the `requireChroot` crash; it will fill
once those open up (the recipe `patch`, RPM capsule and `unzip` tests).

## Top 15 signatures (Run B, any class)

| # | count | signature | class |
|---|---|---|---|
| 1 | 2325 | `AttributeError @ conary/lib/util.py:rmtree` (`os.path.walk` gone) | removed stdlib module/API |
| 2 | 73 | `IsADirectoryError @ conary/lib/util.py:loadSourceModule` (`archive/site` dir) | py3 semantics |
| 3 | 51 | `TypeError @ conary/lib/util.py:getId` (str to hashlib) | bytes/str: hashing |
| 4 | 29 | `AttributeError @ conary/local/sqldb.py:__init__` (`sqlite3.Connection._BEGIN`) | py3 semantics |
| 5 | 15 | `TypeError @ conary/files.py:freeze` (str + bytes) | bytes/str: streams/trove |
| 6 | 7 | `TypeError @ conary/lib/util.py:write` | bytes/str: file I/O |
| 7 | 7 | `NameError @ conary_test/libtest/cpiostreamtest.py:_createCpio` (`file`) | py2 code in tests |
| 8 | 6 | `TypeError @ conary/conaryclient/cml.py:iterFormat` (None vs int) | sort/compare |
| 9 | 6 | `TypeError @ conary/lib/util.py:copyfileobj` (hashing) | bytes/str: hashing |
| 10 | 6 | `TypeError @ conary/lib/sha1helper.py:sha1String` | bytes/str: hashing |
| 11 | 6 | `NameError @ conary_test/libtest/artest.py:getArchiveFile` | py2 code in tests |
| 12 | 5 | `AttributeError @ conary_test/repositorytest/datastoretest.py:addFile` | bytes/str: streams/trove |
| 13 | 5 | `UnicodeDecodeError @ conary/rpmhelper.py:readSignatureHeader` | bytes/str: file I/O |
| 14 | 4 | `TypeError @ conary/lib/networking.py:format` | bytes/str: other |
| 15 | 4 | `AssertionError @ conary/streams.py:set` (`type(val) is bytes`) | bytes/str: streams/trove |

Signature 1 is 82.5% of all elements, so the 5% split rule applies. It is one cause (`rmtree`,
called from `rephelp.resetWork` in `tearDown`), split by element kind: 1544 teardown errors on
skipped tests, 454 teardown errors on failed tests (these also have a second element or a
failure elsewhere), 327 plain failures where it is the only problem. Signature 2 (73) and 3 (51) are each over 1.5% and are single causes: 73 tests share one
fixture path (`rephelp.setUp` `defaultMacros` includes the `archive/site` directory) and 51 call
`util.getId` with a str.

## Layer behind the teardown error (Run C, supplementary)

Run C re-ran the 78 modules with an `rmtree` failure, with the one-line `os.walk` patch applied
in the throwaway copy. The 646 ids that had an `rmtree` element and failed in Run B became:
**199 pass, 113 skip, 334 still fail** (for the reasons in the class table). Merging Run C over
Run B (modules not re-run keep their Run B result with the `rmtree` element on skipped ids
removed) gives the real picture:

| | passed | failed | skipped | unresolved |
|---|---|---|---|---|
| merged | 441 | 504 | 1766 | 5 |

Failure/error elements by class (504): py3 semantics 111, bytes/str total 241
(streams/trove 69, hashing 68, file I/O 65, other 37, network 2), py2 code in tests 60,
unknown 47, removed stdlib 16, iterator/dict-view 10, harness gap 9, sort/compare 6,
integer division 2, missing binary 1, timeout 1. The new top signatures are
`IsADirectoryError loadSourceModule` (74), `getId` (51), `sqldb.__init__` (29),
`files.freeze` (15). Worst modules after the patch: openpgptest 44, cmdlinetest 30,
utiltest 26, trovetest 26, manifesttest 24, expansiontest 20, sourcetest 18,
streamstest 18, sqldbtest 17, magictest 15. "Unresolved" are five ids that failed only
in a per-id re-run of a crashed module and were not in Run C.

## Skips (Run B, primary outcome skipped, 1653)

| reason | count |
|---|---|
| sqlharness (`sqlharness: repository database harness not rebuilt yet`) | 1585 |
| other: webunit missing (13), requires system conary database (9), squid (3), CNY-525 (3), requires networking (2), ... | 60 |
| binary/module not installed: unlzma 2, cpio 2, desktop-file-utils 1, lzop 1 | 6 |
| server stand-ins (nginx/gunicorn/uwsgi/memcache: `memcache_server: web server harness not rebuilt`) | 1 |
| M2Crypto is not installed | 1 |

Of the 1653 skips, 1544 also carry the `rmtree` teardown error (sum of skips plus errors on one id).
After Run C, skips grow to 1766 (sqlharness 1698) because 113 tests that failed only in teardown
now skip cleanly.

**SQLite-only sqlharness estimate:** 1585 tests in Run B, 1698 after the `rmtree` fix, are the
ceiling on what a SQLite-only `sqlharness.start` could open. This is an upper bound on tests
that *run past `openRepository`*, not on tests that will pass: they have never executed past the
repository setup, so most will turn into bytes/str failures (streams/trove, hashing, file I/O) and Py2
recipe-string failures first. Skips by subpackage: `cvctest` 802, top-level 441, `clienttest` 185,
`repositorytest` 165. Plan on a small single-digit-percent pass rate on the first
run, not 1585. Nothing was raised in this task to test that; it is an estimate from skip counts.

## Not run, timeouts, time

- Not run (94): see "Totals". Crash modules recorded in `crashed.txt`. No outer timeout fired.
- Per-test timeout: 1 (`testLazyFileCache`, 120 s, `signal` method worked).
- Time: sum of module wall times 4870 s (81 min). `rephelp.openRepository` wraps the
  skip in a bare `except:` with 4 retries and 0.5/1.0/1.5 s sleeps, so each of the ~1585
  repository-backed tests costs about 3 s before it skips: about 79 min of the 81. The
  slowest modules are `packagepolicytest` 434 s, `clienttest/updatetest` 383 s, `updatetest` 370 s,
  `grouptest` 350 s. Run A (everything failing in setUp) took 212 s.

## Repository changes in this task

- `devenv/Dockerfile`: added `python3-pytest-timeout`. `devenv/check.sh`: checks `import pytest_timeout`.
  No other package changed (cpio, rpm-build, patch, unzip, lzma left absent on purpose).
- `devenv/conary_test_baseline.sh`, `devenv/triage.py`, `py3tests/test_triage.py`: runner, classifier, and its table-driven test.
- Not committed (per instruction). Logs and XML are in `tmp/` (gitignored).

## Phase 3 task proposal

Task numbers are identifiers, not the execution order. The order of work, by expected unlock
per unit of work, is given under "Suggested order of work" below the table; tasks 2 and 3
unlock few or no tests by themselves but come first on purpose, because they make every later
re-measurement possible (arm64 hosts) and fast (81 to about 3 minutes). "Unlock" counts tests that go from failed/not-run
to passed or to a clean skip, using Run B/C; it is a ceiling, since a fixed first error can
expose a second. Phase 3 should re-run `devenv/conary_test_baseline.sh` after each task and
update this table.

| # | task | scope | class | expected unlock | depends on |
|---|---|---|---|---|---|
| 1 | Replace `os.path.walk` in `util.rmtree` | one function in `conary/lib/util.py`; add a unit test | removed stdlib | 2325 error elements cleared; 199 fail->pass, 113 fail->skip (measured, Run C) | none |
| 2 | Make the container x86_64-capable and complete the toolset | `devenv/run` honours `DEVENV_PLATFORM` (distinct image tag per platform; amd64 emulation on Docker Desktop ran at usable speed); decide whether to add an `aarch64` arch to `conary/build/use.py` instead; install `cpio rpm-build patch unzip lzma python-unversioned-command`; pass `--user` on macOS to avoid uid 0; re-measure | unsupported arch, missing binary | on arm64 hosts 2303 tests (all of Run A's), on amd64 hosts ~7 tests now plus cook/patch/rpm tests once sqlharness opens | none (do first on an arm64 host; task 1 is independent) |
| 3 | `openRepository`: stop retrying on `SkipTestException` | `conary_test/rephelp.py` `__openRepository` retry loop (narrow the bare `except:`); cuts the run from 81 min to about 3 min | harness gap | 0 tests; 78 min saved per baseline | none |
| 4 | Fix `requireChroot` ctypes crash and the rpm decorator | `conary_test/__init__.py`: set `restype`/`argtypes` for libcap, decode bytes; skip cleanly without `cap_sys_chroot`; also stop `filestest` device/symlink tests leaving a deleted cwd | harness gap | 94 not-run ids become pass or skip; 3 more in filestest | none |
| 5 | Hashing callers pass bytes | `util.getId`, `util.copyfileobj`, `sha1helper.sha1String/md5String`, `digestlib` callers: encode at the boundary, one rule | bytes/str: hashing | 68 (cmdlinetest 24, acltest, sigtest, filestest, ...) | none |
| 6 | Streams/trove layer decode above StringStream | `files.py` freeze/thaw, `trove.py`, `trovetup.fromString`, `changelog`; `streams.set` callers in `rephelp.createMetadataItem`; `OptionalFlavorStream.diff` returns str; decode names/owner/group/changelog read from StringStream | bytes/str: streams/trove (+ part of other) | 69 + about 20 of "other" = about 90 (streamstest 18, trovetest 26, filestest 12, filetypestest 5) | none; precedes task 12 |
| 7 | File I/O bytes/str, including magic and javadeps | `conary/lib/magic.py` and `javadeps.py` compare bytes to str signatures (clears the 3 strict xfails in py3tests and 19 magictest, 1 javadepstest tests); `util.write/_writeImpl`, `rpmhelper.readSignatureHeader`, `logger` termios, `cpiostream`, `debhelper` | bytes/str: file I/O | 65 + 3 xfails | none |
| 8 | Py2 names and idioms in tests | `file()`, `cmp`, `cPickle`, `StringIO`, `xmlrpclib` in conary_test (cpiostreamtest, artest, systemmodeltest, rpmhelpertest, ...); mechanical | py2 code in tests | 60 (some then fall to task 5-7 errors) | none |
| 9 | `sqlite3.Connection` subclass and dbstore behaviour | `conary/local/sqldb.py` and `dbstore` sqlite driver: Py3 `sqlite3.Connection` has no `__dict__` for `_BEGIN`; PEP 479 `StopIteration` in generators; `__next__` on `DictAsCsf`; `has_key` | py3 semantics, iterator | 29 + about 20 (databasetest, sqldbtest, changesettest, utiltest) | none; gates task 12 |
| 10 | `defaultMacros` pointing at a directory | `rephelp.setUp` includes `archive/site`; `util.loadSourceModule`/`recipe.loadMacros` handle (or skip) directories as `imp.load_source` effectively did; needs manual reading of Py2 behaviour | py3 semantics (possible real bug) | 74 (expansiontest, packagepolicytest, destdirpolicytest, ...) | task 1 |
| 11 | Small Py3 semantics sweep | `cml.iterFormat` None-vs-int compare (6), `UnboundLocalError` (`util.xmlrpcDump` `io`, `conarycfgtest` `queue`), `re` LOCALE flag with str, unhashable `CMTroveSpec`, float indices in `tupleListBsearchInsert`/`TroveInfoMerge`, `isAlive`, `testDecompressStream`, harness kwarg `_returnException` | sort/compare, iterator, integer division, harness gap | about 35 | none |
| 12 | SQLite-only `sqlharness.start` | testharness only: back repository tests with SQLite, no PostgreSQL | harness gap | up to 1585 (1698 after task 1) can run past `openRepository`; expect most to fail first on bytes/str and Py2 recipes, so the first run is a new baseline, not a gain | 1, 3, 5, 6, 7, 9 |
| 13 | Py2 recipe strings | 198 of 1018 embedded recipe-like string constants fail `ast.parse` on Py3 (static scan of conary_test; 974 recipe class definitions, mostly `packagepolicytest` 247, `grouptest` 145, `recipes.py` 93, `buildtest` 67, `sourcetest` 54); mechanical `2to3` pass on the strings, then runtime fixes | py2 code in tests | measured only after task 12; ceiling is the cvctest skips (802) plus top-level cook tests | 12 |
| 14 | OpenPGP | `libtest/openpgptest.py` (88 tests, 44 failing after task 1, mostly bytes in `openpgpfile.py` and `base64.decodestring`), plus untested OpenPGP paths (signing, keyring cache, `xorStr`) | bytes/str, removed stdlib | 44 | 5, 7 |
| 15 | Transport and SSL skip behaviour | `repositorytest/transporttest.py`: the SSL tests must skip without M2Crypto like the others (currently fail); `xmlrpcDump` `UnboundLocalError`; `networking.format` bytes | harness gap, bytes/str | 4 | none |

Deferred (not tied to a measured count yet):

- epdb client/server bytes bugs: no conary_test test reaches epdb; add a py3tests test when touched.
- sqlite `PATHTYPE TEXT` rejects non-UTF-8 paths on bind: only reachable once repository tests run (after task 12); decide TEXT vs BLOB then.
- Server stand-ins (nginx/gunicorn/uwsgi/memcache): 1 skip measured here; larger once task 12 opens repository tests.
- M2Crypto: no Fedora 45 / Python 3.15 package; SSL tests stay skipped.
- Real-bug candidates: none confirmed. Task 10 and `unknown` items in `cmdlinetest`, `cmltest`, `cooktest`
  need manual reading after tasks 5-7; revisit then.

Suggested order of work: 1, 3, 2 (environment and one-liners, about 2000 errors cleared and the
loop shrinks to minutes), then 5, 4, 8, 9, 7, 6 (about 330 tests), then 10, 11, 14, 15, then
12 and 13 together as the repository milestone.

## Re-baseline after 3.1-3.3 (2026-11-26)

Tooling: `devenv/conary_test_baseline.sh`, committed state plus the 3.3 working tree
(HEAD b609b1f78). Two runs, each in its own outdir, as uid 501 (non-root):

- **native**: `devenv/conary_test_baseline.sh tmp/baseline-aarch64` (aarch64 image
  `conary-devenv:fde2af09a6c3`).
- **amd64** (canonical baseline): `DEVENV_PLATFORM=linux/amd64 devenv/conary_test_baseline.sh tmp/baseline-amd64`
  (image `conary-devenv:fde2af09a6c3-amd64`, emulated). This overwrote the old Run B outdir
  of the same name; Run B numbers above are unchanged and come from the earlier run.

`env.txt` in each outdir records host and container git HEAD, platform, `uname -m` and uid.

| | Run B (amd64, root, before 3.1-3.3) | native aarch64 | amd64 (canonical) |
|---|---|---|---|
| collected (ids) | 2810 | 2810 | 2812 |
| ids reported | 2716 | 2719 | 2719 |
| passed | 242 | 450 | 450 |
| failed | 821 | 514 | 513 |
| skipped | 1653 | 1755 | 1756 |
| not run (crashed.txt) | 94 | 91 | 91 |
| wall time | 81 min | 6 min 59 s | 11 min 40 s |
| 'No Such Arch' occurrences | 0 | 0 (Run A: 2303) | 0 |

The not-run ids are the same 91 in both runs (`capsuletest` 34, `cookrpmcapsuletest` 23,
`capsulepolicytest` 21, `derivedcapsuletest` 4, and singles): the `requireChroot` libcap ctypes
segfault (Phase 3 task 4). No outer timeout fired. Per-test timeout: 1 (`testLazyFileCache`).

Top classes from `devenv/triage.py` (native; amd64 is within one test of every count, with
unknown 58 instead of 59):

| class | native | amd64 |
|---|---|---|
| py3 semantics: other | 111 | 111 |
| bytes/str: streams/trove | 70 | 70 |
| bytes/str: hashing | 68 | 68 |
| bytes/str: file I/O | 64 | 64 |
| py2 code in tests | 60 | 60 |
| unknown | 59 | 58 |

Run B's top class (`rmtree` removed stdlib, 2325 elements) is gone; `removed stdlib module/API`
is now 15. `unsupported arch` is 0 natively: the aarch64 arch data file (`config/arch/aarch64`,
`conary_test/archive/arch/aarch64`) fixes Run A's 2303 `No Such Arch aarch64` failures.

New triage class `arch-specific expectation` (a test hardcodes x86/x86_64 or an arch key):
native 1 (`CrossCompileTest.testCrossToolProvidesRequires`, `KeyError: 'aarch64'`), amd64 0.
This is far below the roughly 204 hardcoded x86 sites in conary_test because 1690 of the
1755 skips are `sqlharness` skips that hide those tests; expect the class to grow on aarch64
once task 12 lets repository tests run. **The amd64 run stays the canonical baseline**; native
aarch64 results are comparable only for tests that do not assert an x86 flavor.

Non-root (uid 501, compared with Run B as root): the container no longer runs as root, so root-only
tests now fail instead of passing: `filestest.FilesTest.testBlock` and `testChar` (mknod of device
files, `PermissionError: Operation not permitted`) and the teardown of
`cooktest.MultipleMainPackageTest.testCookRemoveBadPermissions` (`Permission denied` removing a
read-only dir). These are the only root-needing results in the logs; use `DEVENV_ROOT=1` to
reproduce root behaviour. The three permission tests in `py3tests/test_util_rmtree.py` now run.
Building `conary/lib`, `conary/lib/ext` and `conary_test` and writing `tmp/` work as non-root.

Other measured facts:

- The build outputs (`conary/lib/elf.so`, `filename_wrapper.so`, `conary/lib/ext/*.so`,
  `conary_test/*.so`) live in the shared checkout and are architecture specific.
  Switching `DEVENV_PLATFORM` requires `make -C conary/lib clean`, `make -C conary/lib/ext clean`
  and `make -C conary_test clean` first. A first amd64 baseline taken with a stale aarch64
  `elf.so` and `norpmlock.so` was discarded and re-run.
- py3tests: native 702 passed, 3 xfailed, 0 skipped; amd64 702 passed, 3 xfailed.
- `python` (python-unversioned-command) is needed: `cmdlinetest.testCvcImportNoSysArgv` execs it.
