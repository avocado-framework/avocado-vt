from avocado.core import exceptions
from avocado.utils import path

from virttest.test_setup.core import Setuper


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
