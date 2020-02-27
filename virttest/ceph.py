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

from virttest import utils_numeric
from virttest import error_context


class CephError(Exception):
    pass


@error_context.context_aware
def rbd_image_create(ceph_monitor, rbd_pool_name, rbd_image_name,
                     rbd_image_size, force_create=False,
                     ceph_conf=None, keyfile=None):
    """
    Create a rbd image.
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    :params rbd_image_size: The size of rbd image
    :params force_create: Force create the image or not
    :params ceph_conf: The path to the ceph configuration file
    :params keyfile: The path to the ceph keyring configuration file
    """
    create_image = True
    try:
        int(rbd_image_size)
        compare_str = rbd_image_size
    except ValueError:
        compare_str = utils_numeric.normalize_data_size(rbd_image_size, 'M')

    if rbd_image_exist(ceph_monitor, rbd_pool_name, rbd_image_name,
                       ceph_conf, keyfile):
        create_image = False
        image_info = rbd_image_info(ceph_monitor, rbd_pool_name,
                                    rbd_image_name, ceph_conf, keyfile)
        if image_info['size'] != compare_str or force_create:
            rbd_image_rm(ceph_monitor, rbd_pool_name, rbd_image_name,
                         ceph_conf, keyfile)
            create_image = True

    if create_image:
        cmd = "rbd {opts} create {pool}/{image} {size} {keyring}"
        c_opt = '-c %s' % ceph_conf if ceph_conf else ''
        m_opt = '-m %s' % ceph_monitor if ceph_monitor else ''
        opts = m_opt + ' ' + c_opt
        size = '-s %d' % utils_numeric.align_value(compare_str, 1)
        keyring = '--keyring %s' % keyfile if keyfile else ''
        cmd = cmd.format(opts=opts, pool=rbd_pool_name,
                         image=rbd_image_name, size=size, keyring=keyring)
        process.system(cmd, verbose=True)
    else:
        logging.debug("Image already exist skip the create.")


@error_context.context_aware
def rbd_image_rm(ceph_monitor, rbd_pool_name, rbd_image_name,
                 ceph_conf=None, keyfile=None):
    """
    Remove a rbd image
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    :params ceph_conf: The path to the ceph configuration file
    :params keyfile: The path to the ceph keyring configuration file
    """
    if rbd_image_exist(ceph_monitor, rbd_pool_name, rbd_image_name,
                       ceph_conf, keyfile):
        cmd = "rbd {opts} rm {pool}/{image} {keyring}"
        c_opt = '-c %s' % ceph_conf if ceph_conf else ''
        m_opt = '-m %s' % ceph_monitor if ceph_monitor else ''
        opts = m_opt + ' ' + c_opt
        keyring = '--keyring %s' % keyfile if keyfile else ''
        cmd = cmd.format(opts=opts, pool=rbd_pool_name, image=rbd_image_name,
                         keyring=keyring)
        process.system(cmd, verbose=True)
    else:
        logging.debug("Image not exist, skip to remove it.")


@error_context.context_aware
def rbd_image_exist(ceph_monitor, rbd_pool_name, rbd_image_name,
                    ceph_conf=None, keyfile=None):
    """
    Check if rbd image is exist
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    :params ceph_conf: The path to the ceph configuration file
    :params keyfile: The path to the ceph keyring configuration file
    """
    cmd = "rbd {opts} ls {pool} {keyring}"
    c_opt = '-c %s' % ceph_conf if ceph_conf else ''
    m_opt = '-m %s' % ceph_monitor if ceph_monitor else ''
    opts = m_opt + ' ' + c_opt
    keyring = '--keyring %s' % keyfile if keyfile else ''
    cmd = cmd.format(opts=opts, pool=rbd_pool_name, keyring=keyring)
    output = process.run(cmd, ignore_status=True,
                         verbose=True).stdout_text

    logging.debug("Response from rbd ls command is: %s" % output)

    return (rbd_image_name.strip() in output.splitlines())


@error_context.context_aware
def rbd_image_info(ceph_monitor, rbd_pool_name, rbd_image_name,
                   ceph_conf=None, keyfile=None):
    """
    Get information of a rbd image
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    :params ceph_conf: The path to the ceph configuration file
    :params keyfile: The path to the ceph keyring configuration file
    """
    cmd = "rbd {opts} info {pool}/{image} {keyring}"
    c_opt = '-c %s' % ceph_conf if ceph_conf else ''
    m_opt = '-m %s' % ceph_monitor if ceph_monitor else ''
    opts = m_opt + ' ' + c_opt
    keyring = '--keyring %s' % keyfile if keyfile else ''
    cmd = cmd.format(opts=opts, pool=rbd_pool_name, image=rbd_image_name,
                     keyring=keyring)
    output = process.system(cmd)
    info_pattern = "rbd image \'%s\':.*?$" % rbd_image_name

    rbd_image_info_str = re.findall(info_pattern, output, re.S)[0]

    rbd_image_info = {}
    for rbd_image_line in rbd_image_info_str.splitlines():
        if ":" not in rbd_image_line:
            if "size" in rbd_image_line:
                size_str = re.findall("size\s+(\d+\s+\w+)\s+",
                                      rbd_image_line)[0]
                size = utils_numeric.normalize_data_size(size_str, 'M')
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
    output = process.system_output(cmd, verbose=True).stdout_text
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
    output = process.system_output(cmd, verbose=True).stdout_text
    if os.path.exist(os.path.join("/dev/rbd", rbd_pool_name, rbd_image_name)):
        logging.debug("Failed to unmap image from local: %s" % output)


@error_context.context_aware
def get_image_filename(ceph_monitor, rbd_pool_name, rbd_image_name,
                       ceph_conf=None):
    """
    Configuration has already been configured in the conf file
    Return the rbd image file name
    :params ceph_monitor: The specified monitor to connect to
    :params rbd_pool_name: The name of rbd pool
    :params rbd_image_name: The name of rbd image
    :params ceph_conf: The path to the ceph configuration file
    """
    uri = 'rbd:{pool}/{image}{opts}'
    conf_opt = ':conf=%s' % ceph_conf if ceph_conf else ''
    mon_opt = ':mon_host=%s' % ceph_monitor if ceph_monitor else ''
    opts = conf_opt + mon_opt
    return uri.format(pool=rbd_pool_name, image=rbd_image_name, opts=opts)


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
