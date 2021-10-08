"""
Module to contain logic testing protected key module 'pkey'
"""
import logging
import os

from avocado.utils import process

LOG = logging.getLogger('avocado.' + __name__)


class ProtectedKeyHelper(object):
    """
    Helper class to test for protected key support on s390x
    """

    def __init__(self, session=None):
        self.session = session
        self.sysfs = "/sys/devices/virtual/misc/pkey/protkey"
        self.module_name = "pkey"

    def load_module(self):
        """
        Loads pkey module

        :return: If there were errors loading the module
        """
        error, output = cmd_status_output(cmd="modprobe %s" % self.module_name,
                                          session=self.session)
        if error:
            LOG.debug("Error loading module 'pkey': %s", output)
            return False
        return True

    def get_some_aes_key_token(self):
        """
        Guests some aes key token

        :return: key token string
        """
        some_key_attribute = "protkey_aes_128"
        attr_path = os.path.join(self.sysfs, some_key_attribute)
        error, output = cmd_status_output(cmd="hexdump %s" % attr_path,
                                          session=self.session)
        if error or "No such device" in output:
            LOG.debug("Error reading from %s: %s", attr_path, output)
            return None
        return output


def cmd_status_output(cmd, session=None, timeout=60):
    """
    Function to unify usage of process and ShellSession"

    :param cmd: Command to issue.
    :param session: Guest session. If empty, command is executed on host.
    """

    status = None
    stdout = None
    if session:
        status, stdout = session.cmd_status_output(cmd, timeout=timeout)
    else:
        result = process.run(cmd, shell=False, ignore_status=True,
                             verbose=True, timeout=timeout)
        status = result.exit_status
        stdout = result.stdout
    return status, stdout
