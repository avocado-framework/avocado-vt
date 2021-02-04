"""
libvirt disk related utility functions
"""

from avocado.core import exceptions

from virttest import utils_misc
from virttest.utils_test import libvirt


def create_disk(disk_type, path=None, size="500M", disk_format="raw", extra='',
                session=None):
    """
    Create disk on local or remote

    :param disk_type: Disk type
    :param path: The path of disk
    :param size: The size of disk
    :param disk_format: The format of disk
    :param extra: Extra parameters
    :param session： Session object to a remote host or guest
    :return: The path of disk
    :raise: TestError if the disk can't be created
    """

    if session:
        if disk_type == "file":
            disk_cmd = ("qemu-img create -f %s %s %s %s"
                        % (disk_format, extra, path, size))
        else:
            # TODO: Add implementation for other types
            raise exceptions.TestError("Unknown disk type %s" % disk_type)

        status, stdout = utils_misc.cmd_status_output(disk_cmd, session=session)
        if status:
            raise exceptions.TestError("Failed to create img on remote: cmd: {} "
                                       "status: {}, stdout: {}"
                                       .format(disk_cmd, status, stdout))
        return path
    else:
        return libvirt.create_local_disk(disk_type, path=path, size=size,
                                         disk_format=disk_format, extra=extra)
