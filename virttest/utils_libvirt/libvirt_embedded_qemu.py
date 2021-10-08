"""
Classes and functions for embedded qemu driver.
"""
import re
import logging

import aexpect
from avocado.core import exceptions
from avocado.utils import path
from avocado.utils import process

from virttest import utils_split_daemons
from virttest import utils_misc

try:
    path.find_command("virt-qemu-run")
    EMBEDDEDQEMU = "virt-qemu-run"
except path.CmdNotFoundError:
    EMBEDDEDQEMU = None

LOG = logging.getLogger('avocado.' + __name__)


class EmbeddedQemuSession(object):

    """
    Interaction embeddedQemu session can start a qemu process.
    """

    def __init__(self,
                 logging_handler=None,
                 logging_params=(),
                 logging_pattern=r'.*'):
        """
        :param logging_handler: Callback function to handle logging
        :param logging_params: Where log is stored
        :param logging_pattern: Regex for filtering specific log lines
        """
        if not utils_split_daemons.is_modular_daemon():
            raise exceptions.TestFail("Embedded qemu driver needs modular daemon mode.")
        self.tail = None
        self.running = False
        self.service_exec = "virt-qemu-run"
        cmd = "pgrep qemu | wc -l"
        self.qemu_pro_num = int(process.run(cmd, shell=True).stdout_text.strip())

        self.logging_handler = logging_handler
        self.logging_params = logging_params
        self.logging_pattern = logging_pattern

    def _output_handler(self, line):
        """
        Adapter output callback function.
        """
        if self.logging_handler is not None:
            if re.match(self.logging_pattern, line):
                self.logging_handler(line, *self.logging_params)

    def start(self, arg_str='', wait_for_working=True):
        """
        Start embeddedqemu session.

        :param arg_str: Argument passing to the session
        :param wait_for_working: Whether wait for embeddedqemu finish loading
        """
        self.tail = aexpect.Tail(
                "%s %s" % (self.service_exec, arg_str),
                output_func=self._output_handler,
            )
        self.running = True

        if wait_for_working:
            self.wait_for_working()

    def wait_for_working(self, timeout=60):
        """
        Wait for embeddedqemu to work.

        :param timeout: Max wait time
        """
        LOG.debug('Waiting for %s to work', self.service_exec)
        return utils_misc.wait_for(
            self.is_working,
            timeout=timeout,
        )

    def is_working(self):
        """
        Check if embeddedqemu is start by return status of 'virsh list'
        """
        cmd = 'pgrep qemu | wc -l'
        output = int(process.run(cmd, shell=True).stdout_text.strip())
        if output - self.qemu_pro_num == 2:
            self.running = True
            return True
        else:
            return False

    def exit(self):
        """
        Exit the embeddedqemu session.
        """
        if self.tail:
            self.tail.close()
