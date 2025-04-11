"""
This module provides interfaces about vdpa storage backend.

Available functions:
- get_image_filename: Get the device path from vdpa.

"""

from virttest import utils_vdpa


def get_image_filename(name):
    """
    Get the device path from vdpa.
    NOTE: the vdpa protocol is a customized-private protocol
          instead of a standard protocol.

    :param name: the name of device
    :type name: str
    :return: The path from vdpa in vpda protocol
             e.g: vdpa:///dev/vhost-vdpa
    :rtype: str
    """
    path = utils_vdpa.get_vdpa_dev_file_by_name(name)
    return "vdpa://%s" % path
