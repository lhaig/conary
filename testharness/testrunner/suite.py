"""Minimal TestSuite so the root testsuite.py imports and constructs.

The real runner arrives with the pytest integration; until then setup(),
main() and run() raise NotImplementedError and the hooks testsuite.py
overrides are no-ops.
"""


class TestSuite:
    __test__ = False
    testsuite_module = None
    topLevelStrip = 0

    def setupPaths(self):
        pass

    def sortTests(self, tests):
        return tests

    def getCoverageDirs(self, handler, environ):
        return []

    def getCoverageExclusions(self, handler, environ):
        return []

    def setup(self):
        raise NotImplementedError('use pytest to run conary_test')

    def main(self, *args, **kw):
        raise NotImplementedError('use pytest to run conary_test')

    def run(self, *args, **kw):
        raise NotImplementedError('use pytest to run conary_test')
