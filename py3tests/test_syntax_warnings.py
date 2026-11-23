"""Compile every in-scope source and assert no SyntaxWarning is emitted.

File discovery mirrors devenv/compile_check.sh.
"""
import os
import re
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTS = ['conary', 'conary_test', 'commands', 'scripts']
SHEBANG = re.compile(rb'^#!.*python')


def _sources():
    for root in ROOTS:
        for dp, dns, fns in os.walk(os.path.join(ROOT, root)):
            dns[:] = [d for d in dns if d not in ('.git', '__pycache__')]
            for fn in sorted(fns):
                p = os.path.join(dp, fn)
                if os.path.islink(p) or not os.path.isfile(p):
                    continue
                if not (fn.endswith('.py') or fn.endswith('.py.in')):
                    if '.' in fn:
                        continue
                    with open(p, 'rb') as f:
                        if not SHEBANG.match(f.readline()):
                            continue
                yield p


def test_no_syntax_warnings():
    found = []
    nfiles = 0
    for p in _sources():
        nfiles += 1
        with open(p, 'rb') as f:
            src = f.read()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            compile(src, p, 'exec', dont_inherit=True)
        for w in caught:
            if issubclass(w.category, SyntaxWarning):
                found.append('%s:%s %s' % (os.path.relpath(p, ROOT),
                                           w.lineno, w.message))
    assert nfiles > 200
    assert not found, '%d SyntaxWarnings:\n%s' % (len(found), '\n'.join(found))
