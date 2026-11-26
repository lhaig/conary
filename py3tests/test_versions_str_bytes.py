"""VersionFromString and ThawVersion must treat str and bytes alike."""
import pytest

from conary import versions

VER = '/localhost@rpl:linux/1.0-1-1'
FROZEN = '/localhost@rpl:linux/1.0:1-1-1'


@pytest.mark.parametrize('fn, text', [
    (versions.VersionFromString, VER),
    (versions.ThawVersion, FROZEN),
])
def test_str_and_bytes_equal(fn, text):
    from_str = fn(text)
    from_bytes = fn(text.encode('ascii'))
    assert from_str.asString() == from_bytes.asString()
    assert from_str == from_bytes
