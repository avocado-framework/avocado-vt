"""
CEPH Support
This file has the functions that helps
* To create rbd pool
* To map/unmap rbd pool
* To mount/umount cephfs to localhost
* To return rbd uri which can be used as disk image file path.
"""

import logging
import os
import re

from avocado.utils import process

from virttest import utils_misc
from virttest import error_context
from virttest.compat_52lts import decode_to_text


class CephError(Exception):
    pass


@error_context.context_aware
def rbd_image_create(ceph_monitor, rbd_pool_name, rbd_image_name,
                     rbd_image_size, force_create=False):
    """
    Create a rbd image.
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    :params rbd_image_size: The size of rbd image
    :params force_create: Force create the image or not
    """
    if rbd_image_exist(ceph_monitor, rbd_pool_name, rbd_image_name):
        create_image = False
        image_info = rbd_image_info(ceph_monitor, rbd_pool_name,
                                    rbd_image_name)
        try:
            int(rbd_image_size)
            compare_str = rbd_image_size
        except ValueError:
            compare_str = utils_misc.normalize_data_size(rbd_image_size)
        if image_info['size'] != compare_str or force_create:
            rbd_image_rm(ceph_monitor, rbd_pool_name, rbd_image_name)
            create_image = True
    if create_image:
        cmd = "rbd create %s/%s -m %s" % (rbd_pool_name, rbd_image_name,
                                          ceph_monitor)
        process.system(cmd, verbose=True)
    else:
        logging.debug("Image already exist skip the create.")


@error_context.context_aware
def rbd_image_rm(ceph_monitor, rbd_pool_name, rbd_image_name):
    """
    Remove a rbd image
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    """
    if rbd_image_exist(ceph_monitor, rbd_pool_name, rbd_image_name):
        cmd = "rbd rm %s/%s -m %s" % (rbd_pool_name, rbd_image_name,
                                      ceph_monitor)
        process.system(cmd, verbose=True)
    else:
        logging.debug("Image not exist, skip to remove it.")


@error_context.context_aware
def rbd_image_exist(ceph_monitor, rbd_pool_name, rbd_image_name):
    """
    Check if rbd image is exist
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    """
    cmd = "rbd ls %s -m %s" % (rbd_pool_name, ceph_monitor)
    output = decode_to_text(process.system_output(cmd, ignore_status=True,
                                                  verbose=True))

    logging.debug("Resopense from rbd ls command is: %s" % output)

    return (rbd_image_name.strip() in output.splitlines())


@error_context.context_aware
def rbd_image_info(ceph_monitor, rbd_pool_name, rbd_image_name):
    """
    Get information of a rbd image
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    """
    cmd = "rbd info %s/%s -m %s" % (rbd_pool_name, rbd_image_name,
                                    ceph_monitor)
    output = process.system(cmd)
    info_pattern = "rbd image \'%s\':.*?$" % rbd_image_name

    rbd_image_info_str = re.findall(info_pattern, output, re.S)[0]

    rbd_image_info = {}
    for rbd_image_line in rbd_image_info_str.splitlines():
        if ":" not in rbd_image_line:
            if "size" in rbd_image_line:
                size_str = re.findall("size\s+(\d+\s+\w+)\s+",
                                      rbd_image_line)[0]
                size = utils_misc.normalize_data_size(size_str)
                rbd_image_info['size'] = size
            if "order" in rbd_image_line:
                rbd_image_info['order'] = int(re.findall("order\s+(\d+)",
                                                         rbd_image_line))
        else:
            tmp_str = rbd_image_line.strip().split(":")
            rbd_image_info[tmp_str[0]] = tmp_str[1]
    return rbd_image_info


@error_context.context_aware
def rbd_image_map(ceph_monitor, rbd_pool_name, rbd_image_name):
    """
    Maps the specified image to a block device via rbd kernel module
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    """
    cmd = "rbd map %s --pool %s -m %s" % (rbd_image_name, rbd_pool_name,
                                          ceph_monitor)
    output = decode_to_text(process.system_output(cmd, verbose=True))
    if os.path.exist(os.path.join("/dev/rbd", rbd_pool_name, rbd_image_name)):
        return os.path.join("/dev/rbd", rbd_pool_name, rbd_image_name)
    else:
        logging.debug("Failed to map image to local: %s" % output)
        return None


@error_context.context_aware
def rbd_image_unmap(rbd_pool_name, rbd_image_name):
    """
    Unmaps the block device that was mapped via the rbd kernel module
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    """
    cmd = "rbd unmap /dev/rbd/%s/%s" % (rbd_pool_name, rbd_image_name)
    output = decode_to_text(process.system_output(cmd, verbose=True))
    if os.path.exist(os.path.join("/dev/rbd", rbd_pool_name, rbd_image_name)):
        logging.debug("Failed to unmap image from local: %s" % output)


@error_context.context_aware
def get_image_filename(ceph_monitor, rbd_pool_name, rbd_image_name):
    """
    Return the rbd image file name
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    """
    return "rbd:%s/%s:mon_host=%s" % (rbd_pool_name, rbd_image_name,
                                      ceph_monitor)


@error_context.context_aware
def create_config_file(ceph_monitor):
    """
    Create an ceph config file when the config file is not exist
    :params ceph_monitor: The specified monitor to connect to
    """
    ceph_dir = "/etc/ceph"
    ceph_cfg = os.path.join(ceph_dir, "ceph.conf")
    if not os.path.exists(ceph_dir):
        os.makedirs(ceph_dir)
    if not os.path.exists(ceph_cfg):
        with open(ceph_cfg, 'w+') as f:
            f.write('mon_host = %s' % ceph_monitor)
        return ceph_cfg
