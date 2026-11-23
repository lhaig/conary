"""conary.repository.transport helpers that replaced removed stdlib APIs."""
import pytest

from conary.repository import transport


@pytest.mark.parametrize('value,expected', [
    # expected results are what cgi.parse_header returned on Python 3.11
    ('', ('', {})),
    ('text/xml', ('text/xml', {})),
    ('multipart/mixed; boundary="abc def"',
     ('multipart/mixed', {'boundary': 'abc def'})),
    ('TEXT/XML; Charset=utf-8', ('TEXT/XML', {'charset': 'utf-8'})),
    ('application/x-conary-change-set ; boundary=x;a=1',
     ('application/x-conary-change-set', {'boundary': 'x', 'a': '1'})),
])
def test_parse_header_matches_cgi(value, expected):
    assert transport._parseHeader(value) == expected


def test_transport_imports_without_cgi():
    # cgi left the stdlib in 3.13; a third-party cgi.py in site-packages
    # (pulled in by webob) must not be what makes transport importable.
    import os, subprocess, sys
    code = (
        "import sys\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'cgi':\n"
        "            raise ImportError('cgi blocked')\n"
        "sys.meta_path.insert(0, Block())\n"
        "import conary.repository.transport\n")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res = subprocess.run([sys.executable, '-c', code], cwd=root,
                         env=dict(os.environ, PYTHONPATH=root),
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
