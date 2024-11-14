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
    """Enumerate the flags of VM capabilities."""

    BLOCKDEV = _auto_value()
    SMP_DIES = _auto_value()
    SMP_CLUSTERS = _auto_value()
    SMP_DRAWERS = _auto_value()
    SMP_BOOKS = _auto_value()
    INCOMING_DEFER = _auto_value()
    MACHINE_MEMORY_BACKEND = _auto_value()
    MIGRATION_PARAMS = _auto_value()
    SEV_GUEST = _auto_value()
    SNP_GUEST = _auto_value()
    TDX_GUEST = _auto_value()
    FLOPPY_DEVICE = _auto_value()
    BLOCKJOB_BACKING_MASK_PROTOCOL = _auto_value()


class MigrationParams(object):
    """Enumerate migration parameters."""

    DOWNTIME_LIMIT = _auto_value()
    MAX_BANDWIDTH = _auto_value()
    XBZRLE_CACHE_SIZE = _auto_value()


class Capabilities(object):
    """Representation of VM capabilities."""

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
