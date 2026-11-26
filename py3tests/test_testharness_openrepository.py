"""conary_test.rephelp.openRepository against the SQLite + stdlib harness."""
import os

import pytest

from conary_test import rephelp


class OpenRepositoryTest(rephelp.RepositoryHelper):

    def testOpenAndRead(self):
        repos = self.openRepository()
        server = self.servers.getServer(0)
        assert server.appServer.isStarted()
        assert server.getUrl() == server.appServer.getProxyTo() + '/conary/'
        assert repos.getRoles('localhost') == ['test']
        assert repos.troveNames(self.defLabel) == []
        assert repos.getRoles('localhost') == ['test']
        assert 'test' in repos.listRoles('localhost')

    def testServerErrorLogStaysClean(self):
        self.openRepository()
        server = self.servers.getServer(0)
        with open(server.appServer.errorLog) as f:
            assert 'Traceback' not in f.read()

    def testRepositoryDatabaseIsTheHarnessFile(self):
        self.openRepository()
        server = self.servers.getServer(0)
        db = server.reposDB
        assert os.path.exists(db.path)
        cu = db.connect().cursor()
        cu.execute("select userName from Users where userName = 'test'")
        assert cu.fetchall() == [('test',)]

    @pytest.mark.xfail(strict=True, raises=TypeError,
                       reason='task 3.16: changeset file container still '
                              'writes str names/tags to a binary file')
    def testCommitAndReadBack(self):
        repos = self.openRepository()
        self.addComponent('foo:runtime', '1.0',
                          fileContents=[('/usr/bin/foo', 'contents\n')])
        assert repos.troveNames(self.defLabel) == ['foo:runtime']
        trv = repos.getTrove(*self.findAndGetTrove('foo:runtime').getNameVersionFlavor())
        assert [x[1] for x in trv.iterFileList()] == ['/usr/bin/foo']
