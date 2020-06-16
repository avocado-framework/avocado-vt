"""
Module for defining the capabilities of vm.

Available class:
- Flags: Enumerate of the flags of VM capabilities.
- Capabilities: Representation of VM capabilities.
"""

from itertools import count

ID_COUNTER = count()


def _auto_value():
    return next(ID_COUNTER)


class Flags(object):
    """ Enumerate the flags of VM capabilities. """

    BLOCKDEV = _auto_value()
    SMP_DIES = _auto_value()
    INCOMING_DEFER = _auto_value()


class Capabilities(object):
    """ Representation of VM capabilities. """

    def __init__(self):
        self._flags = set()

    def set_flag(self, flag):
        """
        Set the flag.

        :param flag: The name of flag.
        :type flag: Flags
        """
        self._flags.add(flag)

    def clear_flag(self, flag):
        """
        Clear the flag.

        :param flag: The name of flag.
        :type flag: Flags
        """
        self._flags.remove(flag)

    def __contains__(self, flag):
        return flag in self._flags
