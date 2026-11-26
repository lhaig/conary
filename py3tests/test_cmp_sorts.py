"""Sorts that passed a Python 2 comparison function by position."""
import functools
import inspect

import pytest

from conary.conaryclient import mirror
from conary.lib import graph
from conary.lib.compat import cmp
from conary.local import update as localupdate
from conary.repository.netrepos import cache


def _byItem(a, b):
    """nodeSort style comparator on (index, item) tuples."""
    return cmp(a[1], b[1])


def _diamond():
    g = graph.DirectedGraph()
    for n in 'abcd':
        g.addNode(n)
    g.addEdge('a', 'b')
    g.addEdge('a', 'c')
    g.addEdge('b', 'd')
    g.addEdge('c', 'd')
    return g


# --- NodeData sorting is not broken when no comparator is given ---------

@pytest.mark.parametrize('dataCls', [graph.NodeData, graph.NodeDataByHash])
def test_nodedata_sort_without_comparator(dataCls):
    nd = dataCls()
    for n in ('z', 'y', 'x'):
        nd.getIndex(n)
    assert nd.sort() == [(0, 'z'), (1, 'y'), (2, 'x')]


@pytest.mark.parametrize('dataCls', [graph.NodeData, graph.NodeDataByHash])
def test_nodedata_sort_with_comparator(dataCls):
    nd = dataCls()
    for n in ('z', 'y', 'x'):
        nd.getIndex(n)
    assert nd.sort(_byItem) == [(2, 'x'), (1, 'y'), (0, 'z')]


def test_nodedata_sort_subset_reverse_and_default():
    nd = graph.NodeData()
    for n in ('z', 'y', 'x', 'w'):
        nd.getIndex(n)
    assert nd.sortSubset([3, 1, 2]) == [(1, 'y'), (2, 'x'), (3, 'w')]
    assert nd.sortSubset([3, 1, 2], reverse=True) == [
        (3, 'w'), (2, 'x'), (1, 'y')]
    assert nd.sortSubset([0, 1, 2], _byItem) == [(2, 'x'), (1, 'y'), (0, 'z')]
    assert nd.sortSubset([0, 1, 2], _byItem, reverse=True) == [
        (0, 'z'), (1, 'y'), (2, 'x')]


# --- DFS / BFS / total ordering / SCC -----------------------------------

def test_doDFS_without_nodesort():
    g = _diamond()
    starts, finishes, trees = g.doDFS()
    assert len(starts) == len(finishes) == 4
    # children are visited in insertion order
    assert _dfsOrder(g) == ['a', 'b', 'd', 'c']


def _dfsOrder(g, **kw):
    starts, finishes, trees = g.doDFS(**kw)
    return [g.get(i) for i in sorted(starts, key=starts.get)]


def test_doDFS_with_nodesort_picks_requested_order():
    g = _diamond()
    assert _dfsOrder(g, nodeSort=_byItem) == ['a', 'b', 'd', 'c']
    desc = lambda a, b: -_byItem(a, b)
    assert _dfsOrder(g, nodeSort=desc) == ['d', 'c', 'b', 'a']


def _bfsOrder(g, **kw):
    starts = g.doBFS(**kw)[0]
    return [g.get(i) for i in sorted(starts, key=starts.get)]


def test_doBFS_with_and_without_nodesort():
    g = _diamond()
    starts, _, _, _, depth = g._walk(dfs=False)
    assert depth[g.getIndex('d')] == 2
    desc = lambda a, b: -_byItem(a, b)
    asc = _bfsOrder(g, nodeSort=_byItem)
    assert asc == ['a', 'b', 'c', 'd']
    assert _bfsOrder(g, nodeSort=desc) == ['d', 'c', 'b', 'a']
    assert _bfsOrder(g) == ['a', 'b', 'c', 'd']


def test_getTotalOrdering_default_and_sorted():
    g = _diamond()
    ordered = g.getTotalOrdering()
    assert ordered.index('a') < ordered.index('b') < ordered.index('d')
    assert ordered.index('a') < ordered.index('c') < ordered.index('d')
    # nodeSort breaks ties: smallest wins
    assert g.getTotalOrdering(nodeSort=_byItem) == ['a', 'b', 'c', 'd']
    assert g.getTotalOrdering(
        nodeSort=lambda a, b: -_byItem(a, b)) == ['a', 'c', 'b', 'd']


def test_getTotalOrdering_nodesort_contract_is_comparator():
    # nodeSort stays a two argument comparison function, not a key
    sig = inspect.signature(graph.DirectedGraph.getTotalOrdering)
    assert list(sig.parameters) == ['self', 'nodeSort']
    g = _diamond()
    calls = []

    def sort(a, b):
        calls.append((a, b))
        return _byItem(a, b)
    g.getTotalOrdering(nodeSort=sort)
    assert calls and all(len(c) == 2 for c in calls)


def test_getStronglyConnectedComponents():
    g = graph.DirectedGraph()
    for n in 'abcde':
        g.addNode(n)
    g.addEdge('a', 'b')
    g.addEdge('b', 'a')
    g.addEdge('b', 'c')
    g.addEdge('c', 'd')
    g.addEdge('d', 'c')
    g.addEdge('d', 'e')
    comps = g.getStronglyConnectedComponents()
    assert sorted(sorted(c) for c in comps) == [['a', 'b'], ['c', 'd'], ['e']]
    # no strongly connected component spans the condensation order
    pos = {n: i for i, c in enumerate(comps) for n in c}
    assert pos['a'] < pos['c'] < pos['e']


def test_getTotalOrdering_back_edge():
    g = graph.DirectedGraph()
    g.addNode('a')
    g.addNode('b')
    g.addEdge('a', 'b')
    g.addEdge('b', 'a')
    with pytest.raises(graph.BackEdgeError):
        g.getTotalOrdering()


# --- mirror.py -----------------------------------------------------------

def _py2TroveListSort(troveList):
    """Reference implementation of the Python 2 lambda comparator."""
    def c(a, b):
        return (cmp(a[0], b[0]) or cmp(a[1][1], b[1][1]) or
                cmp(a[1][2], b[1][2]) or cmp(b[1][0], a[1][0]))
    return sorted(troveList, key=functools.cmp_to_key(c))


def test_mirror_trove_list_order_mark_version_flavor_reverse_name():
    tl = [
        (2, ('a', 'v1', 'f1')),
        (1, ('a', 'v2', 'f1')),
        (1, ('a', 'v1', 'f2')),
        (1, ('a', 'v1', 'f1')),
        (1, ('b', 'v1', 'f1')),     # same mark/version/flavor: name reversed
        (1, ('c', 'v1', 'f1')),
        (1, ('a:run', 'v1', 'f1')),
    ]
    got = sorted(tl, key=functools.cmp_to_key(mirror._troveListCmp))
    assert [x[1][0] for x in got[:4]] == ['c', 'b', 'a:run', 'a']
    assert got[4] == (1, ('a', 'v1', 'f2'))
    assert got[5] == (1, ('a', 'v2', 'f1'))
    assert got[6][0] == 2
    assert got == _py2TroveListSort(tl)


def test_mirror_trove_list_exact_ties_are_stable():
    tl = [(1, ('a', 'v', 'f'), 'first'), (1, ('a', 'v', 'f'), 'second')]
    got = sorted(tl, key=functools.cmp_to_key(mirror._troveListCmp))
    assert [x[2] for x in got] == ['first', 'second']


def test_group_troves_order():
    tl = [
        (5, ('foo:run', 'v3', 'f')),
        (1, ('foo:run', 'v1', 'f')),
        (5, ('group-x', 'v4', 'f')),      # same mark as v3, holds a group
        (5, ('foo:lib', 'v3', 'f')),
        (2, ('foo:run', 'v2', 'f')),
    ]
    got = mirror.groupTroves(tl)
    # ascending first mark; at equal mark the group-holding set goes last
    assert [g[0][1][1] for g in got] == ['v1', 'v2', 'v3', 'v4']
    assert [len(g) for g in got] == [1, 1, 2, 1]
    assert [x[1][0] for x in got[2]] == ['foo:run', 'foo:lib']


# --- netrepos cache ------------------------------------------------------

def test_dumbcache_shrink_skips_none_and_removes_latest_expiry():
    c = cache.DumbCache(limit=200)
    dict.__setitem__(c, 'forever', ('v', None))
    for i in range(204):
        dict.__setitem__(c, i, (i, 1000.0 + i))
    c._shrink()
    # limit // 10 == 20 entries with the latest expiry are dropped
    assert all(i not in c for i in range(184, 204))
    assert 183 in c
    assert 'forever' in c
    assert len(c) == 205 - 20


def test_dumbcache_shrink_tie_order_is_stable():
    c = cache.DumbCache(limit=200)
    for i in range(205):
        dict.__setitem__(c, i, (i, 5.0))
    c._shrink()
    # equal expiry: original order is kept, so the first 20 go
    assert all(i not in c for i in range(20))
    assert 20 in c


# --- local/update.py _InfoFile ------------------------------------------

def test_infofile_lines_sorted_numerically_on_id(tmp_path):
    root = str(tmp_path)
    (tmp_path / 'etc').mkdir()
    info = localupdate._InfoFile(root, '/etc/passwd', 0, 2, None,
                                 ['root', '*', '0', '0', 'root', '/root',
                                  '/bin/bash'])
    info._lines = [['b', '*', '10'], ['a', '*', '9'], ['c', '*', '100']]
    info._modified = True
    info.write()
    lines = (tmp_path / 'etc' / 'passwd').read_text().splitlines()
    assert [l.split(':')[2] for l in lines] == ['9', '10', '100']
