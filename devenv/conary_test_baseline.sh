#!/bin/bash
# Baseline run of conary_test: one pytest process per test file, bounded by
# an outer timeout, JUnit XML per file in <outdir> (default tmp/baseline,
# gitignored). A file whose process dies without writing XML (segfault,
# outer timeout, test that removes the cwd) is re-run one test id per process
# so the survivors are still measured; ids that die are recorded in crashed.txt.
# Usage: devenv/conary_test_baseline.sh [outdir]   (run on the host; outdir relative to the repo root)
set -u
cd "$(dirname "$0")/.."
OUT=${1:-tmp/baseline}
# The repo is mounted at /src, so OUT must be a plain path relative to the repo root.
case "$OUT" in
  /*|*..*|*[!A-Za-z0-9._/-]*) echo "outdir must be relative to the repo root, without spaces or '..': $OUT" >&2; exit 2;;
esac
mkdir -p "$OUT"
# Recorded in env.txt. The host HEAD is passed in because a tree copy has no .git.
HOST_HEAD=$(git rev-parse HEAD 2>/dev/null || echo unknown)
PLAT=${DEVENV_PLATFORM:-native}
case "$PLAT" in *[!A-Za-z0-9._/-]*) echo "bad DEVENV_PLATFORM: $PLAT" >&2; exit 2;; esac
rm -f "$OUT"/*.xml "$OUT"/*.log "$OUT"/rc.txt "$OUT"/crashed.txt
exec devenv/run bash -c '
OUT=/src/'"$OUT"'
cd /src
{ date -u +%FT%TZ; python3 -VV
  echo "host git HEAD: '"$HOST_HEAD"'"
  echo "container git HEAD: $(git -c safe.directory=/src rev-parse HEAD 2>&1)"
  echo "platform: '"$PLAT"'"
  echo "uname -m: $(uname -m)"
  echo "uid: $(id -u)"; } > $OUT/env.txt 2>&1
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
