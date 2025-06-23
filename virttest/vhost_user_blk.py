"""
This module provides interfaces about vhost-user-blk storage backend.

Available functions:
- get_image_filename: Get the device path from vhost-user-blk.

"""

import os
import stat


def get_image_filename(params):
    """
    Get the device path from vhost-user-blk.
    NOTE: the vhost-user-blk protocol is a customized-private protocol
          instead of a standard protocol.

    :param params: Dictionary containing the test parameters
    :type name: dict
    :return: The path in virtio-blk-vhost-user protocol
             e.g: vhost-user-blk:///tmp/vhost-user-blk1.sock
    :rtype: str
    """
    sock_path = params.get("image_name")
    mode = os.stat(sock_path).st_mode
    if stat.S_ISSOCK(mode):
        return "vhost-user-blk://%s" % sock_path
