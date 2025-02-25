"""
This module provides interfaces about vhost-user storage backend.

Available functions:
- get_image_filename: Get the device path from vhost-user.

"""


def get_image_filename(name):
    """
    Get the device path from vhost-user.
    NOTE: the vhost-user protocol is a customized-private protocol
          instead of a standard protocol.

    :param name: the name of device
    :type name: str
    :return: The path in virtio-blk-vhost-user protocol
             e.g: /tmp/vhost-user-blk1.sock
    :rtype: str
    """
    return name
