"""Recipe source embedded in conary_test strings parses on Python 3.

Conary compiles recipe text at cook time, so a Python 2 construct in an
embedded recipe (an old octal literal, a print statement, ``except X, e``)
only shows up when that test reaches the cook.  This scan finds every string
constant that looks like recipe source and compiles it with ast.parse, so the
debt is visible without a repository.

Strings that are %-templates are formatted later, so they are retried with
the placeholders replaced by an identifier.  Pieces joined with ``+`` or
``"\\n".join([...])`` are rebuilt first, with a placeholder identifier in
place of every non-constant piece.  SyntaxWarning (invalid escapes) counts
as a failure: the warning reaches stderr when the recipe is cooked.
"""
import ast
import os
import re
import textwrap
import warnings

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONARY_TEST = os.path.join(ROOT, 'conary_test')

_RECIPE_CLASS = re.compile(r'^[ \t]*class \w+\s*\(.*Recipe.*\)\s*:', re.M)
_PLACEHOLDER = '_PH_'
_PCT = re.compile(r'%%|%\([^)]*\)[-#0 +]*\d*(?:\.\d+)?[a-zA-Z]|%[sdr]')

# (relative path, marker substring) -> reason.  Strings that are
# intentionally not valid Python 3 recipes.  Keyed by a stable marker, never
# a line number; test_allowlist_entries_still_match keeps the list honest.
ALLOWLIST = {
    ('conary_test/cvctest/buildtest/loadrecipetest.py',
     "NameError: name 'b' is not defined"):
        'expected traceback text of a failing recipe load, not recipe source',
}


def looks_like_recipe(text):
    if _RECIPE_CLASS.search(text):
        return True
    return 'class ' in text and 'def setup' in text


def _substitute(text):
    return _PCT.sub(
        lambda m: '%' if m.group(0) == '%%' else _PLACEHOLDER, text)


def _parse(text):
    """Return None when text parses, else an error string.

    A SyntaxWarning is reported like an error.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        try:
            ast.parse(text)
        except (SyntaxError, ValueError) as err:
            return err
    for w in caught:
        if issubclass(w.category, SyntaxWarning):
            return w
    return None


def _describe(text, err):
    if isinstance(err, SyntaxError):
        lineno = err.lineno or 1
        msg = err.msg
    elif isinstance(err, ValueError):
        return 0, str(err)
    else:
        lineno = err.lineno or 1
        msg = str(err.message)
    lines = text.splitlines()
    src = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ''
    return lineno, '%s: %s' % (msg, src)


def check_recipe_text(text):
    """Return None if recipe text is valid Python 3, else (lineno, message).

    lineno is relative to the (dedented) text.  The text is parsed as it is;
    only when that fails are %-placeholders substituted and the parse
    repeated, and the error from that second parse is the one reported.
    """
    text = textwrap.dedent(text)
    err = _parse(text)
    if err is None:
        return None
    substituted = _substitute(text)
    if substituted == text:
        return _describe(text, err)
    err = _parse(substituted)
    if err is None:
        return None
    return _describe(substituted, err)


def _flatten_add(node):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _flatten_add(node.left) + _flatten_add(node.right)
    return [node]


def _str_value(node, env=None):
    """The text a node contributes to a rebuilt string, else None.

    env maps module-level names bound to strings, so that
    a recipe built as preface + tail is rebuilt with the preface text.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and env and node.id in env:
        return env[node.id]
    # 'text %s' % x  contributes its text (a template)
    if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
            and _str_value(node.left, env) is not None):
        return _str_value(node.left, env)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        parts = [_str_value(p, env) for p in _flatten_add(node)]
        if all(p is not None for p in parts):
            return ''.join(parts)
    return None


def _join_parts(node):
    """The element nodes of  "sep".join([a, b, ...]), else None."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'join' and len(node.args) == 1
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
            and isinstance(node.args[0], (ast.List, ast.Tuple))):
        return node.func.value.value, node.args[0].elts
    return None


def _rebuild(parts, sep, env=None):
    pieces = []
    for p in parts:
        v = _str_value(p, env)
        pieces.append(_PLACEHOLDER if v is None else v)
    return sep.join(pieces)


def candidate_strings(tree):
    """Yield (lineno, text) for each recipe-like string in an ast tree.

    Fragments joined with + or "sep".join([...]) are rebuilt and yielded once,
    at the line of the outermost node.
    """
    consumed = set()
    env = {}
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            value = _str_value(stmt.value, env)
            if value is not None:
                env[stmt.targets[0].id] = value

    def visit(node):
        text = None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            parts = _flatten_add(node)
            if any(_str_value(p, env) is not None for p in parts):
                text = _rebuild(parts, '', env)
                for p in parts:
                    if _str_value(p, env) is not None:
                        consumed.add(id(p))
                        if isinstance(p, ast.BinOp):
                            consumed.add(id(p.left))
        else:
            joined = _join_parts(node)
            if joined is not None:
                sep, elts = joined
                text = _rebuild(elts, sep, env)
                for p in elts:
                    consumed.add(id(p))
                    if isinstance(p, ast.BinOp):
                        consumed.add(id(p.left))
        if text is not None and looks_like_recipe(text):
            yield node.lineno, text
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in consumed
                and looks_like_recipe(node.value)):
            yield node.lineno, node.value
        for child in ast.iter_child_nodes(node):
            yield from visit(child)

    yield from visit(tree)


def _sources(root=None):
    for dirpath, dirnames, filenames in os.walk(root or CONARY_TEST):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.endswith('.py'):
                path = os.path.join(dirpath, fn)
                with open(path, encoding='utf-8') as f:
                    yield path, f.read()


def _allowed(rel, text):
    for (arel, marker), _reason in ALLOWLIST.items():
        if arel == rel and marker in text:
            return (arel, marker)
    return None


def scan(root=None):
    """Return (failures, allowlist keys that matched, candidate count)."""
    failures = []
    used = set()
    count = 0
    for path, source in _sources(root):
        rel = os.path.relpath(path, ROOT)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                tree = ast.parse(source, path)
        except SyntaxError as e:
            # a module that does not parse hides all of its recipe strings
            failures.append('%s:%s module does not parse: %s'
                            % (rel, e.lineno, e.msg))
            continue
        for lineno, text in candidate_strings(tree):
            count += 1
            key = _allowed(rel, text)
            if key:
                used.add(key)
                continue
            res = check_recipe_text(text)
            if res is not None:
                failures.append('%s:%d (recipe line %d) %s'
                                % (rel, lineno, res[0], res[1]))
    return failures, used, count


def test_embedded_recipes_parse_on_python3():
    failures, _used, count = scan()
    assert count > 900, 'scan found only %d candidate strings' % count
    assert failures == [], '\n' + '\n'.join(failures)


def test_allowlist_entries_still_match():
    _failures, used, _count = scan()
    assert used == set(ALLOWLIST), set(ALLOWLIST) - used


# -- helper unit tests -------------------------------------------------------

RECIPE = '''
class Foo(PackageRecipe):
    name = 'foo'
    version = '1'
    def setup(r):
%s
'''


@pytest.mark.parametrize('body,ok', [
    ("        r.Create('/a', mode=0755)", False),
    ("        r.Create('/a', mode=0o755)", True),
    ("        print 'x'", False),
    ("        x = `1`", False),
    ("        r.Create('/a', mode=0)", True),
    ("        r.Create('/foo/%d' % 1)", True),
])
def test_check_recipe_text(body, ok):
    res = check_recipe_text(RECIPE % body)
    assert (res is None) == ok, res


def test_octal_failure_is_located():
    lineno, msg = check_recipe_text(RECIPE % "        x = 0755")
    # leading newline of RECIPE is line 1; the class is line 2
    assert lineno == 6
    assert '0755' in msg


def test_template_placeholders_pass():
    for body in ("        requireLatest = %(LATEST)s",
                 "        r.addRedirect(%(redirect)s)",
                 "        x = '100%%'; y = %s"):
        assert check_recipe_text(RECIPE % body) is None, body
    assert check_recipe_text(
        'class %(classname)sRecipe(PackageRecipe):\n'
        '    def setup(r):\n        pass\n') is None


def test_template_substitution_still_checks_the_rest():
    res = check_recipe_text(RECIPE % "        x = %(v)s\n        y = 0755")
    assert res is not None and '0755' in res[1]


def test_real_percent_code_is_not_mangled():
    # raw parse succeeds, so the template fallback is never used
    assert check_recipe_text(
        RECIPE % "        for i in range(3):\n"
                 "            r.Create('/foo/%d' % i)") is None


def test_fragments_are_rebuilt():
    src = ("x = ('class Foo(PackageRecipe):\\n'\n"
           "     '    def setup(r):\\n        x = ' + body)\n"
           "y = '\\n'.join(['class Bar(PackageRecipe):',\n"
           "               '    def setup(r):', '        x = 0755'])\n")
    found = list(candidate_strings(ast.parse(src)))
    assert [ln for ln, _t in found] == [1, 3]
    assert found[0][1] == ('class Foo(PackageRecipe):\n'
                           '    def setup(r):\n        x = ' + _PLACEHOLDER)
    assert check_recipe_text(found[0][1]) is None
    assert check_recipe_text(found[1][1]) is not None


def test_syntax_warning_is_a_failure():
    res = check_recipe_text(RECIPE % "        r.Run('\\d+')")
    assert res is not None and 'escape' in res[1]
    assert check_recipe_text(RECIPE % "        r.Run(r'\\d+')") is None


def test_non_recipe_strings_are_not_candidates():
    tree = ast.parse("a = 'class Foo: pass'\nb = 'def setup(): 0755'\n")
    assert list(candidate_strings(tree)) == []


def test_unparseable_module_is_a_failure(tmp_path):
    (tmp_path / 'broken.py').write_text('def f(:\n')
    failures, _used, count = scan(str(tmp_path))
    assert count == 0
    assert len(failures) == 1 and 'module does not parse' in failures[0]
