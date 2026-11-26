#!/usr/bin/env python3
"""Classify conary_test failures from the JUnit XML of a baseline run.

Usage: python3 devenv/triage.py [outdir]   (default tmp/baseline)

Every failing test is given a signature (final exception type plus the
innermost frame under conary/, falling back to conary_test/ then
testharness/) and exactly one class from an ordered first-match rule list.
Skips are grouped by reason. Output is Markdown on stdout.
"""
import collections
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

FRAME = re.compile(r'^\s*File "([^"]+)", line (\d+), in (.+)$')
EXC = re.compile(r'^([A-Za-z_][\w.]*)(?::\s?(.*))?$')
SRC_ROOTS = (('conary', '/src/conary/'),
             ('conary_test', '/src/conary_test/'),
             ('testharness', '/src/testharness/'))

CLASSES = ['missing binary', 'harness gap', 'timeout', 'unsupported arch',
           'removed stdlib module/API', 'py2 code in tests',
           'bytes/str: streams/trove', 'bytes/str: file I/O',
           'bytes/str: hashing', 'bytes/str: network/xmlrpc',
           'bytes/str: other', 'sort/compare', 'iterator/dict-view', 'py3 semantics: other',
           'integer division', 'real bug', 'unknown']

BYTES_MSGS = (
    'a bytes-like object is required', "can't concat str to bytes",
    "can't concat bytes to str", 'decoding str is not supported',
    'argument must be str, not bytes', 'startswith first arg must be bytes',
    'must be str, not bytes', 'must be bytes', 'expected bytes',
    'expected str', 'cannot use a string pattern on a bytes-like',
    'cannot use a bytes pattern on a string-like', 'a str-like object',
    "'bytes' object has no attribute 'encode'",
    "'str' object has no attribute 'decode'",
    "'bytes' object has no attribute", "write() argument must be str",
    'string argument without an encoding', "bytes' object cannot be interpreted",
    'Unicode-objects must be encoded', 'object supporting the buffer API',
)
BINARIES = ('python', 'cpio', 'rpmbuild', 'patch', 'unzip', 'lzma', 'rpm2cpio',
            'rpmbuild-', 'sudo', 'chroot', 'gpg', 'git', 'ldd')


def parse_trace(text):
    """Return (exc_type, exc_msg, frames) from the last traceback in text."""
    lines = text.splitlines()
    start = 0
    for i, ln in enumerate(lines):
        if ln.startswith('Traceback (most recent call last)'):
            start = i
    frames = []
    last_frame = -1
    for i in range(start, len(lines)):
        m = FRAME.match(lines[i])
        if m:
            frames.append((m.group(1), int(m.group(2)), m.group(3)))
            last_frame = i
    exc_type, exc_msg = '', ''
    for ln in lines[last_frame + 1:]:
        if not ln.strip() or ln[0] in ' \t':
            continue
        m = EXC.match(ln)
        if m:
            exc_type, exc_msg = m.group(1), m.group(2) or ''
        else:
            exc_type, exc_msg = ln.split(':', 1)[0], ln
        break
    # multi-line messages: keep the whole tail for classification
    tail = '\n'.join(lines[last_frame + 1:])
    return exc_type, exc_msg, frames, tail


def innermost(frames):
    """(tag, 'path:func') for the innermost conary frame, else fallbacks."""
    for tag, root in SRC_ROOTS:
        for path, _line, func in reversed(frames):
            if path.startswith(root):
                return tag, '%s:%s' % (path[len('/src/'):], func)
    return 'none', '-'


def signature(text):
    exc_type, exc_msg, frames, tail = parse_trace(text)
    tag, frame = innermost(frames)
    return {'exc': exc_type.split('.')[-1], 'msg': exc_msg, 'tail': tail,
            'full': text,
            'frame': frame, 'tag': tag, 'frames': frames}


def _paths(sig):
    return [f[0] for f in sig['frames']]


def classify(sig, extra=''):
    """Return one class from CLASSES. extra is captured stdout/stderr."""
    exc, msg, tail = sig['exc'], sig['msg'], sig['tail']
    frame, tag = sig['frame'], sig['tag']
    blob = tail + '\n' + extra
    last = sig['frames'][-1][0] if sig['frames'] else ''

    # 1. missing binary
    if exc == 'FileNotFoundError' and any(
            re.search(r"No such file or directory: '(%s)'" % b, msg)
            for b in BINARIES):
        return 'missing binary'
    if re.search(r'(%s): (command )?not found' % '|'.join(BINARIES), blob) \
            or re.search(r"(^|\W)(cpio|rpmbuild|unzip|lzma|patch)(: | not found|\b.*not installed)",
                         msg):
        return 'missing binary'
    if 'is not installed' in msg and 'M2Crypto' not in msg:
        return 'missing binary'
    # 2. harness gap (including skips swallowed by a broad except)
    if tag == 'testharness' or last.startswith('/src/testharness/') \
            or 'SkipTestException' in exc \
            or 'sqlharness:' in blob or 'harness not rebuilt' in blob:
        return 'harness gap'
    if exc == 'TypeError' and 'RepositoryHelper' in msg:
        return 'harness gap'
    if exc in ('AttributeError', 'TypeError') and re.search(
            r'testutils|testrunner|testhelp|sqlharness', msg):
        return 'harness gap'
    if exc == 'TypeError' and re.search(
            r"unexpected keyword argument '_returnException'", msg):
        return 'harness gap'
    if exc == 'AttributeError' and re.search(
            r"object has no attribute '(owner|findUnknownIds|assertEquals|"
            r"assertRaisesRegexp|failUnless|failIf)'", msg):
        return 'harness gap'
    if exc == 'Failed' and 'Timeout' in msg:
        return 'timeout'
    # 3. unsupported architecture (container is aarch64)
    if 'No Such Arch' in msg:
        return 'unsupported arch'
    # 4. removed module or stdlib API
    if exc in ('ModuleNotFoundError', 'ImportError'):
        return 'removed stdlib module/API'
    if re.search(r"module '(types|string|os|sys|itertools|inspect|time|"
                 r"collections|operator|urllib|socket)' has no attribute",
                 sig['full']) or "type object 'Marshaller' has no" in msg:
        return 'removed stdlib module/API'
    if exc == 'AttributeError' and re.search(
            r"module '(posixpath|os\.path|os|string|types|itertools|sys|"
            r"time|socket|inspect|collections|unittest|pickle|imp)' has no "
            r"attribute", msg):
        return 'removed stdlib module/API'
    # 5. Py2 code in tests / recipes
    if exc in ('SyntaxError', 'IndentationError', 'TabError') or (
            exc in ('NameError', 'TypeError') and any(
                p in ('<string>', '<recipe>') or p.startswith('<')
                for p in _paths(sig))):
        return 'py2 code in tests'
    if exc == 'NameError' and re.search(
            r"name '(unicode|basestring|long|xrange|raw_input|unichr|reduce|"
            r"file|cmp|execfile|reload|cPickle|xmlrpclib|StringIO|cStringIO)' "
            r"is not defined", msg):
        return 'py2 code in tests'
    # 6. bytes/str
    if 'Strings must be encoded before hashing' in msg:
        return 'bytes/str: hashing'
    if exc == 'AssertionError' and frame == 'conary/streams.py:set':
        return 'bytes/str: streams/trove'
    if re.search(r"string argument expected, got 'bytes'|initial_value must "
                 r"be str|underlying read\(\) should have returned a bytes|"
                 r"unsupported operand type\(s\) for \^: 'str' and 'str'|"
                 r"expected a bytes-like object, str found|"
                 r"decodestring|InvalidMagicError", sig['full']):
        return 'bytes/str: file I/O' if 'openpgp' not in frame else 'bytes/str: other'
    if exc == 'AttributeError' and "'NoneType' object has no attribute" in msg \
            and 'magictest' in frame:
        return 'bytes/str: file I/O'
    isbytes = any(m in blob for m in BYTES_MSGS) or (
        re.search(r'can only concatenate str \(not "bytes"\)|'
                  r'argument should be integer or bytes-like', msg)) or (
        exc == 'AssertionError' and re.search(r"\bb['\"]", tail)) or (
        exc == 'UnicodeDecodeError') or (exc == 'UnicodeEncodeError')
    if isbytes:
        where = frame
        if re.search(r'(streams|trove|files|deps/|versions|changelog|'
                     r'conary/local/|filecontents|datastore)', where):
            return 'bytes/str: streams/trove'
        if re.search(r'(sha1helper|digestlib|digest|sha256)', where):
            return 'bytes/str: hashing'
        if re.search(r'(transport|netclient|xmlshims|netrepos|'
                     r'conaryclient/|http|proxy|callcache|server)', where):
            return 'bytes/str: network/xmlrpc'
        if re.search(r'(util\.py|lib/(magic|elf|openpgp|log|cfg|fixeddifflib)|'
                     r'lib/(copy|misc|ext)|open|read|write|archive)', where):
            return 'bytes/str: file I/O'
        return 'bytes/str: other'
    # 7. sort/compare
    if re.search(r"'[<>]=?' not supported between|cmp\(\) got an unexpected"
                 r"|'cmp' is an invalid keyword|sort\(\) takes no positional",
                 msg):
        return 'sort/compare'
    # 8. iterator/dict-view
    if re.search(r"'(dict_keys|dict_values|dict_items|map|filter|zip|"
                 r"dict_keyiterator|range)' object|dictionary changed size|"
                 r"is not subscriptable|object is not an iterator", msg) \
            and ('not callable' not in msg):
        return 'iterator/dict-view'
    if "generator raised StopIteration" in msg or "'Thread' object has no attribute 'isAlive'" in msg:
        return 'iterator/dict-view' if 'StopIteration' in msg else 'removed stdlib module/API'
    if "has no attribute '__next__'" in msg or "has no attribute 'next'" in msg \
            or re.search(r"has no attribute '(iteritems|itervalues|iterkeys|"
                         r"has_key)'", msg):
        return 'iterator/dict-view'
    # 9. integer division
    if re.search(r"list indices must be integers or slices, not float", msg):
        return 'integer division'
    if re.search(r"'float' object cannot be interpreted as an integer|"
                 r"slice indices must be|float.*as an index|"
                 r"can't multiply sequence by non-int of type 'float'", msg):
        return 'integer division'
    if exc == 'UnboundLocalError' or re.search(
            r'unhashable type|no __dict__ for setting|cannot use LOCALE|invalid mode|Unrecognized end-of-string|'
            r'is not subscriptable|IsADirectoryError', msg + exc):
        return 'py3 semantics: other'
    # 10. real bug: only by manual reading, so assertion failures that carry
    # no porting signature stay in unknown until reviewed
    return 'unknown'


def load(outdir):
    """Return (results, dup_ids).

    results[id] = {status, module, skip_reason, problems}. status is the
    primary outcome: failed > skipped/xfail > error > passed. problems lists
    every <failure>/<error> element as (kind, text, message, extra); a test
    that skipped and then failed in teardown has status skipped and one
    problem of kind error (pytest counts both).
    """
    results = {}
    dups = 0
    for path in sorted(glob.glob(os.path.join(outdir, '*.xml'))):
        mod = os.path.basename(path)[:-4]
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for tc in root.iter('testcase'):
            tid = '%s::%s' % (tc.get('classname'), tc.get('name'))
            extra = ''.join((tc.findtext(t) or '')
                            for t in ('system-out', 'system-err'))
            problems = [(c.tag, c.text or '', c.get('message', ''), extra)
                        for c in tc if c.tag in ('failure', 'error')]
            sk = tc.find('skipped')
            if any(p[0] == 'failure' for p in problems):
                status = 'failed'
            elif sk is not None:
                status = 'xfail' if sk.get('type') == 'pytest.xfail' \
                    else 'skipped'
            elif problems:
                status = 'error'
            else:
                status = 'passed'
            rec = {'status': status, 'module': mod, 'problems': problems,
                   'skip_reason': ((sk.get('message') or sk.text or '')
                                   if sk is not None else '')}
            if tid in results:
                dups += 1
                old = results[tid]
                order = ['passed', 'error', 'skipped', 'xfail', 'failed']
                if order.index(old['status']) >= order.index(status):
                    old['problems'] += problems
                    continue
                rec['problems'] += old['problems']
            results[tid] = rec
    return results, dups


def skip_group(reason):
    r = reason
    if 'sqlharness' in r or 'sql harness' in r.lower():
        return 'sqlharness'
    if 'web server harness' in r:
        return 'server stand-ins (nginx/gunicorn/uwsgi/memcache)'
    if 'M2Crypto' in r:
        return 'M2Crypto'
    if 'is not installed' in r:
        return 'binary/module not installed'
    if 'RPM module' in r or 'cap_sys_chroot' in r:
        return 'rpm/chroot'
    return 'other'


def report(outdir):
    results, dups = load(outdir)
    by_status = collections.Counter(r['status'] for r in results.values())
    out = ['total ids: %d  %s  (duplicate ids across files: %d)'
           % (len(results), dict(by_status), dups)]
    cls = collections.defaultdict(list)
    sigs = collections.Counter()
    sig_class = {}
    kinds = collections.Counter()
    for tid, r in sorted(results.items()):
        for kind, text, _msg, extra in r['problems']:
            s = signature(text)
            c = classify(s, extra)
            key = '%s @ %s [%s]' % (s['exc'], s['frame'], s['tag'])
            kinds[kind] += 1
            sigs[key] += 1
            sig_class.setdefault(key, collections.Counter())[c] += 1
            cls[c].append((tid, s['exc'] + ': ' + s['msg'].strip()[:100],
                           key, kind, r['status']))
    out.append('\nproblem elements: %s' % dict(kinds))
    out.append('\n## Classes (sum %d)' % sum(len(v) for v in cls.values()))
    for c in CLASSES:
        v = cls.get(c, [])
        out.append('- %s: %d' % (c, len(v)))
        for tid, msg, _k, kind, st in v[:3]:
            out.append('    - %s [%s/%s] -- %s' % (tid, kind, st, msg))
    out.append('\n## Top 15 signatures')
    for key, n in sigs.most_common(15):
        out.append('- %d  %s  -> %s' % (n, key, dict(sig_class[key])))
    skips = collections.defaultdict(collections.Counter)
    for t, r in results.items():
        if r['status'] == 'skipped':
            skips[skip_group(r['skip_reason'])][r['skip_reason'][:100]] += 1
    out.append('\n## Skips (primary outcome skipped)')
    for g, c in sorted(skips.items(), key=lambda kv: -sum(kv[1].values())):
        out.append('- %s: %d' % (g, sum(c.values())))
        for reason, n in c.most_common(5):
            out.append('    - %d  %s' % (n, reason))
    return '\n'.join(out), results, cls, sigs, sig_class


if __name__ == '__main__':
    print(report(sys.argv[1] if len(sys.argv) > 1 else 'tmp/baseline')[0])
