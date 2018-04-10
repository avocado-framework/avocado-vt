"""Utility functions to handle block related actions."""

from . import qemu_monitor


def get_block_virtual_size(dev_name):
    """
    Get block virtual-size of specified block device with dev_name.

    :param dev_name: block device name, like "drive-hotadd" etc.
    :return: Matched block device virual size.
             The default unit of the size is Byte.
             eg: disk image is 30G, should return 32212254720.
    """
    blocks_info = qemu_monitor.info("block")
    for dict_block in blocks_info:
        if dev_name == dict_block['device']:
            size = dict_block['inserted']['image']['virtual-size']
            return int(size)
