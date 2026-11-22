#!/bin/bash
# Byte-compile (in memory, no .pyc written) every Python source under
# conary, conary_test, commands and scripts with the container's python3.
# Covers *.py, *.py.in and extensionless files with a python shebang.
# Prints FAIL lines and exits 1 on any failure.
# Usage: devenv/compile_check.sh   (run on the host; it calls devenv/run itself)
set -euo pipefail
cd "$(dirname "$0")/.."
exec devenv/run python3 -I - <<'PY'
import os, re, sys
roots = ['conary', 'conary_test', 'commands', 'scripts']
shebang = re.compile(rb'^#!.*python')
fails = total = 0
for root in roots:
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in ('.git', '__pycache__')]
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            if not (fn.endswith('.py') or fn.endswith('.py.in')):
                if '.' in fn:
                    continue
                with open(p, 'rb') as f:
                    if not shebang.match(f.readline()):
                        continue
            total += 1
            with open(p, 'rb') as f:
                src = f.read()
            try:
                compile(src, p, 'exec', dont_inherit=True)
            except (SyntaxError, ValueError, UnicodeDecodeError) as e:
                fails += 1
                print('FAIL %s:%s %s' % (p, getattr(e, 'lineno', '?'), e))
print('checked %d files, %d failures' % (total, fails))
sys.exit(1 if fails else 0)
PY
