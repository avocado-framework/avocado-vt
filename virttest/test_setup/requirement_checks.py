from avocado.core import exceptions
from avocado.utils import path

from virttest import utils_misc
from virttest.test_setup.core import Setuper

version_info = {}


class CheckInstalledCMDs(Setuper):
    def setup(self):
        # throw a TestSkipError exception if command requested by test is not
        # installed.
        if self.params.get("cmds_installed_host"):
            for cmd in self.params.get("cmds_installed_host").split():
                try:
                    path.find_command(cmd)
                except path.CmdNotFoundError as msg:
                    raise exceptions.TestSkipError(msg)

    def cleanup(self):
        pass


class CheckRunningAsRoot(Setuper):
    def setup(self):
        # Verify if this test does require root or not. If it does and the
        # test suite is running as a regular user, we shall just throw a
        # TestSkipError exception, which will skip the test.
        if self.params.get("requires_root", "no") == "yes":
            utils_misc.verify_running_as_root()

    def cleanup(self):
        pass
