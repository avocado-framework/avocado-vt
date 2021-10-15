"""
High-level libvirt ceph utility functions.

This module is meant to reduce code size by performing common ceph setup procedures.
:author: Chunfu Wen <chwen@redhat.com>
:copyright: 2021 Red Hat Inc.
"""

import logging
import os

from avocado.core import exceptions
from avocado.utils import process

from virttest import ceph
from virttest import data_dir
from virttest import utils_package
from virttest import virsh

from virttest.utils_test import libvirt
from virttest.utils_libvirt import libvirt_disk

from virttest.libvirt_xml import vm_xml

LOG = logging.getLogger('avocado.' + __name__)


def _create_secret(auth_sec_usage_type, ceph_auth_key):
    """
    Setup secret with auth

    :param auth_sec_usage_type: auth secret usage
    :param ceph_auth_key: ceph auth key
    :return: auth secret uuid
    """
    auth_sec_dict = {"sec_usage": auth_sec_usage_type,
                     "sec_name": "ceph_auth_secret"}
    auth_sec_uuid = libvirt.create_secret(auth_sec_dict)
    virsh.secret_set_value(auth_sec_uuid, ceph_auth_key,
                           debug=True)
    return auth_sec_uuid


def _create_image(device_format, img_file, vm_name, storage_size,
                  ceph_disk_name, ceph_mon_ip, key_opt,
                  ceph_auth_user, ceph_auth_key):
    """
    Creates image on ceph
    :param device_format: device format
    :param img_file: image file
    :param vm_name: vm name
    :param storage_size: storage size
    :param ceph_disk_name: ceph disk name
    :param ceph_mon_ip: ceph host ip
    :param key_opt: key option
    :param ceph_auth_user: ceph auth user
    :param ceph_auth_key: ceph auth key
    """
    #Create necessary image file if not exists
    if img_file is None:
        img_file = os.path.join(data_dir.get_data_dir(),
                                "%s_test.img" % vm_name)
        # Create an local image and make FS on it.
        disk_cmd = ("qemu-img create -f %s %s %s" %
                    (device_format, img_file, storage_size))
        process.run(disk_cmd, ignore_status=False, shell=True)
    # Convert the image to remote ceph storage
    disk_path = ("rbd:%s:mon_host=%s" %
                 (ceph_disk_name, ceph_mon_ip))
    if ceph_auth_user and ceph_auth_key:
        disk_path += (":id=%s:key=%s" %
                      (ceph_auth_user, ceph_auth_key))
    rbd_cmd = ("rbd -m %s %s info %s 2> /dev/null|| qemu-img convert -O"
               " %s %s %s" % (ceph_mon_ip, key_opt, ceph_disk_name,
                              device_format, img_file, disk_path))
    process.run(rbd_cmd, ignore_status=False, shell=True, verbose=True)


def create_or_cleanup_ceph_backend_vm_disk(vm, params, is_setup=True):
    """
    Setup vm ceph disk with given parameters

    :param vm: the vm object
    :param params: dict, dict include setup vm disk xml configurations
    :param is_setup: one parameter indicate whether setup or clean up
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm.name)
    LOG.debug("original xml is: %s", vmxml)

    # Device related configurations
    device_format = params.get("virt_disk_device_format", "raw")
    device_bus = params.get("virt_disk_device_bus", "virtio")
    device = params.get("virt_disk_device", "disk")
    device_target = params.get("virt_disk_device_target", "vdb")
    hotplug = "yes" == params.get("virt_disk_device_hotplug", "no")
    keep_raw_image_as = "yes" == params.get("keep_raw_image_as", "no")

    # Ceph related configurations
    ceph_mon_ip = params.get("ceph_mon_ip", "EXAMPLE_MON_HOST")
    ceph_host_port = params.get("ceph_host_port", "EXAMPLE_PORTS")
    ceph_disk_name = params.get("ceph_disk_name", "EXAMPLE_SOURCE_NAME")
    ceph_client_name = params.get("ceph_client_name")
    ceph_client_key = params.get("ceph_client_key")
    ceph_auth_user = params.get("ceph_auth_user")
    ceph_auth_key = params.get("ceph_auth_key")
    auth_sec_usage_type = params.get("ceph_auth_sec_usage_type", "ceph")
    storage_size = params.get("storage_size", "1G")
    img_file = params.get("ceph_image_file")
    attach_option = params.get("virt_device_attach_option", "--live")
    key_file = os.path.join(data_dir.get_tmp_dir(), "ceph.key")
    key_opt = ""
    is_local_img_file = True if img_file is None else False
    rbd_key_file = None

    # Prepare a blank params to confirm if delete the configure at the end of the test
    ceph_cfg = ""
    disk_auth_dict = None
    auth_sec_uuid = None
    names = ceph_disk_name.split('/')
    pool_name = names[0]
    image_name = names[1]
    if not utils_package.package_install(["ceph-common"]):
        raise exceptions.TestError("Failed to install ceph-common")

    # Create config file if it doesn't exist
    ceph_cfg = ceph.create_config_file(ceph_mon_ip)
    # If enable auth, prepare a local file to save key
    if ceph_client_name and ceph_client_key:
        with open(key_file, 'w') as f:
            f.write("[%s]\n\tkey = %s\n" %
                    (ceph_client_name, ceph_client_key))
        key_opt = "--keyring %s" % key_file
        rbd_key_file = key_file
    if is_setup:
        # If enable auth, prepare disk auth
        if ceph_client_name and ceph_client_key:
            auth_sec_uuid = _create_secret(auth_sec_usage_type, ceph_auth_key)
            disk_auth_dict = {"auth_user": ceph_auth_user,
                              "secret_type": auth_sec_usage_type,
                              "secret_uuid": auth_sec_uuid}
        # clean up image file if exists
        ceph.rbd_image_rm(ceph_mon_ip, pool_name,
                          image_name, keyfile=rbd_key_file)

        #Create necessary image file if not exists
        _create_image(device_format, img_file, vm.name, storage_size,
                      ceph_disk_name, ceph_mon_ip, key_opt,
                      ceph_auth_user, ceph_auth_key)

        # Disk related config
        disk_src_dict = {"attrs": {"protocol": "rbd",
                                   "name": ceph_disk_name},
                         "hosts":  [{"name": ceph_mon_ip,
                                     "port": ceph_host_port}]}
        # Create network disk
        disk_xml = libvirt_disk.create_primitive_disk_xml("network", device, device_target, device_bus,
                                                          device_format, disk_src_dict, disk_auth_dict)
        if not keep_raw_image_as:
            if hotplug:
                virsh.attach_device(vm.name, disk_xml.xml,
                                    flagstr=attach_option, ignore_status=False, debug=True)
            else:
                vmxml = vm_xml.VMXML.new_from_dumpxml(vm.name)
                vmxml.add_device(disk_xml)
                vmxml.sync()
    else:
        ceph.rbd_image_rm(ceph_mon_ip, pool_name,
                          image_name, keyfile=rbd_key_file)
        # Remove ceph config and key file if created.
        for file_path in [ceph_cfg, key_file]:
            if os.path.exists(file_path):
                os.remove(file_path)
        if is_local_img_file and img_file and os.path.exists(img_file):
            libvirt.delete_local_disk("file", img_file)
        if auth_sec_uuid:
            virsh.secret_undefine(auth_sec_uuid, ignore_status=True)
