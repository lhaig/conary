"""CM.iterFormat with a mix of parsed (int index) and new (None index) ops."""
from conary.conaryclient import cml
from conary.deps import deps


class _Cfg:
    installLabelPath = ['a@b:c', 'd@e:f']
    flavor = deps.parseFlavor('')
    root = '/'
    modelPath = '/etc/conary/system-model'


def _cml(lines):
    m = cml.CML(_Cfg())
    m.parse(fileData=lines)
    return m


def test_new_op_after_parsed_ops():
    m = _cml(['# comment\n', 'search foo\n', 'install bar\n'])
    m.appendOpByName('install', text='baz')
    assert m.format() == (
        '# comment\nsearch foo\ninstall bar\ninstall baz\n')


def test_new_noop_header_and_op():
    m = _cml(['search foo\n', 'install bar\n'])
    m.appendNoOpByText('# new header')
    m.appendOpByName('update', text='baz')
    assert list(m.iterFormat()) == [
        '# new header', 'search foo', 'install bar', 'update baz']


def test_only_new_entries():
    m = _cml([])
    m.appendNoOpByText('# header')
    m.appendOpByName('install', text='foo')
    assert m.format() == '# header\ninstall foo\n'


def test_modified_parsed_op_still_formatted():
    m = _cml(['install bar\n', 'install baz\n'])
    m.modelOps[0].modified = True
    m.appendNoOpByText('# tail')
    assert list(m.iterFormat()) == ['# tail', 'install bar', 'install baz']
