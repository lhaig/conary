"""loadMacros/loadSourceModule with file, directory and missing entries,
and loadrecipe._copyReusedRecipes on a module holding a Recipe subclass."""
import sys
import types

import pytest

from conary.build import loadrecipe, recipe
from conary.lib import util


@pytest.fixture(autouse=True)
def _clean_tmpmodule():
    sys.modules.pop('tmpmodule', None)
    yield
    sys.modules.pop('tmpmodule', None)


def test_file_entry_has_no_dunder_keys(tmp_path):
    f = tmp_path / 'macros'
    f.write_text("foo = 'bar'\n")
    assert recipe.loadMacros([str(f)]) == {'foo': 'bar'}


def test_glob_entry_sorted_later_wins(tmp_path):
    d = tmp_path / 'macros.d'
    d.mkdir()
    (d / 'b').write_text("x = 'b'\nonlyb = 1\n")
    (d / 'a').write_text("x = 'a'\nonlya = 1\n")
    assert recipe.loadMacros([str(d / '*')]) == {
        'x': 'b', 'onlya': 1, 'onlyb': 1}


def test_directory_entry_adds_nothing(tmp_path):
    d = tmp_path / 'site'
    d.mkdir()
    assert recipe.loadMacros([str(d)]) == {}


def test_directory_in_glob_is_skipped(tmp_path):
    d = tmp_path / 'macros.d'
    (d / '__pycache__').mkdir(parents=True)
    (d / 'a').write_text("foo = 1\n")
    assert recipe.loadMacros([str(d / '*')]) == {'foo': 1}


def test_file_plus_directory_keeps_file_macros(tmp_path):
    f = tmp_path / 'macros'
    f.write_text("foo = 'bar'\n")
    d = tmp_path / 'site'
    d.mkdir()
    assert recipe.loadMacros([str(f), str(d)]) == {'foo': 'bar'}


def test_missing_entry_adds_nothing(tmp_path):
    assert recipe.loadMacros([str(tmp_path / 'nope')]) == {}


def test_load_source_module_file(tmp_path):
    f = tmp_path / 'noext'
    f.write_text("attr = 42\n")
    mod = util.loadSourceModule('tmpmodule', str(f))
    assert mod.attr == 42
    assert sys.modules['tmpmodule'] is mod


def test_load_source_module_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        util.loadSourceModule('tmpmodule', str(tmp_path / 'nope'))
    assert 'tmpmodule' not in sys.modules


def test_load_source_module_directory_raises(tmp_path):
    """Deliberately differs from Py2 imp.load_source, which returned an
    empty module for a directory. loadMacros skips directories itself;
    other callers load explicit files and should fail loudly."""
    with pytest.raises(IsADirectoryError):
        util.loadSourceModule('tmpmodule', str(tmp_path))
    assert 'tmpmodule' not in sys.modules


def test_copy_reused_recipes():
    class Base(recipe.Recipe):
        attr = ['a']

        def method(self):
            return 'ok'

    mod = types.ModuleType('fake')
    mod.Base = Base
    loader = object.__new__(loadrecipe.Importer)
    loader.module = mod
    loader._copyReusedRecipes()
    copy = mod.Base
    assert copy is not Base
    assert copy.__name__ == 'Base'
    assert copy.method is Base.method
    assert copy.attr == ['a'] and copy.attr is not Base.attr
