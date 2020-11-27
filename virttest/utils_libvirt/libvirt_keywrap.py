"""
Module to contain logic testing protected key module 'pkey'
"""
import logging
import os

from virttest.utils_misc import cmd_status_output


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
        error, output = cmd_status_output("modprobe %s" % self.module_name)
        if error:
            logging.debug("Error loading module 'pkey': %s", output)
            return False
        return True

    def get_some_aes_key_token(self):
        """
        Guests some aes key token

        :return: key token string
        """
        some_key_attribute = "protkey_aes_128"
        attr_path = os.path.join(self.sysfs, some_key_attribute)
        error, output = cmd_status_output("cat %s" % attr_path)
        if error:
            logging.debug("Error reading from %s: %s", attr_path, output)
            return None
        return output
