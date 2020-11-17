"""
High-level libvirt test utility functions.

This module is meant to reduce code size by performing common test procedures.
Generally, code here should look like test code.

More specifically:
    - Functions in this module should raise exceptions if things go wrong
    - Functions in this module typically use functions and classes from
      lower-level modules (e.g. utils_misc, qemu_vm, aexpect).
    - Functions in this module should not be used by lower-level linux_modules.
    - Functions in this module should be used in the right context.
      For example, a function should not be used where it may display
      misleading or inaccurate info or debug messages.

:copyright: 2014 Red Hat Inc.
"""

from __future__ import division
import re
import os
import ast
import logging
import shutil
import time
import sys
import aexpect
import platform
import random
import string

from aexpect import remote

from avocado.core import exceptions
from avocado.utils import path as utils_path
from avocado.utils import process
from avocado.utils import stacktrace
from avocado.utils import linux_modules
from avocado.utils import distro
from avocado.utils.astring import to_text

import six

from virttest import virsh
from virttest import xml_utils
from virttest import iscsi
from virttest import nfs
from virttest import utils_misc
from virttest import utils_selinux
from virttest import libvirt_storage
from virttest import utils_net
from virttest import gluster
from virttest import test_setup
from virttest import data_dir
from virttest import utils_libvirtd
from virttest import utils_config
from virttest import utils_split_daemons
from virttest import remote as remote_old
from virttest.staging import lv_utils
from virttest.utils_libvirtd import service_libvirtd_control
from virttest.libvirt_xml import vm_xml
from virttest.libvirt_xml import network_xml
from virttest.libvirt_xml import xcepts
from virttest.libvirt_xml import NetworkXML
from virttest.libvirt_xml import IPXML
from virttest.libvirt_xml import pool_xml
from virttest.libvirt_xml import nwfilter_xml
from virttest.libvirt_xml import vol_xml
from virttest.libvirt_xml import secret_xml
from virttest.libvirt_xml import CapabilityXML
from virttest.libvirt_xml import base
from virttest.libvirt_xml.devices import disk
from virttest.libvirt_xml.devices import hostdev
from virttest.libvirt_xml.devices import controller
from virttest.libvirt_xml.devices import redirdev
from virttest.libvirt_xml.devices import seclabel
from virttest.libvirt_xml.devices import channel
from virttest.libvirt_xml.devices import interface
from virttest.libvirt_xml.devices import panic
from virttest.libvirt_xml.devices import tpm
from virttest.libvirt_xml.devices import vsock
from virttest.libvirt_xml.devices import rng

ping = utils_net.ping


class LibvirtNetwork(object):

    """
    Class to create a temporary network for testing.
    """

    def create_network_xml_with_dhcp(self):
        """
        Create XML for a network xml with dhcp.
        """
        net_xml = NetworkXML()
        net_xml.name = self.kwargs.get('net_name')
        ip_version = self.kwargs.get('ip_version')
        dhcp_start = self.kwargs.get('dhcp_start')
        dhcp_end = self.kwargs.get('dhcp_end')
        address = self.kwargs.get('address')
        ip = None
        if ip_version == 'ipv6':
            ip = IPXML(address=address, ipv6=ip_version)
            ip.prefix = '64'
        else:
            ip = IPXML(address=address)
        ip.family = ip_version
        ip.dhcp_ranges = {'start': dhcp_start, 'end': dhcp_end}
        net_xml.ip = ip
        net_xml.bridge = {'name': self.kwargs.get('br_name'), 'stp': 'on', 'delay': '0'}
        return net_xml

    def create_vnet_xml(self):
        """
        Create XML for a virtual network.
        """
        address = self.kwargs.get('address')
        if not address:
            raise exceptions.TestError('Create vnet need address be set')
        net_xml = NetworkXML()
        net_xml.name = self.name
        ip = IPXML(address=address)
        dhcp_start = self.kwargs.get('dhcp_start')
        dhcp_end = self.kwargs.get('dhcp_end')
        if all([dhcp_start, dhcp_end]):
            ip.dhcp_ranges = {'start': dhcp_start, 'end': dhcp_end}
        net_xml.ip = ip
        return address, net_xml

    def create_macvtap_xml(self):
        """
        Create XML for a macvtap network.
        """
        iface = self.kwargs.get('iface')
        if not iface:
            raise exceptions.TestError('Create macvtap need iface be set')
        net_xml = NetworkXML()
        net_xml.name = self.kwargs.get('net_name')
        net_xml.forward = {'mode': 'bridge', 'dev': iface}
        ip_version = self.kwargs.get('ip_version')
        ip = utils_net.get_ip_address_by_interface(iface, ip_ver=ip_version)
        return ip, net_xml

    def create_bridge_xml(self):
        """
        Create XML for a bridged network.
        """
        iface = self.kwargs.get('iface')
        if not iface:
            raise exceptions.TestError('Create bridge need iface be set')
        net_xml = NetworkXML()
        net_xml.name = self.name
        net_xml.forward = {'mode': 'bridge'}
        net_xml.bridge = {'name': iface}
        ip = utils_net.get_ip_address_by_interface(iface)
        return ip, net_xml

    def create_nat_xml(self):
        """
        Create XML for a nat network.
        """
        address = self.kwargs.get('address')
        if not address:
            raise exceptions.TestError("'address' is required to create nat network xml.")
        net_xml = self.create_network_xml_with_dhcp()
        net_xml.forward = {'mode': 'nat'}
        return address, net_xml

    def create_route_xml(self):
        """
        Create XML for a route network.
        """
        address = self.kwargs.get('address')
        if not address:
            raise exceptions.TestError("'address' is required to create route network xml.")
        net_xml = self.create_network_xml_with_dhcp()
        net_xml.forward = {'mode': 'route'}
        return address, net_xml

    def __init__(self, net_type, **kwargs):
        self.kwargs = kwargs
        net_name = kwargs.get('net_name')
        if net_name is None:
            self.name = 'avocado-vt-%s' % net_type
        else:
            self.name = net_name
        self.persistent = kwargs.get('persistent', False)

        if net_type == 'vnet':
            self.ip, net_xml = self.create_vnet_xml()
        elif net_type == 'macvtap':
            self.ip, net_xml = self.create_macvtap_xml()
        elif net_type == 'bridge':
            self.ip, net_xml = self.create_bridge_xml()
        elif net_type == 'nat':
            self.ip, net_xml = self.create_nat_xml()
        elif net_type == 'route':
            self.ip, net_xml = self.create_route_xml()
        else:
            raise exceptions.TestError(
                'Unknown libvirt network type %s' % net_type)
        if self.persistent:
            net_xml.define()
            net_xml.start()
        else:
            net_xml.create()

    def cleanup(self):
        """
        Clear up network.
        """
        virsh.net_destroy(self.name)
        if self.persistent:
            virsh.net_undefine(self.name)


def create_macvtap_vmxml(iface, params):
    """
    Method to create Macvtap interface xml for VM

    :param iface: macvtap interface name
    :param params: Test dict params for macvtap config

    :return: macvtap xml object
    """
    mode = params.get('macvtap_mode', 'passthrough')
    model = params.get('macvtap_model', 'virtio')
    macvtap_type = params.get('macvtap_type', 'direct')
    macvtap = interface.Interface(macvtap_type)
    macvtap.mac_address = utils_net.generate_mac_address_simple()
    macvtap.model = model
    macvtap.source = {'dev': iface, 'mode': mode}
    return macvtap


def get_machine_types(arch, virt_type, virsh_instance=base.virsh, ignore_status=True):
    """
    Method to get all supported machine types

    :param arch: architecture of the machine
    :param virt_type: virtualization type hvm or pv
    :param virsh_instance: virsh instance object
    :param ignore_status: False to raise Error, True to ignore

    :return: list of machine types supported
    """
    machine_types = []
    try:
        capability = CapabilityXML(virsh_instance=virsh_instance)
        machine_types = capability.guest_capabilities[virt_type][arch]['machine']
        return machine_types
    except KeyError as detail:
        if ignore_status:
            return machine_types
        else:
            if detail.args[0] == virt_type:
                raise KeyError("No libvirt support for %s virtualization, "
                               "does system hardware + software support it?"
                               % virt_type)
            elif detail.args[0] == arch:
                raise KeyError("No libvirt support for %s virtualization of "
                               "%s, does system hardware + software support "
                               "it?" % (virt_type, arch))
            raise exceptions.TestError(detail)


def clean_up_snapshots(vm_name, snapshot_list=[], domxml=None):
    """
    Do recovery after snapshot

    :param vm_name: Name of domain
    :param snapshot_list: The list of snapshot name you want to remove
    :param domxml: The object of domain xml for dumpxml command
    """
    if not snapshot_list:
        # Get all snapshot names from virsh snapshot-list
        snapshot_list = virsh.snapshot_list(vm_name)

        # Get snapshot disk path
        for snap_name in snapshot_list:
            # Delete useless disk snapshot file if exists
            result = virsh.snapshot_dumpxml(vm_name, snap_name)
            snap_xml = result.stdout_text.strip()
            xtf_xml = xml_utils.XMLTreeFile(snap_xml)
            disks_path = xtf_xml.findall('disks/disk/source')
            for disk in disks_path:
                os.system('rm -f %s' % disk.get('file'))
            # Delete snapshots of vm
            virsh.snapshot_delete(vm_name, snap_name)

        # External disk snapshot couldn't be deleted by virsh command,
        # It need to be deleted by qemu-img command
        snapshot_list = virsh.snapshot_list(vm_name)
        if snapshot_list:
            # Delete snapshot metadata first
            for snap_name in snapshot_list:
                virsh.snapshot_delete(vm_name, snap_name, "--metadata")
            # Delete all snapshot by qemu-img.
            # Domain xml should be proviced by parameter, we can't get
            # the image name from dumpxml command, it will return a
            # snapshot image name
            if domxml:
                disks_path = domxml.xmltreefile.findall('devices/disk/source')
                for disk in disks_path:
                    img_name = disk.get('file')
                    snaps = utils_misc.get_image_snapshot(img_name)
                    cmd = "qemu-img snapshot %s" % img_name
                    for snap in snaps:
                        process.run("%s -d %s" % (cmd, snap))
    else:
        # Get snapshot disk path from domain xml because
        # there is no snapshot info with the name
        dom_xml = vm_xml.VMXML.new_from_dumpxml(vm_name).xmltreefile
        disk_path = dom_xml.find('devices/disk/source').get('file')
        for name in snapshot_list:
            snap_disk_path = disk_path.split(".")[0] + "." + name
            os.system('rm -f %s' % snap_disk_path)


def get_all_cells():
    """
    Use virsh freecell --all to get all cells on host

    ::

        # virsh freecell --all
            0:     124200 KiB
            1:    1059868 KiB
        --------------------
        Total:    1184068 KiB

    That would return a dict like:

    ::

        cell_dict = {"0":"124200 KiB", "1":"1059868 KiB", "Total":"1184068 KiB"}

    :return: cell_dict
    """
    fc_result = virsh.freecell(options="--all", ignore_status=True)
    if fc_result.exit_status:
        stderr = fc_result.stderr_text.strip()
        if fc_result.stderr.count(b"NUMA not supported"):
            raise exceptions.TestSkipError(stderr)
        else:
            raise exceptions.TestFail(stderr)
    output = fc_result.stdout_text.strip()
    cell_list = output.splitlines()
    # remove "------------" line
    del cell_list[-2]
    cell_dict = {}
    for cell_line in cell_list:
        cell_info = cell_line.split(":")
        cell_num = cell_info[0].strip()
        cell_mem = cell_info[-1].strip()
        cell_dict[cell_num] = cell_mem
    return cell_dict


def check_blockjob(vm_name, target, check_point="none", value="0"):
    """
    Run blookjob command to check block job progress, bandwidth, ect.

    :param vm_name: Domain name
    :param target: Domian disk target dev
    :param check_point: Job progrss, bandwidth or none(no job)
    :param value: Value of progress, bandwidth(with unit) or 0(no job)
    :return: Boolean value, true for pass, false for fail
    """
    if check_point not in ["progress", "bandwidth", "none"]:
        logging.error("Check point must be: progress, bandwidth or none")
        return False
    try:
        cmd_result = virsh.blockjob(
            vm_name, target, "--info", debug=True, ignore_status=True)
        output = cmd_result.stdout_text.strip()
        err = cmd_result.stderr_text.strip()
        status = cmd_result.exit_status
    except Exception as e:
        logging.error("Error occurred: %s", e)
        return False
    if status:
        logging.error("Run blockjob command fail")
        return False
    # libvirt print block job progress to stderr
    if check_point == 'none':
        if len(err):
            logging.error("Expect no job but find block job:\n%s", err)
            return False
        return True
    if check_point == "progress":
        progress = value + " %"
        if re.search(progress, err):
            return True
        return False
    # Since 1.3.3-1, libvirt support bytes and scaled integers for bandwith,
    # and the output of blockjob may looks like:
    # # virsh blockjob avocado-vt-vm1 vda --info
    # Block Copy: [100 %]    Bandwidth limit: 9223372036853727232 bytes/s (8.000 EiB/s)
    #
    # So we need specific the bandwidth unit when calling this function
    # and universalize the unit before comparing
    if check_point == "bandwidth":
        try:
            bandwidth, unit = re.findall(r'(\d+) (\w+)/s', output)[0]
            # unit could be 'bytes' or 'Mib'
            if unit == 'bytes':
                unit = 'B'
            else:
                unit = 'M'
            u_value = utils_misc.normalize_data_size(value, unit)
            if float(u_value) == float(bandwidth):
                logging.debug("Bandwidth is equal to %s", bandwidth)
                return True
            logging.error("Bandwidth is not equal to %s", bandwidth)
            return False
        except Exception as e:
            logging.error("Fail to get bandwidth: %s", e)
            return False


def setup_or_cleanup_nfs(is_setup, mount_dir="nfs-mount", is_mount=False,
                         export_options="rw,no_root_squash",
                         mount_options="rw",
                         export_dir="nfs-export",
                         restore_selinux="",
                         rm_export_dir=True,
                         set_selinux_permissive=False):
    """
    Set SElinux to "permissive" and Set up nfs service on localhost.
    Or clean up nfs service on localhost and restore SElinux.

    Note: SElinux status must be backed up and restored after use.
    Example:

    # Setup NFS.
    res = setup_or_cleanup_nfs(is_setup=True)
    # Backup SELinux status.
    selinux_bak = res["selinux_status_bak"]

    # Do something.
    ...

    # Cleanup NFS and restore NFS.
    res = setup_or_cleanup_nfs(is_setup=False, restore_selinux=selinux_bak)

    :param is_setup: Boolean value, true for setup, false for cleanup
    :param mount_dir: NFS mount dir. This can be an absolute path on the
                      host or a relative path origin from libvirt tmp dir.
                      Default to "nfs-mount".
    :param is_mount: Boolean value, Whether the target NFS should be mounted.
    :param export_options: Options for nfs dir. Default to "nfs-export".
    :param mount_options: Options for mounting nfs dir. Default to "rw".
    :param export_dir: NFS export dir. This can be an absolute path on the
                      host or a relative path origin from libvirt tmp dir.
                      Default to "nfs-export".
    :param rm_export_dir: Boolean, True for forcely removing nfs export dir
                                   False for keeping nfs export dir
    :param set_selinux_permissive: Boolean, True to set selinux to permissive
                                   mode, False not set.
    :return: A dict contains export and mount result parameters:
             export_dir: Absolute directory of exported local NFS file system.
             mount_dir: Absolute directory NFS file system mounted on.
             selinux_status_bak: SELinux status before set
    """
    result = {}
    ubuntu = distro.detect().name == 'Ubuntu'

    tmpdir = data_dir.get_tmp_dir()
    if not os.path.isabs(export_dir):
        export_dir = os.path.join(tmpdir, export_dir)
    if not os.path.isabs(mount_dir):
        mount_dir = os.path.join(tmpdir, mount_dir)
    result["export_dir"] = export_dir
    result["mount_dir"] = mount_dir
    result["selinux_status_bak"] = None
    if not ubuntu:
        result["selinux_status_bak"] = utils_selinux.get_status()

    nfs_params = {"nfs_mount_dir": mount_dir, "nfs_mount_options": mount_options,
                  "nfs_mount_src": export_dir, "setup_local_nfs": "yes",
                  "export_options": export_options}
    _nfs = nfs.Nfs(nfs_params)

    if is_setup:
        if not ubuntu and utils_selinux.is_enforcing():
            if set_selinux_permissive:
                utils_selinux.set_status("permissive")
                logging.debug("selinux set to permissive mode, "
                              "this is not recommended, potential access "
                              "control error could be missed.")
            else:
                logging.debug("selinux is in enforcing mode, libvirt needs "
                              "\"setsebool virt_use_nfs on\" to get "
                              "nfs access right.")
        _nfs.setup()
        nfs_mount_info = process.run('nfsstat -m', shell=True).stdout_text.strip().split(",")
        for i in nfs_mount_info:
            if 'vers' in i:
                source_protocol_ver = i[5]
                result["source_protocol_ver"] = source_protocol_ver
                break
        if not is_mount:
            _nfs.umount()
            del result["mount_dir"]
    else:
        if not ubuntu and restore_selinux:
            utils_selinux.set_status(restore_selinux)
        _nfs.unexportfs_in_clean = True
        _nfs.rm_mount_dir = True
        _nfs.rm_export_dir = rm_export_dir
        _nfs.cleanup()
    return result


def setup_or_cleanup_iscsi(is_setup, is_login=True,
                           emulated_image="emulated-iscsi", image_size="1G",
                           chap_user="", chap_passwd="", restart_tgtd="no",
                           portal_ip="127.0.0.1"):
    """
    Set up(and login iscsi target) or clean up iscsi service on localhost.

    :param is_setup: Boolean value, true for setup, false for cleanup
    :param is_login: Boolean value, true for login, false for not login
    :param emulated_image: name of iscsi device
    :param image_size: emulated image's size
    :param chap_user: CHAP authentication username
    :param chap_passwd: CHAP authentication password
    :return: iscsi device name or iscsi target
    """
    tmpdir = data_dir.get_tmp_dir()
    emulated_path = os.path.join(tmpdir, emulated_image)
    emulated_target = ("iqn.%s.com.virttest:%s.target" %
                       (time.strftime("%Y-%m"), emulated_image))
    iscsi_params = {"emulated_image": emulated_path, "target": emulated_target,
                    "image_size": image_size, "iscsi_thread_id": "virt",
                    "chap_user": chap_user, "chap_passwd": chap_passwd,
                    "restart_tgtd": restart_tgtd, "portal_ip": portal_ip}
    _iscsi = iscsi.Iscsi.create_iSCSI(iscsi_params)
    if is_setup:
        if is_login:
            _iscsi.login()
            # The device doesn't necessarily appear instantaneously, so give
            # about 5 seconds for it to appear before giving up
            iscsi_device = utils_misc.wait_for(_iscsi.get_device_name, 5, 0, 1,
                                               "Searching iscsi device name.")
            if iscsi_device:
                logging.debug("iscsi device: %s", iscsi_device)
                return iscsi_device
            if not iscsi_device:
                logging.error("Not find iscsi device.")
            # Cleanup and return "" - caller needs to handle that
            # _iscsi.export_target() will have set the emulated_id and
            # export_flag already on success...
            _iscsi.cleanup()
            process.run("rm -f %s" % emulated_path)
        else:
            _iscsi.export_target()
            return (emulated_target, _iscsi.luns)
    else:
        _iscsi.export_flag = True
        _iscsi.emulated_id = _iscsi.get_target_id()
        _iscsi.cleanup()
        process.run("rm -f %s" % emulated_path)
    return ""


def define_pool(pool_name, pool_type, pool_target, cleanup_flag, **kwargs):
    """
    To define a given type pool(Support types: 'dir', 'netfs', logical',
    iscsi', 'gluster', 'disk' and 'fs').

    :param pool_name: Name of the pool
    :param pool_type: Type of the pool
    :param pool_target: Target for underlying storage
    :param cleanup_flag: A list contains 3 booleans and 1 string stands for
                         need_cleanup_nfs, need_cleanup_iscsi,
                         need_cleanup_logical, selinux_bak and
                         need_cleanup_gluster
    :param kwargs: key words for special pool define. eg, glusterfs pool
                         source path and source name, etc
    """

    extra = ""
    vg_name = pool_name
    cleanup_nfs = False
    cleanup_iscsi = False
    cleanup_logical = False
    selinux_bak = ""
    cleanup_gluster = False
    if not os.path.exists(pool_target) and pool_type != "gluster":
        os.mkdir(pool_target)
    if pool_type == "dir":
        pass
    elif pool_type == "netfs":
        # Set up NFS server without mount
        res = setup_or_cleanup_nfs(True, pool_target, False)
        nfs_path = res["export_dir"]
        selinux_bak = res["selinux_status_bak"]
        cleanup_nfs = True
        extra = "--source-host %s --source-path %s" % ('127.0.0.1',
                                                       nfs_path)
    elif pool_type == "logical":
        # Create vg by using iscsi device
        lv_utils.vg_create(vg_name, setup_or_cleanup_iscsi(True))
        cleanup_iscsi = True
        cleanup_logical = True
        extra = "--source-name %s" % vg_name
    elif pool_type == "iscsi":
        # Set up iscsi target without login
        iscsi_target, _ = setup_or_cleanup_iscsi(True, False)
        cleanup_iscsi = True
        extra = "--source-host %s  --source-dev %s" % ('127.0.0.1',
                                                       iscsi_target)
    elif pool_type == "disk":
        # Set up iscsi target and login
        device_name = setup_or_cleanup_iscsi(True)
        cleanup_iscsi = True
        # Create a partition to make sure disk pool can start
        mk_label(device_name)
        mk_part(device_name)
        extra = "--source-dev %s" % device_name
    elif pool_type == "fs":
        # Set up iscsi target and login
        device_name = setup_or_cleanup_iscsi(True)
        cleanup_iscsi = True
        # Format disk to make sure fs pool can start
        source_format = kwargs.get('source_format', 'ext4')
        mkfs(device_name, source_format)
        extra = "--source-dev %s --source-format %s" % (device_name, source_format)
    elif pool_type == "gluster":
        gluster_source_path = kwargs.get('gluster_source_path')
        gluster_source_name = kwargs.get('gluster_source_name')
        gluster_file_name = kwargs.get('gluster_file_name')
        gluster_file_type = kwargs.get('gluster_file_type')
        gluster_file_size = kwargs.get('gluster_file_size')
        gluster_vol_number = kwargs.get('gluster_vol_number')

        # Prepare gluster service and create volume
        hostip = gluster.setup_or_cleanup_gluster(True, gluster_source_name,
                                                  pool_name=pool_name, **kwargs)
        logging.debug("hostip is %s", hostip)
        # create image in gluster volume
        file_path = "gluster://%s/%s" % (hostip, gluster_source_name)
        for i in range(gluster_vol_number):
            file_name = "%s_%d" % (gluster_file_name, i)
            process.run("qemu-img create -f %s %s/%s %s" %
                        (gluster_file_type, file_path, file_name,
                         gluster_file_size))
        cleanup_gluster = True
        extra = "--source-host %s --source-path %s --source-name %s" % \
                (hostip, gluster_source_path, gluster_source_name)
    elif pool_type in ["scsi", "mpath", "rbd", "sheepdog"]:
        raise exceptions.TestSkipError(
            "Pool type '%s' has not yet been supported in the test." %
            pool_type)
    else:
        raise exceptions.TestFail("Invalid pool type: '%s'." % pool_type)
    # Mark the clean up flags
    cleanup_flag[0] = cleanup_nfs
    cleanup_flag[1] = cleanup_iscsi
    cleanup_flag[2] = cleanup_logical
    cleanup_flag[3] = selinux_bak
    cleanup_flag[4] = cleanup_gluster
    try:
        result = virsh.pool_define_as(pool_name, pool_type, pool_target, extra,
                                      ignore_status=True)
    except process.CmdError:
        logging.error("Define '%s' type pool fail.", pool_type)
    return result


def verify_virsh_console(session, user, passwd, timeout=10, debug=False):
    """
    Run commands in console session.
    """
    log = ""
    console_cmd = "cat /proc/cpuinfo"
    try:
        while True:
            match, text = session.read_until_last_line_matches(
                [r"[E|e]scape character is", r"login:",
                 r"[P|p]assword:", session.prompt],
                timeout, internal_timeout=1)

            if match == 0:
                if debug:
                    logging.debug("Got '^]', sending '\\n'")
                session.sendline()
            elif match == 1:
                if debug:
                    logging.debug("Got 'login:', sending '%s'", user)
                session.sendline(user)
            elif match == 2:
                if debug:
                    logging.debug("Got 'Password:', sending '%s'", passwd)
                session.sendline(passwd)
            elif match == 3:
                if debug:
                    logging.debug("Got Shell prompt -- logged in")
                break

        status, output = session.cmd_status_output(console_cmd)
        logging.info("output of command:\n%s", output)
        session.close()
    except (aexpect.ShellError,
            aexpect.ExpectError) as detail:
        log = session.get_output()
        logging.error("Verify virsh console failed:\n%s\n%s", detail, log)
        session.close()
        return False

    if not re.search("processor", output):
        logging.error("Verify virsh console failed: Result does not match.")
        return False

    return True


def pci_info_from_address(address_dict, radix=10, type="label"):
    """
    Generate a pci label or id from a dict of address.

    :param address_dict: A dict contains domain, bus, slot and function.
    :param radix: The radix of your data in address_dict.
    :param type: label or id

    Example:

    ::

        address_dict = {'domain': '0x0000', 'bus': '0x08', 'slot': '0x10', 'function': '0x0'}
        radix = 16
        return = pci_0000_08_10_0 or 0000:08:10.0
    """
    try:
        domain = int(address_dict['domain'], radix)
        bus = int(address_dict['bus'], radix)
        slot = int(address_dict['slot'], radix)
        function = int(address_dict['function'], radix)
    except (TypeError, KeyError) as detail:
        raise exceptions.TestError(detail)
    if type == "label":
        result = ("pci_%04x_%02x_%02x_%01x" % (domain, bus, slot, function))
    elif type == "id":
        result = ("%04x:%02x:%02x.%01x" % (domain, bus, slot, function))
    else:
        # TODO: for other type
        result = None
    return result


def mk_label(disk, label="msdos", session=None):
    """
    Set label for disk.
    """
    mklabel_cmd = "parted -s %s mklabel %s" % (disk, label)
    if session:
        session.cmd(mklabel_cmd)
    else:
        process.run(mklabel_cmd)


def mk_part(disk, size="100M", fs_type='ext4', session=None):
    """
    Create a partition for disk
    """
    # TODO: This is just a temporary function to create partition for
    # testing usage, should be replaced by a more robust one.
    support_lable = ['unknown', 'gpt', 'msdos']
    disk_label = 'msdos'
    part_type = 'primary'
    part_start = '0'

    run_cmd = process.system_output
    if session:
        run_cmd = session.get_command_output

    print_cmd = "parted -s %s print" % disk
    output = to_text(run_cmd(print_cmd))
    current_label = re.search(r'Partition Table: (\w+)', output).group(1)
    if current_label not in support_lable:
        logging.error('Not support create partition on %s disk', current_label)
        return

    disk_size = re.search(r"Disk %s: (\w+)" % disk, output).group(1)
    pat = r'(?P<num>\d+)\s+(?P<start>\S+)\s+(?P<end>\S+)\s+(?P<size>\S+)\s+'
    current_parts = [m.groupdict() for m in re.finditer(pat, output)]

    mkpart_cmd = "parted -s -a optimal %s" % disk
    if current_label == 'unknown':
        mkpart_cmd += " mklabel %s" % disk_label
    if len(current_parts) > 0:
        part_start = current_parts[-1]['end']
    part_end = (float(utils_misc.normalize_data_size(part_start,
                                                     factor='1000')) +
                float(utils_misc.normalize_data_size(size, factor='1000')))

    # Deal with msdos disk
    if current_label == 'msdos':
        if len(current_parts) == 3:
            extended_cmd = " mkpart extended %s %s" % (part_start, disk_size)
            to_text(run_cmd(mkpart_cmd + extended_cmd))
        if len(current_parts) > 2:
            part_type = 'logical'

    mkpart_cmd += ' mkpart %s %s %s %s' % (part_type, fs_type, part_start,
                                           part_end)
    to_text(run_cmd(mkpart_cmd))


def mkfs(partition, fs_type, options="", session=None):
    """
    Force to make a file system on the partition
    """
    force_option = ''
    if fs_type in ['ext2', 'ext3', 'ext4', 'ntfs']:
        force_option = '-F'
    elif fs_type in ['fat', 'vfat', 'msdos']:
        force_option = '-I'
    elif fs_type in ['xfs', 'btrfs']:
        force_option = '-f'
    mkfs_cmd = "mkfs.%s %s %s %s" % (fs_type, force_option, partition, options)
    if session:
        session.cmd(mkfs_cmd)
    else:
        process.run(mkfs_cmd)


def yum_install(pkg_list, session=None):
    """
    Try to install packages on system
    """
    if not isinstance(pkg_list, list):
        raise exceptions.TestError("Parameter error.")
    yum_cmd = "rpm -q {0} || yum -y install {0}"
    for pkg in pkg_list:
        if session:
            status = session.cmd_status(yum_cmd.format(pkg))
        else:
            status = process.run(yum_cmd.format(pkg),
                                 shell=True).exit_status
        if status:
            raise exceptions.TestFail("Failed to install package: %s"
                                      % pkg)


def check_actived_pool(pool_name):
    """
    Check if pool_name exist in active pool list
    """
    sp = libvirt_storage.StoragePool()
    if not sp.pool_exists(pool_name):
        raise exceptions.TestFail("Can't find pool %s" % pool_name)
    if not sp.is_pool_active(pool_name):
        raise exceptions.TestFail("Pool %s is not active." % pool_name)
    logging.debug("Find active pool %s", pool_name)
    return True


def check_vm_state(vm_name, state='paused', reason=None, uri=None):
    """
    checks whether state of the vm is as expected

    :param vm_name: VM name
    :param state: expected state of the VM
    :param reason: expected reason of vm state
    :param uri: connect uri

    :return: True if state of VM is as expected, False otherwise
    """
    if not virsh.domain_exists(vm_name, uri=uri):
        return False
    if reason:
        result = virsh.domstate(vm_name, extra="--reason", uri=uri)
        expected_result = "%s (%s)" % (state.lower(), reason.lower())
    else:
        result = virsh.domstate(vm_name, uri=uri)
        expected_result = state.lower()
    vm_state = result.stdout_text.strip()
    return vm_state.lower() == expected_result


class PoolVolumeTest(object):

    """Test class for storage pool or volume"""

    def __init__(self, test, params):
        self.tmpdir = data_dir.get_tmp_dir()
        self.params = params
        self.selinux_bak = ""

    def cleanup_pool(self, pool_name, pool_type, pool_target, emulated_image,
                     **kwargs):
        """
        Delete vols, destroy the created pool and restore the env
        """
        sp = libvirt_storage.StoragePool()
        source_format = kwargs.get('source_format')
        source_name = kwargs.get('source_name')
        device_name = kwargs.get('device_name', "/DEV/EXAMPLE")
        try:
            if sp.pool_exists(pool_name):
                pv = libvirt_storage.PoolVolume(pool_name)
                if pool_type in ["dir", "netfs", "logical", "disk"]:
                    if sp.is_pool_active(pool_name):
                        vols = pv.list_volumes()
                        for vol in vols:
                            # Ignore failed deletion here for deleting pool
                            pv.delete_volume(vol)
                if not sp.delete_pool(pool_name):
                    raise exceptions.TestFail(
                        "Delete pool %s failed" % pool_name)
        finally:
            if pool_type == "netfs" and source_format != 'glusterfs':
                nfs_server_dir = self.params.get("nfs_server_dir", "nfs-server")
                nfs_path = os.path.join(self.tmpdir, nfs_server_dir)
                setup_or_cleanup_nfs(is_setup=False, export_dir=nfs_path,
                                     restore_selinux=self.selinux_bak)
                if os.path.exists(nfs_path):
                    shutil.rmtree(nfs_path)
            if pool_type == "logical":
                cmd = "pvs |grep vg_logical|awk '{print $1}'"
                pv = process.run(cmd, shell=True).stdout_text
                # Cleanup logical volume anyway
                process.run("vgremove -f vg_logical", ignore_status=True)
                process.run("pvremove %s" % pv, ignore_status=True)
            # These types used iscsi device
            # If we did not provide block device
            if (pool_type in ["logical", "fs", "disk"] and
                    device_name.count("EXAMPLE")):
                setup_or_cleanup_iscsi(is_setup=False,
                                       emulated_image=emulated_image)
            # Used iscsi device anyway
            if pool_type in ["iscsi", "iscsi-direct", "scsi"]:
                setup_or_cleanup_iscsi(is_setup=False,
                                       emulated_image=emulated_image)
                if pool_type == "scsi":
                    scsi_xml_file = self.params.get("scsi_xml_file", "")
                    if os.path.exists(scsi_xml_file):
                        os.remove(scsi_xml_file)
            if pool_type in ["dir", "fs", "netfs"]:
                pool_target = os.path.join(self.tmpdir, pool_target)
                if os.path.exists(pool_target):
                    shutil.rmtree(pool_target)
            if pool_type == "gluster" or source_format == 'glusterfs':
                gluster.setup_or_cleanup_gluster(False, source_name,
                                                 pool_name=pool_name, **kwargs)

    def pre_pool(self, pool_name, pool_type, pool_target, emulated_image,
                 **kwargs):
        """
        Prepare(define or create) the specific type pool

        :param pool_name: created pool name
        :param pool_type: dir, disk, logical, fs, netfs or else
        :param pool_target: target of storage pool
        :param emulated_image: use an image file to simulate a scsi disk
                               it could be used for disk, logical pool, etc
        :param kwargs: key words for specific pool
        """
        extra = ""
        image_size = kwargs.get('image_size', "100M")
        source_format = kwargs.get('source_format')
        source_name = kwargs.get('source_name', None)
        persistent = kwargs.get('persistent', False)
        device_name = kwargs.get('device_name', "/DEV/EXAMPLE")
        adapter_type = kwargs.get('pool_adapter_type', 'scsi_host')
        pool_wwnn = kwargs.get('pool_wwnn', None)
        pool_wwpn = kwargs.get('pool_wwpn', None)
        source_protocol_ver = kwargs.get('source_protocol_ver', "no")

        # If tester does not provide block device, creating one
        if (device_name.count("EXAMPLE") and
                pool_type in ["disk", "fs", "logical"]):
            device_name = setup_or_cleanup_iscsi(is_setup=True,
                                                 emulated_image=emulated_image,
                                                 image_size=image_size)

        if pool_type == "dir":
            if not os.path.isdir(pool_target):
                pool_target = os.path.join(self.tmpdir, pool_target)
            if not os.path.exists(pool_target):
                os.mkdir(pool_target)
        elif pool_type == "disk":
            extra = " --source-dev %s" % device_name
            # msdos is libvirt default pool source format, but libvirt use
            # notion 'dos' here
            if not source_format:
                source_format = 'dos'
            extra += " --source-format %s" % source_format
            disk_label = source_format
            if disk_label == 'dos':
                disk_label = 'msdos'
            mk_label(device_name, disk_label)
            # Disk pool does not allow to create volume by virsh command,
            # so introduce parameter 'pre_disk_vol' to create partition(s)
            # by 'parted' command, the parameter is a list of partition size,
            # and the max number of partitions depends on the disk label.
            # If pre_disk_vol is None, disk pool will have no volume
            pre_disk_vol = kwargs.get('pre_disk_vol', None)
            if isinstance(pre_disk_vol, list) and len(pre_disk_vol):
                for vol in pre_disk_vol:
                    mk_part(device_name, vol)
        elif pool_type == "fs":
            pool_target = os.path.join(self.tmpdir, pool_target)
            if not os.path.exists(pool_target):
                os.mkdir(pool_target)
            if not source_format:
                source_format = 'ext4'
            mkfs(device_name, source_format)
            extra = " --source-dev %s --source-format %s" % (device_name,
                                                             source_format)
        elif pool_type == "logical":
            logical_device = device_name
            vg_name = "vg_%s" % pool_type
            lv_utils.vg_create(vg_name, logical_device)
            extra = "--source-name %s" % vg_name
            # Create a small volume for verification
            # And VG path will not exist if no any volume in.(bug?)
            lv_utils.lv_create(vg_name, 'default_lv', '1M')
        elif pool_type == "netfs":
            export_options = kwargs.get('export_options',
                                        "rw,async,no_root_squash")
            pool_target = os.path.join(self.tmpdir, pool_target)
            if not os.path.exists(pool_target):
                os.mkdir(pool_target)
            if source_format == 'glusterfs':
                hostip = gluster.setup_or_cleanup_gluster(True, source_name,
                                                          pool_name=pool_name,
                                                          **kwargs)
                logging.debug("hostip is %s", hostip)
                extra = "--source-host %s --source-path %s" % (hostip,
                                                               source_name)
                extra += " --source-format %s" % source_format
                process.system("setsebool virt_use_fusefs on")
            else:
                nfs_server_dir = self.params.get(
                    "nfs_server_dir", "nfs-server")
                nfs_path = os.path.join(self.tmpdir, nfs_server_dir)
                if not os.path.exists(nfs_path):
                    os.mkdir(nfs_path)
                res = setup_or_cleanup_nfs(is_setup=True,
                                           export_options=export_options,
                                           export_dir=nfs_path)
                self.selinux_bak = res["selinux_status_bak"]
                source_host = self.params.get("source_host", "localhost")
                extra = "--source-host %s --source-path %s" % (source_host,
                                                               nfs_path)
                if source_protocol_ver == "yes":
                    extra += "  --source-protocol-ver %s" % res["source_protocol_ver"]
        elif pool_type in ["iscsi", "iscsi-direct"]:
            ip_protocal = kwargs.get('ip_protocal', "ipv4")
            iscsi_chap_user = kwargs.get('iscsi_chap_user', None)
            iscsi_chap_password = kwargs.get('iscsi_chap_password', None)
            iscsi_secret_usage = kwargs.get('iscsi_secret_usage', None)
            iscsi_initiator = kwargs.get('iscsi_initiator', None)
            if ip_protocal == "ipv6":
                ip_addr = "::1"
            else:
                ip_addr = "127.0.0.1"
            if iscsi_chap_user and iscsi_chap_password and iscsi_secret_usage:
                logging.debug("setup %s pool with chap authentication", pool_type)
                extra = (" --auth-type chap --auth-username %s "
                         "--secret-usage %s" %
                         (iscsi_chap_user, iscsi_secret_usage))
            else:
                logging.debug("setup %s pool without authentication", pool_type)
            setup_or_cleanup_iscsi(is_setup=True,
                                   emulated_image=emulated_image,
                                   image_size=image_size,
                                   chap_user=iscsi_chap_user,
                                   chap_passwd=iscsi_chap_password,
                                   portal_ip=ip_addr)
            iscsi_sessions = iscsi.iscsi_get_sessions()
            iscsi_target = None
            for iscsi_node in iscsi_sessions:
                if iscsi_node[1].count(emulated_image):
                    iscsi_target = iscsi_node[1]
                    break
            iscsi.iscsi_logout(iscsi_target)
            extra += " --source-host %s  --source-dev %s" % (ip_addr,
                                                             iscsi_target)
            if pool_type == "iscsi-direct":
                extra += " --source-iqn %s" % iscsi_initiator

        elif pool_type == "scsi":
            scsi_xml_file = self.params.get("scsi_xml_file", "")
            if not os.path.exists(scsi_xml_file):
                logical_device = setup_or_cleanup_iscsi(
                    is_setup=True,
                    emulated_image=emulated_image,
                    image_size=image_size)
                cmd = ("iscsiadm -m session -P 3 |grep -B3 %s| grep Host|awk "
                       "'{print $3}'" % logical_device.split('/')[2])
                scsi_host = process.run(cmd, shell=True).stdout_text.strip()
                scsi_pool_xml = pool_xml.PoolXML()
                scsi_pool_xml.name = pool_name
                scsi_pool_xml.pool_type = "scsi"
                scsi_pool_xml.target_path = pool_target
                scsi_pool_source_xml = pool_xml.SourceXML()
                scsi_pool_source_xml.adp_type = adapter_type
                scsi_pool_source_xml.adp_name = "host" + scsi_host
                if pool_wwpn:
                    scsi_pool_source_xml.adp_wwpn = pool_wwpn
                if pool_wwnn:
                    scsi_pool_source_xml.adp_wwnn = pool_wwnn

                scsi_pool_xml.set_source(scsi_pool_source_xml)
                logging.debug("SCSI pool XML %s:\n%s", scsi_pool_xml.xml,
                              str(scsi_pool_xml))
                scsi_xml_file = scsi_pool_xml.xml
                self.params['scsi_xml_file'] = scsi_xml_file
        elif pool_type == "gluster":
            source_path = kwargs.get('source_path')
            logging.info("source path is %s" % source_path)
            hostip = gluster.setup_or_cleanup_gluster(True, source_name,
                                                      pool_name=pool_name,
                                                      **kwargs)
            logging.debug("Gluster host ip address: %s", hostip)
            extra = "--source-host %s --source-path %s --source-name %s" % \
                    (hostip, source_path, source_name)
        elif pool_type == "mpath":
            mpath_xml_file = self.params.get("mpath_xml_file", "")
            if not os.path.exists(mpath_xml_file):
                mpath_pool_xml = pool_xml.PoolXML()
                mpath_pool_xml.name = pool_name
                mpath_pool_xml.pool_type = "mpath"
                mpath_pool_xml.target_path = pool_target
                logging.debug("mpath pool XML %s:\n%s",
                              mpath_pool_xml.xml, str(mpath_pool_xml))
                mpath_xml_file = mpath_pool_xml.xml
                self.params['mpath_xml_file'] = mpath_xml_file

        func = virsh.pool_create_as
        if pool_type == "scsi" or pool_type == "mpath":
            func = virsh.pool_create
        if persistent:
            func = virsh.pool_define_as
            if pool_type == "scsi" or pool_type == "mpath":
                func = virsh.pool_define

        # Create/define pool
        if pool_type == "scsi":
            result = func(scsi_xml_file, debug=True)
        elif pool_type == "mpath":
            result = func(mpath_xml_file, debug=True)
        elif pool_type == "iscsi-direct":
            result = func(pool_name, pool_type, "", extra, debug=True)
        else:
            result = func(pool_name, pool_type, pool_target, extra, debug=True)
        # Here, virsh.pool_create_as return a boolean value and all other 3
        # functions return CmdResult object
        if isinstance(result, bool):
            re_v = result
        else:
            re_v = result.exit_status == 0
        if not re_v:
            self.cleanup_pool(pool_name, pool_type, pool_target,
                              emulated_image, **kwargs)
            raise exceptions.TestFail("Prepare pool failed")
        xml_str = virsh.pool_dumpxml(pool_name)
        logging.debug("New prepared pool XML: %s", xml_str)

    def pre_vol(self, vol_name, vol_format, capacity, allocation, pool_name):
        """
        Preapare the specific type volume in pool
        """
        pv = libvirt_storage.PoolVolume(pool_name)
        if not pv.create_volume(vol_name, capacity, allocation, vol_format):
            raise exceptions.TestFail("Prepare volume failed.")
        if not pv.volume_exists(vol_name):
            raise exceptions.TestFail("Can't find volume: %s" % vol_name)

    def pre_vol_by_xml(self, pool_name, **vol_params):
        """
        Prepare volume by xml file
        """
        volxml = vol_xml.VolXML()
        v_xml = volxml.new_vol(**vol_params)
        v_xml.xmltreefile.write()
        ret = virsh.vol_create(pool_name, v_xml.xml, ignore_status=True)
        check_exit_status(ret, False)


def check_status_output(status, output='',
                        expected_fails=None,
                        skip_if=None,
                        any_error=False,
                        expected_match=None):
    """
    Proxy function to call check_result for commands run in vm session.
    :param status: Exit status (used as CmdResult.exit_status)
    :param output: Stdout and/or stderr
    :param expected_fails: a string or list of regex of expected stderr patterns.
                           The check will pass if any of these patterns matches.
    :param skip_if: a string or list of regex of expected stderr patterns. The
                    check will raise a TestSkipError if any of these patterns matches.
    :param any_error: Whether expect on any error message. Setting to True will
                      will override expected_fails
    :param expected_match: a string or list of regex of expected stdout patterns.
                           The check will pass if any of these patterns matches.
    """

    result = process.CmdResult(stderr=output,
                               stdout=output,
                               exit_status=status)
    check_result(result, expected_fails, skip_if, any_error, expected_match)


def check_result(result,
                 expected_fails=[],
                 skip_if=[],
                 any_error=False,
                 expected_match=[]):
    """
    Check the result of a command and check command error message against
    expectation.

    :param result: Command result instance.
    :param expected_fails: a string or list of regex of expected stderr patterns.
                           The check will pass if any of these patterns matches.
    :param skip_if: a string or list of regex of expected stderr patterns. The
                    check will raise a TestSkipError if any of these patterns matches.
    :param any_error: Whether expect on any error message. Setting to True will
                      will override expected_fails
    :param expected_match: a string or list of regex of expected stdout patterns.
                           The check will pass if any of these patterns matches.
    """
    stderr = result.stderr_text
    stdout = result.stdout_text
    all_msg = '\n'.join([stdout, stderr])
    logging.debug("Command result: %s", all_msg)

    try:
        unicode
    except NameError:
        unicode = str

    if skip_if:
        if isinstance(skip_if, (str, unicode)):
            skip_if = [skip_if]
        for patt in skip_if:
            if re.search(patt, stderr):
                raise exceptions.TestSkipError("Test skipped: found '%s' in test "
                                               "result: %s" %
                                               (patt, all_msg))
    if any_error:
        if result.exit_status:
            return
        else:
            raise exceptions.TestFail(
                "Expect should fail but got: %s" % all_msg)

    if result.exit_status:
        if expected_fails:
            if isinstance(expected_fails, (str, unicode)):
                expected_fails = [expected_fails]
            if not any(re.search(patt, stderr)
                       for patt in expected_fails):
                raise exceptions.TestFail("Expect should fail with one of %s, "
                                          "but failed with:\n%s" %
                                          (expected_fails, all_msg))
            else:
                logging.info("Get expect error msg:%s" % stderr)
        else:
            raise exceptions.TestFail(
                "Expect should succeed, but got: %s" % all_msg)
    else:
        if expected_fails:
            raise exceptions.TestFail("Expect should fail with one of %s, "
                                      "but succeeded: %s" %
                                      (expected_fails, all_msg))
        elif expected_match:
            if isinstance(expected_match, (str, unicode)):
                expected_match = [expected_match]
            if not any(re.search(patt, stdout)
                       for patt in expected_match):
                raise exceptions.TestFail("Expect should match with one of %s,"
                                          "but failed with: %s" %
                                          (expected_match, all_msg))


def check_exit_status(result, expect_error=False):
    """
    Check the exit status of virsh commands.

    :param result: Virsh command result object
    :param expect_error: Boolean value, expect command success or fail
    """
    if not expect_error:
        if result.exit_status != 0:
            raise exceptions.TestFail(result.stderr_text)
        else:
            logging.debug("Command output:\n%s",
                          result.stdout_text.strip())
    elif expect_error and result.exit_status == 0:
        raise exceptions.TestFail("Run '%s' expect fail, but run "
                                  "successfully." % result.command)


def get_interface_details(vm_name):
    """
    Get the interface details from virsh domiflist command output

    :return: list of all interfaces details
    """
    # Parse the domif-list command output
    domiflist_out = virsh.domiflist(vm_name).stdout_text
    # Regular expression for the below output
    #   vnet0    bridge    virbr0   virtio  52:54:00:b2:b3:b4
    rg = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+"
                    "(([a-fA-F0-9]{2}:?){6})")

    iface_cmd = {}
    ifaces_cmd = []
    for line in domiflist_out.split('\n'):
        match_obj = rg.search(line.strip())
        # Due to the extra space in the list
        if match_obj is not None:
            iface_cmd['interface'] = match_obj.group(1)
            iface_cmd['type'] = match_obj.group(2)
            iface_cmd['source'] = match_obj.group(3)
            iface_cmd['model'] = match_obj.group(4)
            iface_cmd['mac'] = match_obj.group(5)
            ifaces_cmd.append(iface_cmd)
            iface_cmd = {}
    return ifaces_cmd


def get_ifname_host(vm_name, mac):
    """
    Get the vm interface name on host

    :return: interface name, None if not exist
    """
    ifaces = get_interface_details(vm_name)
    for iface in ifaces:
        if iface["mac"] == mac:
            return iface["interface"]
    return None


def check_iface(iface_name, checkpoint, extra="", **dargs):
    """
    Check interface with specified checkpoint.

    :param iface_name: Interface name
    :param checkpoint: Check if interface exists,
                       and It's MAC address, IP address and State,
                       also connectivity by ping.
                       valid checkpoint: [exists, mac, ip, ping, state]
    :param extra: Extra string for checking
    :return: Boolean value, true for pass, false for fail
    """
    support_check = ["exists", "mac", "ip", "ping"]
    iface = utils_net.Interface(name=iface_name)
    check_pass = False
    try:
        if checkpoint == "exists":
            # extra is iface-list option
            list_find, ifcfg_find = (False, False)
            # Check virsh list output
            result = virsh.iface_list(extra, ignore_status=True)
            check_exit_status(result, False)
            output = re.findall(r"(\S+)\ +(\S+)\ +(\S+|\s+)[\ +\n]",
                                result.stdout_text)
            if list(filter(lambda x: x[0] == iface_name, output[1:])):
                list_find = True
            logging.debug("Find '%s' in virsh iface-list output: %s",
                          iface_name, list_find)
            # Check network script independent of distro
            iface_script = utils_net.get_network_cfg_file(iface_name)
            ifcfg_find = os.path.exists(iface_script)
            logging.debug("Find '%s': %s", iface_script, ifcfg_find)
            check_pass = list_find and ifcfg_find
        elif checkpoint == "mac":
            # extra is the MAC address to compare
            iface_mac = iface.get_mac().lower()
            check_pass = iface_mac == extra
            logging.debug("MAC address of %s: %s", iface_name, iface_mac)
        elif checkpoint == "ip":
            # extra is the IP address to compare
            iface_ip = iface.get_ip()
            check_pass = iface_ip == extra
            logging.debug("IP address of %s: %s", iface_name, iface_ip)
        elif checkpoint == "state":
            # check iface State
            result = virsh.iface_list(extra, ignore_status=True)
            check_exit_status(result, False)
            output = re.findall(r"(\S+)\ +(\S+)\ +(\S+|\s+)[\ +\n]",
                                result.stdout_text)
            iface_state = filter(lambda x: x[0] == iface_name, output[1:])
            iface_state = list(iface_state)[0][1]
            # active corresponds True, otherwise return False
            check_pass = iface_state == "active"
        elif checkpoint == "ping":
            # extra is the ping destination
            count = dargs.get("count", 3)
            timeout = dargs.get("timeout", 5)
            ping_s, _ = ping(dest=extra, count=count, interface=iface_name,
                             timeout=timeout,)
            check_pass = ping_s == 0
        else:
            logging.debug("Support check points are: %s", support_check)
            logging.error("Unsupport check point: %s", checkpoint)
    except Exception as detail:
        raise exceptions.TestFail("Interface check failed: %s" % detail)
    return check_pass


def create_hostdev_xml(pci_id, boot_order=None, xmlfile=True,
                       dev_type="pci", managed="yes", alias=None):
    """
    Create a hostdev configuration file; supported hostdev types:
    a. pci
    b. usb
    c. scsi
    The named parameter "pci_id" now has an overloaded meaning of "device id".

    :param pci_id: device id on host, naming maintained for compatiblity reasons
    a. "0000:03:04.0" for pci
    b. "1d6b:0002:001:002" for usb (vendor:product:bus:device)
    c. "0:0:0:1" for scsi (scsi_num:bus_num:target_num:unit_num)
    :param boot_order: boot order for hostdev device
    :param xmlfile: Return the file path of xmlfile if True
    :param dev_type: type of hostdev
    :param managed: managed of hostdev
    :param alias: alias name of hostdev
    :return: xml of hostdev device by default
    """
    hostdev_xml = hostdev.Hostdev()
    hostdev_xml.mode = "subsystem"
    hostdev_xml.managed = managed
    hostdev_xml.type = dev_type
    if boot_order:
        hostdev_xml.boot_order = boot_order
    if alias:
        hostdev_xml.alias = dict(name=alias)

    # Create attributes dict for device's address element
    logging.info("pci_id/device id is %s" % pci_id)

    if dev_type in ["pci", "usb"]:
        device_domain = pci_id.split(':')[0]
        device_domain = "0x%s" % device_domain
        device_bus = pci_id.split(':')[1]
        device_bus = "0x%s" % device_bus
        device_slot = pci_id.split(':')[-1].split('.')[0]
        device_slot = "0x%s" % device_slot
        device_function = pci_id.split('.')[-1]
        device_function = "0x%s" % device_function

        if dev_type == "pci":
            attrs = {'domain': device_domain, 'slot': device_slot,
                     'bus': device_bus, 'function': device_function}
            hostdev_xml.source = hostdev_xml.new_source(**attrs)
        if dev_type == "usb":
            addr_bus = pci_id.split(':')[2]
            addr_device = pci_id.split(':')[3]
            hostdev_xml.source = hostdev_xml.new_source(
                **(dict(vendor_id=device_domain, product_id=device_bus,
                        address_bus=addr_bus, address_device=addr_device)))
    if dev_type == "scsi":
        id_parts = pci_id.split(':')
        hostdev_xml.source = hostdev_xml.new_source(
            **(dict(adapter_name="scsi_host%s" % id_parts[0], bus=id_parts[1],
                    target=id_parts[2], unit=id_parts[3])))

    logging.debug("Hostdev XML:\n%s", str(hostdev_xml))
    if not xmlfile:
        return hostdev_xml
    return hostdev_xml.xml


def add_controller(vm_name, contr):
    """
    Add a specified controller to the vm xml
    :param vm_name: The vm name to be added with a controller
    :param contr: The controller object to be added
    :raise: exceptions.TestFail if the controller can't be added
    """
    vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm_name)
    org_controllers = vmxml.get_controllers(contr.type)
    vmxml.add_device(contr)
    vmxml.sync()
    vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm_name)
    updated_controllers = vmxml.get_controllers(contr.type)
    for one_contr in updated_controllers:
        if one_contr not in org_controllers:
            new_added_ctr = one_contr
    if 'new_added_ctr' not in locals():
        raise exceptions.TestFail("Fail to get new added controller.")


def create_controller_xml(contr_dict):
    """
    Create a controller xml

    :param contr_dict: The dict params includs controller configurations
    :return: new controller created
    """
    contr_type = contr_dict.get("controller_type", 'scsi')
    contr_model = contr_dict.get("controller_model", "virtio-scsi")
    contr_index = contr_dict.get("controller_index")
    contr_alias = contr_dict.get("contr_alias")
    contr_addr = contr_dict.get("controller_addr")
    contr_target = contr_dict.get("controller_target")
    contr_node = contr_dict.get("controller_node")
    contr = controller.Controller(contr_type)
    contr.model = contr_model
    if contr_index:
        contr.index = contr_index
    if contr_alias:
        contr.alias = dict(name=contr_alias)
    if contr_target:
        contr.target = eval(contr_target)
    if contr_node:
        contr.node = contr_node
    if contr_addr:
        contr.address = contr.new_controller_address(attrs=eval(contr_addr))

    return contr


def create_redirdev_xml(redir_type="spicevmc", redir_bus="usb",
                        redir_alias=None, redir_params={}):
    """
    Create redirdev xml

    :param redir_type: redirdev type name
    :param redir_bus: redirdev bus type
    :param redir_alias: redirdev alias name
    :param redir_params: others redir xml parameters
    :return redirdev xml file
    """
    redir = redirdev.Redirdev(redir_type)
    redir.type = redir_type
    redir.bus = redir_bus
    if redir_alias:
        redir.alias = dict(name=redir_alias)
    redir_source = redir_params.get("source")
    if redir_source:
        redir_source_dict = eval(redir_source)
        redir.source = redir.new_source(**redir_source_dict)
    redir_protocol = redir_params.get("protocol")
    if redir_protocol:
        redir.protocol = eval(redir_protocol)

    return redir.xml


def alter_boot_order(vm_name, pci_id, boot_order=0):
    """
    Alter the startup sequence of VM to PCI-device firstly

    OS boot element and per-device boot elements are mutually exclusive,
    It's necessary that remove all OS boots before setting PCI-device order

    :param vm_name: VM name
    :param pci_id:  such as "0000:06:00.1"
    :param boot_order: order priority, such as 1, 2, ...
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    # remove all of OS boots
    vmxml.remove_all_boots()
    # prepare PCI-device XML with boot order
    try:
        device_domain = pci_id.split(':')[0]
        device_domain = "0x%s" % device_domain
        device_bus = pci_id.split(':')[1]
        device_bus = "0x%s" % device_bus
        device_slot = pci_id.split(':')[-1].split('.')[0]
        device_slot = "0x%s" % device_slot
        device_function = pci_id.split('.')[-1]
        device_function = "0x%s" % device_function
    except IndexError:
        raise exceptions.TestError("Invalid PCI Info: %s" % pci_id)
    attrs = {'domain': device_domain, 'slot': device_slot,
             'bus': device_bus, 'function': device_function}
    vmxml.add_hostdev(attrs, boot_order=boot_order)
    # synchronize XML
    vmxml.sync()


def create_disk_xml(params):
    """
    Create a disk configuration file.
    """
    # Create attributes dict for disk's address element
    type_name = params.get("type_name", "file")
    target_dev = params.get("target_dev", "vdb")
    target_bus = params.get("target_bus", "virtio")
    diskxml = disk.Disk(type_name)
    diskxml.device = params.get("device_type", "disk")
    snapshot_attr = params.get('disk_snapshot_attr')
    slice_in_source = params.get('disk_slice')
    # After libvirt 3.9.0, auth element can be placed in source part.
    # Use auth_in_source to diff whether it is placed in source or disk itself.
    auth_in_source = params.get('auth_in_source')
    input_source_file = params.get("input_source_file")
    if snapshot_attr:
        diskxml.snapshot = snapshot_attr
    source_attrs = {}
    source_host = []
    source_seclabel = []
    auth_attrs = {}
    driver_attrs = {}
    try:
        if type_name == "file":
            source_file = params.get("source_file", "")
            source_attrs = {'file': source_file}
            if slice_in_source:
                source_attrs = {'file': input_source_file}
        elif type_name == "block":
            source_file = params.get("source_file", "")
            source_attrs = {'dev': source_file}
        elif type_name == "dir":
            source_dir = params.get("source_dir", "")
            source_attrs = {'dir': source_dir}
        elif type_name == "volume":
            source_pool = params.get("source_pool")
            source_volume = params.get("source_volume")
            source_mode = params.get("source_mode", "")
            source_attrs = {'pool': source_pool, 'volume': source_volume}
            if source_mode:
                source_attrs.update({"mode": source_mode})
        elif type_name == "network":
            source_protocol = params.get("source_protocol")
            source_name = params.get("source_name")
            source_host_name = params.get("source_host_name").split()
            source_host_port = params.get("source_host_port").split()
            transport = params.get("transport")
            source_attrs = {'protocol': source_protocol, 'name': source_name}
            source_host = []
            for host_name, host_port in list(
                    zip(source_host_name, source_host_port)):
                source_host.append({'name': host_name,
                                    'port': host_port})
            if transport:
                source_host[0].update({'transport': transport})
        else:
            exceptions.TestSkipError("Unsupport disk type %s" % type_name)
        source_startupPolicy = params.get("source_startupPolicy")
        if source_startupPolicy:
            source_attrs['startupPolicy'] = source_startupPolicy

        sec_model = params.get("sec_model")
        relabel = params.get("relabel")
        label = params.get("sec_label")
        if sec_model or relabel:
            sec_dict = {}
            sec_xml = seclabel.Seclabel()
            if sec_model:
                sec_dict.update({'model': sec_model})
            if relabel:
                sec_dict.update({'relabel': relabel})
            if label:
                sec_dict.update({'label': label})
            sec_xml.update(sec_dict)
            logging.debug("The sec xml is %s", sec_xml.xmltreefile)
            source_seclabel.append(sec_xml)

        source_params = {"attrs": source_attrs, "seclabels": source_seclabel,
                         "hosts": source_host}
        src_config_file = params.get("source_config_file")
        if src_config_file:
            source_params.update({"config_file": src_config_file})
            # If we use config file, "hosts" isn't needed
            if "hosts" in source_params:
                source_params.pop("hosts")
        snapshot_name = params.get('source_snap_name')
        if snapshot_name:
            source_params.update({"snapshot_name": snapshot_name})
        disk_source = diskxml.new_disk_source(**source_params)
        auth_user = params.get("auth_user")
        secret_type = params.get("secret_type")
        secret_uuid = params.get("secret_uuid")
        secret_usage = params.get("secret_usage")
        if auth_user:
            auth_attrs['auth_user'] = auth_user
        if secret_type:
            auth_attrs['secret_type'] = secret_type
        if secret_uuid:
            auth_attrs['secret_uuid'] = secret_uuid
        elif secret_usage:
            auth_attrs['secret_usage'] = secret_usage
        if auth_attrs:
            if auth_in_source:
                disk_source.auth = diskxml.new_auth(**auth_attrs)
            else:
                diskxml.auth = diskxml.new_auth(**auth_attrs)
        if slice_in_source:
            if slice_in_source.get('slice_size', None):
                disk_source.slices = diskxml.new_slices(**slice_in_source)
            else:
                slice_size_param = process.run("du -b %s" % input_source_file).stdout_text.strip()
                slice_size = re.findall(r'^[0-9]+', slice_size_param)
                slice_size = ''.join(slice_size)
                disk_source.slices = diskxml.new_slices(**{"slice_type": "storage", "slice_offset": "0",
                                                           "slice_size": slice_size})
        diskxml.source = disk_source
        driver_name = params.get("driver_name", "qemu")
        driver_type = params.get("driver_type", "")
        driver_cache = params.get("driver_cache", "")
        driver_discard = params.get("driver_discard", "")
        driver_model = params.get("model")
        if driver_name:
            driver_attrs['name'] = driver_name
        if driver_type:
            driver_attrs['type'] = driver_type
        if driver_cache:
            driver_attrs['cache'] = driver_cache
        if driver_discard:
            driver_attrs['discard'] = driver_discard
        if driver_attrs:
            diskxml.driver = driver_attrs
        if driver_model:
            diskxml.model = driver_model
        diskxml.readonly = "yes" == params.get("readonly", "no")
        diskxml.share = "yes" == params.get("shareable", "no")
        diskxml.target = {'dev': target_dev, 'bus': target_bus}
        alias = params.get('alias')
        if alias:
            diskxml.alias = {'name': alias}
        sgio = params.get('sgio')
        if sgio:
            diskxml.sgio = sgio
        rawio = params.get('rawio')
        if rawio:
            diskxml.rawio = rawio
        diskxml.xmltreefile.write()
    except Exception as detail:
        logging.error("Fail to create disk XML:\n%s", detail)
    logging.debug("Disk XML %s:\n%s", diskxml.xml, str(diskxml))

    # Wait for file completed
    def file_exists():
        if not process.run("ls %s" % diskxml.xml,
                           ignore_status=True).exit_status:
            return True
    utils_misc.wait_for(file_exists, 5)

    return diskxml.xml


def set_disk_attr(vmxml, target, tag, attr):
    """
    Set value of disk tag attributes for a given target dev.
    :param vmxml: domain VMXML instance
    :param target: dev of the disk
    :param tag: disk tag
    :param attr: the tag attribute dict to set

    :return: True if success, otherwise, False
    """
    key = ""
    try:
        disk = vmxml.get_disk_all()[target]
        if tag in ["driver", "boot", "address", "alias", "source"]:
            for key in attr:
                disk.find(tag).set(key, attr[key])
                logging.debug("key '%s' value '%s' pair is "
                              "set", key, attr[key])
            vmxml.xmltreefile.write()
        else:
            logging.debug("tag '%s' is not supported now", tag)
            return False
    except AttributeError:
        logging.error("Fail to set attribute '%s' with value "
                      "'%s'.", key, attr[key])
        return False

    return True


def create_net_xml(net_name, params):
    """
    Create a new network or update an existed network xml
    """
    dns_dict = {}
    host_dict = {}
    net_bridge = params.get("net_bridge", '{}')
    net_forward = params.get("net_forward", '{}')
    net_forward_pf = params.get("net_forward_pf", '{}')
    forward_iface = params.get("forward_iface")
    net_dns_forward = params.get("net_dns_forward")
    net_dns_txt = params.get("net_dns_txt")
    net_dns_srv = params.get("net_dns_srv")
    net_dns_forwarders = params.get("net_dns_forwarders", "").split()
    net_dns_hostip = params.get("net_dns_hostip")
    net_dns_hostnames = params.get("net_dns_hostnames", "").split()
    net_domain = params.get("net_domain")
    net_virtualport = params.get("net_virtualport")
    net_bandwidth_inbound = params.get("net_bandwidth_inbound", "{}")
    net_bandwidth_outbound = params.get("net_bandwidth_outbound", "{}")
    net_ip_family = params.get("net_ip_family")
    net_ip_address = params.get("net_ip_address")
    net_ip_netmask = params.get("net_ip_netmask", "255.255.255.0")
    net_ipv6_address = params.get("net_ipv6_address")
    net_ipv6_prefix = params.get("net_ipv6_prefix", "64")
    nat_attrs = params.get('nat_attrs', '{}')
    nat_port = params.get("nat_port")
    guest_name = params.get("guest_name")
    guest_ipv4 = params.get("guest_ipv4")
    guest_ipv6 = params.get("guest_ipv6")
    guest_mac = params.get("guest_mac")
    dhcp_start_ipv4 = params.get("dhcp_start_ipv4", "192.168.122.2")
    dhcp_end_ipv4 = params.get("dhcp_end_ipv4", "192.168.122.254")
    dhcp_start_ipv6 = params.get("dhcp_start_ipv6")
    dhcp_end_ipv6 = params.get("dhcp_end_ipv6")
    tftp_root = params.get("tftp_root")
    bootp_file = params.get("bootp_file")
    routes = params.get("routes", "").split()
    pg_name = params.get("portgroup_name", "").split()
    net_port = params.get('net_port')
    try:
        if not virsh.net_info(net_name, ignore_status=True).exit_status:
            # Edit an existed network
            netxml = network_xml.NetworkXML.new_from_net_dumpxml(net_name)
            netxml.del_ip()
        else:
            netxml = network_xml.NetworkXML(net_name)
        if net_dns_forward:
            dns_dict["dns_forward"] = net_dns_forward
        if net_dns_txt:
            dns_dict["txt"] = ast.literal_eval(net_dns_txt)
        if net_dns_srv:
            dns_dict["srv"] = ast.literal_eval(net_dns_srv)
        if net_dns_forwarders:
            dns_dict["forwarders"] = [ast.literal_eval(x) for x in
                                      net_dns_forwarders]
        if net_dns_hostip:
            host_dict["host_ip"] = net_dns_hostip
        if net_dns_hostnames:
            host_dict["hostnames"] = net_dns_hostnames

        dns_obj = netxml.new_dns(**dns_dict)
        if host_dict:
            host = dns_obj.new_host(**host_dict)
            dns_obj.host = host
        netxml.dns = dns_obj
        bridge = ast.literal_eval(net_bridge)
        if bridge:
            netxml.bridge = bridge
        forward = ast.literal_eval(net_forward)
        if forward:
            netxml.forward = forward
        forward_pf = ast.literal_eval(net_forward_pf)
        if forward_pf:
            netxml.pf = forward_pf
        if forward_iface:
            interface = [
                {'dev': x} for x in forward_iface.split()]
            netxml.forward_interface = interface
        nat_attrs = ast.literal_eval(nat_attrs)
        if nat_attrs:
            netxml.nat_attrs = nat_attrs
        if nat_port:
            netxml.nat_port = ast.literal_eval(nat_port)
        if net_domain:
            netxml.domain_name = net_domain
        net_inbound = ast.literal_eval(net_bandwidth_inbound)
        net_outbound = ast.literal_eval(net_bandwidth_outbound)
        if net_inbound:
            netxml.bandwidth_inbound = net_inbound
        if net_outbound:
            netxml.bandwidth_outbound = net_outbound
        if net_virtualport:
            netxml.virtualport_type = net_virtualport
        if net_port:
            netxml.port = ast.literal_eval(net_port)
        if net_ip_family == "ipv6":
            ipxml = network_xml.IPXML()
            ipxml.family = net_ip_family
            ipxml.prefix = net_ipv6_prefix
            del ipxml.netmask
            if net_ipv6_address:
                ipxml.address = net_ipv6_address
            if dhcp_start_ipv6 and dhcp_end_ipv6:
                ipxml.dhcp_ranges = {"start": dhcp_start_ipv6,
                                     "end": dhcp_end_ipv6}
            if guest_name and guest_ipv6 and guest_mac:
                ipxml.hosts = [{"name": guest_name,
                                "ip": guest_ipv6}]
            netxml.set_ip(ipxml)
        if net_ip_address:
            ipxml = network_xml.IPXML(net_ip_address,
                                      net_ip_netmask)
            if dhcp_start_ipv4 and dhcp_end_ipv4:
                ipxml.dhcp_ranges = {"start": dhcp_start_ipv4,
                                     "end": dhcp_end_ipv4}
            if tftp_root:
                ipxml.tftp_root = tftp_root
            if bootp_file:
                ipxml.dhcp_bootp = bootp_file
            if guest_name and guest_ipv4 and guest_mac:
                ipxml.hosts = [{"mac": guest_mac,
                                "name": guest_name,
                                "ip": guest_ipv4}]
            netxml.set_ip(ipxml)
        if routes:
            netxml.routes = [ast.literal_eval(x) for x in routes]
        if pg_name:
            pg_default = params.get("portgroup_default",
                                    "").split()
            pg_virtualport = params.get(
                "portgroup_virtualport", "").split()
            pg_bandwidth_inbound = params.get(
                "portgroup_bandwidth_inbound", "").split()
            pg_bandwidth_outbound = params.get(
                "portgroup_bandwidth_outbound", "").split()
            pg_vlan = params.get("portgroup_vlan", "").split()
            for i in range(len(pg_name)):
                pgxml = network_xml.PortgroupXML()
                pgxml.name = pg_name[i]
                if len(pg_default) > i:
                    pgxml.default = pg_default[i]
                if len(pg_virtualport) > i:
                    pgxml.virtualport_type = pg_virtualport[i]
                if len(pg_bandwidth_inbound) > i:
                    pgxml.bandwidth_inbound = ast.literal_eval(
                        pg_bandwidth_inbound[i])
                if len(pg_bandwidth_outbound) > i:
                    pgxml.bandwidth_outbound = ast.literal_eval(
                        pg_bandwidth_outbound[i])
                if len(pg_vlan) > i:
                    pgxml.vlan_tag = ast.literal_eval(pg_vlan[i])
                netxml.set_portgroup(pgxml)
        logging.debug("New network xml file: %s", netxml)
        netxml.xmltreefile.write()
        return netxml
    except Exception as detail:
        stacktrace.log_exc_info(sys.exc_info())
        raise exceptions.TestFail("Fail to create network XML: %s" % detail)


def create_nwfilter_xml(params):
    """
    Create a new network filter or update an existed network filter xml
    """
    filter_name = params.get("filter_name", "testcase")
    exist_filter = params.get("exist_filter", "no-mac-spoofing")
    filter_chain = params.get("filter_chain")
    filter_priority = params.get("filter_priority", "")
    filter_uuid = params.get("filter_uuid")

    # process filterref_name
    filterrefs_list = []
    filterrefs_key = []
    for i in list(params.keys()):
        if 'filterref_name_' in i:
            filterrefs_key.append(i)
    filterrefs_key.sort()
    for i in filterrefs_key:
        filterrefs_dict = {}
        filterrefs_dict['filter'] = params[i]
        filterrefs_list.append(filterrefs_dict)

    # prepare rule and protocol attributes
    protocol = {}
    rule_dict = {}
    rule_dict_tmp = {}
    RULE_ATTR = ('rule_action', 'rule_direction', 'rule_priority',
                 'rule_statematch')
    PROTOCOL_TYPES = ['mac', 'vlan', 'stp', 'arp', 'rarp', 'ip', 'ipv6',
                      'tcp', 'udp', 'sctp', 'icmp', 'igmp', 'esp', 'ah',
                      'udplite', 'all', 'tcp-ipv6', 'udp-ipv6', 'sctp-ipv6',
                      'icmpv6', 'esp-ipv6', 'ah-ipv6', 'udplite-ipv6',
                      'all-ipv6']
    # rule should end with 'EOL' as separator, multiple rules are supported
    rule = params.get("rule")
    if rule:
        rule_list = rule.split('EOL')
        for i in range(len(rule_list)):
            if rule_list[i]:
                attr = rule_list[i].split()
                for j in range(len(attr)):
                    attr_list = attr[j].split('=')
                    rule_dict_tmp[attr_list[0]] = attr_list[1]
                rule_dict[i] = rule_dict_tmp
                rule_dict_tmp = {}

        # process protocol parameter
        for i in list(rule_dict.keys()):
            if 'protocol' not in rule_dict[i]:
                # Set protocol as string 'None' as parse from cfg is
                # string 'None'
                protocol[i] = 'None'
            else:
                protocol[i] = rule_dict[i]['protocol']
                rule_dict[i].pop('protocol')

                if protocol[i] in PROTOCOL_TYPES:
                    # replace '-' with '_' in ipv6 types as '-' is not
                    # supposed to be in class name
                    if '-' in protocol[i]:
                        protocol[i] = protocol[i].replace('-', '_')
                else:
                    raise exceptions.TestFail("Given protocol type %s"
                                              " is not in supported list %s"
                                              % (protocol[i], PROTOCOL_TYPES))

    try:
        new_filter = nwfilter_xml.NwfilterXML()
        filterxml = new_filter.new_from_filter_dumpxml(exist_filter)

        # Set filter attribute
        filterxml.filter_name = filter_name
        filterxml.filter_priority = filter_priority
        if filter_chain:
            filterxml.filter_chain = filter_chain
        if filter_uuid:
            filterxml.uuid = filter_uuid
        filterxml.filterrefs = filterrefs_list

        # Set rule attribute
        index_total = filterxml.get_rule_index()
        rule = filterxml.get_rule(0)
        rulexml = rule.backup_rule()
        for i in index_total:
            filterxml.del_rule()
        for i in range(len(list(rule_dict.keys()))):
            rulexml.rule_action = rule_dict[i].get('rule_action')
            rulexml.rule_direction = rule_dict[i].get('rule_direction')
            rulexml.rule_priority = rule_dict[i].get('rule_priority')
            rulexml.rule_statematch = rule_dict[i].get('rule_statematch')
            for j in RULE_ATTR:
                if j in list(rule_dict[i].keys()):
                    rule_dict[i].pop(j)

            # set protocol attribute
            if protocol[i] != 'None':
                protocolxml = rulexml.get_protocol(protocol[i])
                new_one = protocolxml.new_attr(**rule_dict[i])
                protocolxml.attrs = new_one
                rulexml.xmltreefile = protocolxml.xmltreefile
            else:
                rulexml.del_protocol()

            filterxml.add_rule(rulexml)

            # Reset rulexml
            rulexml = rule.backup_rule()

        filterxml.xmltreefile.write()
        logging.info("The network filter xml is:\n%s" % filterxml)
        return filterxml

    except Exception as detail:
        stacktrace.log_exc_info(sys.exc_info())
        raise exceptions.TestFail("Fail to create nwfilter XML: %s" % detail)


def create_channel_xml(params, alias=False, address=False):
    """
    Create a XML contains channel information.

    :param params: the params for Channel slot
    :param alias: allow to add 'alias' slot
    :param address: allow to add 'address' slot
    """
    # Create attributes dict for channel's element
    channel_source = {}
    channel_target = {}
    channel_alias = {}
    channel_address = {}
    channel_params = {}

    channel_type_name = params.get("channel_type_name")
    source_mode = params.get("source_mode")
    source_path = params.get("source_path")
    target_type = params.get("target_type")
    target_name = params.get("target_name")

    if channel_type_name is None:
        raise exceptions.TestFail("channel_type_name not specified.")
    # if these params are None, it won't be used.
    if source_mode:
        channel_source['mode'] = source_mode
    if source_path:
        channel_source['path'] = source_path
    if target_type:
        channel_target['type'] = target_type
    if target_name:
        channel_target['name'] = target_name

    channel_params = {'type_name': channel_type_name,
                      'source': channel_source,
                      'target': channel_target}
    if alias:
        if isinstance(alias, str):
            channel_alias = alias
        else:
            channel_alias = target_name
        channel_params['alias'] = {'name': channel_alias}
    if address:
        channel_address = {'type': 'virtio-serial',
                           'controller': '0',
                           'bus': '0'}
        channel_params['address'] = channel_address
    channelxml = channel.Channel.new_from_dict(channel_params)
    logging.debug("Channel XML:\n%s", channelxml)
    return channelxml


def update_on_crash(vm_name, on_crash):
    """
    Update on_crash state of vm

    :param vm_name: name of vm
    :param on_crash: on crash state, destroy, restart ...
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    vmxml.on_crash = on_crash
    vmxml.sync()


def add_panic_device(vm_name, model='isa', addr_type='isa', addr_iobase='0x505'):
    """
    Create panic device xml

    :param vm_name: name of vm
    :param model: panic model
    :param addr_type: address type
    :param addr_iobase: address iobase
    :return: If dev exist, return False, else return True
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    panic_dev = vmxml.xmltreefile.find('devices/panic')
    if panic_dev is not None:
        logging.info("Panic device already exists")
        return False
    else:
        panic_dev = panic.Panic()
        panic_dev.model = model
        panic_dev.addr_type = addr_type
        panic_dev.addr_iobase = addr_iobase
        vmxml.add_device(panic_dev)
        vmxml.sync()
        return True


def set_domain_state(vm, vm_state):
    """
    Set domain state.

    :param vm: the vm object
    :param vm_state: the given vm state string "shut off", "running"
                     "paused", "halt" or "pm_suspend"
    """
    # reset domain state
    if vm.is_alive():
        vm.destroy(gracefully=False)
    if not vm_state == "shut off":
        vm.start()
        session = vm.wait_for_login()
    if vm_state == "paused":
        vm.pause()
    elif vm_state == "halt":
        try:
            session.cmd("halt")
        except (aexpect.ShellProcessTerminatedError, aexpect.ShellStatusError):
            # The halt command always gets these errors, but execution is OK,
            # skip these errors
            pass
    elif vm_state == "pm_suspend":
        # Execute "pm-suspend-hybrid" command directly will get Timeout error,
        # so here execute it in background, and wait for 3s manually
        if session.cmd_status("which pm-suspend-hybrid"):
            raise exceptions.TestSkipError("Cannot execute this test for domain"
                                           " doesn't have pm-suspend-hybrid command!")
        session.cmd("pm-suspend-hybrid &")
        time.sleep(3)


def create_vsock_xml(model, auto_cid='yes', invalid_cid=False):
    """
    Create vsock xml

    :param model: device model
    :param auto_cid: "yes" or "no"
    :param invalid_cid: True or False for cid valid or not
    :return: vsock device
    """
    vsock_dev = vsock.Vsock()
    vsock_dev.model_type = model
    if process.run("modprobe vhost_vsock").exit_status != 0:
        raise exceptions.TestError("Failed to load vhost_vsock module")
    if invalid_cid:
        cid = "-1"
    else:
        cid = random.randint(3, 10)
    vsock_dev.cid = {'auto': auto_cid, 'address': cid}
    chars = string.ascii_letters + string.digits + '-_'
    alias_name = 'ua-' + ''.join(random.choice(chars) for _ in list(range(64)))
    vsock_dev.alias = {'name': alias_name}
    logging.debug(vsock_dev)
    return vsock_dev


def create_rng_xml(dparams):
    """
    Modify interface xml options

    :param dparams: Rng device paramter dict
    """
    rng_model = dparams.get("rng_model", "virtio")
    rng_rate = dparams.get("rng_rate")
    backend_model = dparams.get("backend_model", "random")
    backend_type = dparams.get("backend_type")
    backend_dev = dparams.get("backend_dev", "/dev/urandom")
    backend_source_list = dparams.get("backend_source",
                                      "").split()
    backend_protocol = dparams.get("backend_protocol")
    rng_alias = dparams.get("rng_alias")

    rng_xml = rng.Rng()
    rng_xml.rng_model = rng_model
    if rng_rate:
        rng_xml.rate = ast.literal_eval(rng_rate)
    backend = rng.Rng.Backend()
    backend.backend_model = backend_model
    if backend_type:
        backend.backend_type = backend_type
    if backend_dev:
        backend.backend_dev = backend_dev
    if backend_source_list:
        source_list = [ast.literal_eval(source) for source in
                       backend_source_list]
        backend.source = source_list
    if backend_protocol:
        backend.backend_protocol = backend_protocol
    rng_xml.backend = backend
    if rng_alias:
        rng_xml.alias = dict(name=rng_alias)

    logging.debug("Rng xml: %s", rng_xml)
    return rng_xml


def update_memballoon_xml(vmxml, membal_dict):
    """
    Add/update memballoon attr

    :param vmxml: VMXML object
    :param membal_dict: memballoon parameter dict
    """
    membal_model = membal_dict.get("membal_model")
    membal_stats_period = membal_dict.get("membal_stats_period")
    vmxml.del_device('memballoon', by_tag=True)
    memballoon_xml = vmxml.get_device_class('memballoon')()
    if membal_model:
        memballoon_xml.model = membal_model
    if membal_stats_period:
        memballoon_xml.stats_period = membal_stats_period
    vmxml.add_device(memballoon_xml)
    logging.info(memballoon_xml)
    vmxml.sync()


def create_tpm_dev(params):
    """
    Create tpm device instance

    :param params: tpm parameter dict
    :return: tpm device
    """
    tpm_model = params.get("tpm_model", 'tpm-crb')
    backend_type = params.get("backend_type")
    backend_version = params.get("backend_version")
    encryption_secret = params.get("encryption_secret")
    device_path = params.get("device_path")

    tpm_dev = tpm.Tpm()
    tpm_dev.tpm_model = tpm_model
    if backend_type:
        tpm_backend = tpm_dev.Backend()
        tpm_backend.backend_type = backend_type
        if backend_version:
            tpm_backend.backend_version = backend_version
        if encryption_secret:
            tpm_backend.encryption_secret = encryption_secret
        if device_path:
            tpm_backend.device_path = device_path
        tpm_dev.backend = tpm_backend
    return tpm_dev


def get_vm_device(vmxml, dev_tag, index=0):
    """
    Get current vm device according to device tag

    :param vmxml: domain VMXML instance
    :param dev_tag: device tag
    :param index: device index
    :return: device object
    """
    xml_devices = vmxml.devices
    dev_index = xml_devices.index(xml_devices.by_device_tag(dev_tag)[index])
    dev_obj = xml_devices[dev_index]
    return (dev_obj, xml_devices)


def add_vm_device(vmxml, new_device):
    """
    Add device in vmxml

    :param vmxml: domain VMXML instance
    :param new_device: device instance
    """
    vmxml.add_device(new_device)
    vmxml.xmltreefile.write()
    vmxml.sync()


def set_guest_agent(vm):
    """
    Set domain xml with guest agent channel and install guest agent rpm
    in domain.

    :param vm: the vm object
    """
    logging.warning("This function is going to be deprecated. "
                    "Please use vm.prepare_guest_agent() instead.")
    # reset domain state
    if vm.is_alive():
        vm.destroy(gracefully=False)
    vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm.name)
    logging.debug("Attempting to set guest agent channel")
    vmxml.set_agent_channel()
    vmxml.sync()
    vm.start()
    session = vm.wait_for_login()
    # Check if qemu-ga already started automatically
    cmd = "rpm -q qemu-guest-agent || yum install -y qemu-guest-agent"
    stat_install = session.cmd_status(cmd, 300)
    if stat_install != 0:
        raise exceptions.TestFail("Fail to install qemu-guest-agent, make "
                                  "sure that you have usable repo in guest")

    # Check if qemu-ga already started
    stat_ps = session.cmd_status("ps aux |grep [q]emu-ga")
    if stat_ps != 0:
        session.cmd("qemu-ga -d")
        # Check if the qemu-ga really started
        stat_ps = session.cmd_status("ps aux |grep [q]emu-ga")
        if stat_ps != 0:
            raise exceptions.TestFail("Fail to run qemu-ga in guest")


def set_vm_disk(vm, params, tmp_dir=None, test=None):
    """
    Replace vm first disk with given type in domain xml, including file type
    (local, nfs), network type(gluster, iscsi), block type(use connected iscsi
    block disk).

    For all types, all following params are common and need be specified:

        disk_device: default to 'disk'
        disk_type: 'block' or 'network'
        disk_target: default to 'vda'
        disk_target_bus: default to 'virtio'
        disk_format: default to 'qcow2'
        disk_src_protocol: 'iscsi', 'gluster' or 'netfs'

    For 'gluster' network type, following params are gluster only and need be
    specified:

        vol_name: string
        pool_name: default to 'gluster-pool'
        transport: 'tcp', 'rdma' or '', default to ''

    For 'iscsi' network type, following params need be specified:

        image_size: default to "10G", 10G is raw size of jeos disk
        disk_src_host: default to "127.0.0.1"
        disk_src_port: default to "3260"

    For 'netfs' network type, following params need be specified:

        mnt_path_name: the mount dir name, default to "nfs-mount"
        export_options: nfs mount options, default to "rw,no_root_squash,fsid=0"

    For 'block' type, using connected iscsi block disk, following params need
    be specified:

        image_size: default to "10G", 10G is raw size of jeos disk

    :param vm: the vm object
    :param tmp_dir: string, dir path
    :param params: dict, dict include setup vm disk xml configurations
    """
    vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm.name)
    logging.debug("original xml is: %s", vmxml.xmltreefile)
    disk_device = params.get("disk_device", "disk")
    disk_snapshot_attr = params.get("disk_snapshot_attr")
    disk_type = params.get("disk_type", "file")
    disk_target = params.get("disk_target", 'vda')
    disk_target_bus = params.get("disk_target_bus", "virtio")
    disk_model = params.get("disk_model")
    disk_src_protocol = params.get("disk_source_protocol")
    disk_src_name = params.get("disk_source_name")
    disk_src_host = params.get("disk_source_host", "127.0.0.1")
    disk_src_port = params.get("disk_source_port", "3260")
    disk_src_config = params.get("disk_source_config")
    disk_snap_name = params.get("disk_snap_name")
    emu_image = params.get("emulated_image", "emulated-iscsi")
    image_size = params.get("image_size", "10G")
    disk_format = params.get("disk_format", "qcow2")
    driver_iothread = params.get("driver_iothread", "")
    mnt_path_name = params.get("mnt_path_name", "nfs-mount")
    exp_opt = params.get("export_options", "rw,no_root_squash,fsid=0")
    exp_dir = params.get("export_dir", "nfs-export")
    first_disk = vm.get_first_disk_devices()
    logging.debug("first disk is %s", first_disk)
    blk_source = first_disk['source']
    blk_source = params.get("blk_source_name", blk_source)
    disk_xml = vmxml.devices.by_device_tag('disk')[0]
    src_disk_format = disk_xml.xmltreefile.find('driver').get('type')
    sec_model = params.get('sec_model')
    relabel = params.get('relabel')
    sec_label = params.get('sec_label')
    image_owner_group = params.get('image_owner_group')
    pool_name = params.get("pool_name", "set-vm-disk-pool")
    disk_src_mode = params.get('disk_src_mode', 'host')
    auth_user = params.get("auth_user")
    secret_type = params.get("secret_type")
    secret_usage = params.get("secret_usage")
    secret_uuid = params.get("secret_uuid")
    enable_cache = "yes" == params.get("enable_cache", "yes")
    driver_cache = params.get("driver_cache", "none")
    create_controller = "yes" == params.get("create_controller")
    del_disks = "yes" == params.get("cleanup_disks", 'no')
    disk_params = {'device_type': disk_device,
                   'disk_snapshot_attr': disk_snapshot_attr,
                   'type_name': disk_type,
                   'target_dev': disk_target,
                   'target_bus': disk_target_bus,
                   'driver_type': disk_format,
                   'driver_iothread': driver_iothread,
                   'sec_model': sec_model,
                   'relabel': relabel,
                   'sec_label': sec_label,
                   'auth_user': auth_user,
                   'secret_type': secret_type,
                   'secret_uuid': secret_uuid,
                   'secret_usage': secret_usage}

    if enable_cache:
        disk_params['driver_cache'] = driver_cache
    if disk_model:
        disk_params['model'] = disk_model
    if not tmp_dir:
        tmp_dir = data_dir.get_tmp_dir()

    # gluster only params
    vol_name = params.get("vol_name")
    transport = params.get("transport", "")
    brick_path = os.path.join(tmp_dir, pool_name)
    image_convert = "yes" == params.get("image_convert", 'yes')

    if vm.is_alive():
        vm.destroy(gracefully=False)
    # Replace domain disk with iscsi, gluster, block or netfs disk
    if disk_src_protocol == 'iscsi':
        if disk_type == 'block':
            is_login = True
        elif disk_type == 'network' or disk_type == 'volume':
            is_login = False
        else:
            raise exceptions.TestFail("Disk type '%s' not expected, only disk "
                                      "type 'block', 'network' or 'volume' work "
                                      "with 'iscsi'" % disk_type)

        if disk_type == 'volume':
            pvt = PoolVolumeTest(test, params)
            pvt.pre_pool(pool_name, 'iscsi', "/dev/disk/by-path",
                         emulated_image=emu_image,
                         image_size=image_size)
            # Get volume name
            vols = get_vol_list(pool_name)
            vol_name = list(vols.keys())[0]
            emulated_path = vols[vol_name]
        else:
            # Setup iscsi target
            if is_login:
                iscsi_target = setup_or_cleanup_iscsi(
                    is_setup=True, is_login=is_login,
                    image_size=image_size, emulated_image=emu_image)
            else:
                iscsi_target, lun_num = setup_or_cleanup_iscsi(
                    is_setup=True, is_login=is_login,
                    image_size=image_size, emulated_image=emu_image)
            emulated_path = os.path.join(tmp_dir, emu_image)

        # Copy first disk to emulated backing store path
        cmd = "qemu-img convert -f %s -O %s %s %s" % (src_disk_format,
                                                      disk_format,
                                                      blk_source,
                                                      emulated_path)
        process.run(cmd, ignore_status=False)

        if disk_type == 'block':
            disk_params_src = {'source_file': iscsi_target}
        elif disk_type == "volume":
            disk_params_src = {'source_pool': pool_name,
                               'source_volume': vol_name,
                               'source_mode': disk_src_mode}
        else:
            disk_params_src = {'source_protocol': disk_src_protocol,
                               'source_name': iscsi_target + "/" + str(lun_num),
                               'source_host_name': disk_src_host,
                               'source_host_port': disk_src_port}
    elif disk_src_protocol == 'gluster':
        # Setup gluster.
        host_ip = gluster.setup_or_cleanup_gluster(True, brick_path=brick_path,
                                                   **params)
        logging.debug("host ip: %s " % host_ip)
        dist_img = "gluster.%s" % disk_format

        if image_convert:
            # Convert first disk to gluster disk path
            disk_cmd = ("qemu-img convert -f %s -O %s %s /mnt/%s" %
                        (src_disk_format, disk_format, blk_source, dist_img))
        else:
            # create another disk without convert
            disk_cmd = "qemu-img create -f %s /mnt/%s 10M" % (src_disk_format,
                                                              dist_img)

        # Mount the gluster disk and create the image.
        process.run("mount -t glusterfs %s:%s /mnt; %s; umount /mnt"
                    % (host_ip, vol_name, disk_cmd), shell=True)

        disk_params_src = {'source_protocol': disk_src_protocol,
                           'source_name': "%s/%s" % (vol_name, dist_img),
                           'source_host_name': host_ip,
                           'source_host_port': "24007"}
        if transport:
            disk_params_src.update({"transport": transport})
    elif disk_src_protocol == 'netfs':
        # For testing multiple VMs in a test this param can used
        # to setup/cleanup configurations
        src_file_list = params.get("source_file_list", [])
        # Setup nfs
        res = setup_or_cleanup_nfs(True, mnt_path_name,
                                   is_mount=True,
                                   export_options=exp_opt,
                                   export_dir=exp_dir)
        exp_path = res["export_dir"]
        mnt_path = res["mount_dir"]
        params["selinux_status_bak"] = res["selinux_status_bak"]
        dist_img = params.get("source_dist_img", "nfs-img")

        # Convert first disk to gluster disk path
        disk_cmd = ("qemu-img convert -f %s -O %s %s %s/%s" %
                    (src_disk_format, disk_format,
                     blk_source, exp_path, dist_img))
        process.run(disk_cmd, ignore_status=False)

        # Change image ownership
        if image_owner_group:
            update_owner_cmd = ("chown %s %s/%s" %
                                (image_owner_group, exp_path, dist_img))
            process.run(update_owner_cmd, ignore_status=False)

        src_file_path = "%s/%s" % (mnt_path, dist_img)
        if params.get("change_file_uid") and params.get("change_file_gid"):
            logging.debug("Changing the ownership of {} to {}.{}."
                          .format(src_file_path, params["change_file_uid"],
                                  params["change_file_gid"]))
            os.chown(src_file_path, params["change_file_uid"],
                     params["change_file_gid"])
            res = os.stat(src_file_path)
            logging.debug("The ownership of {} is updated, uid: {}, gid: {}."
                          .format(src_file_path, res.st_uid, res.st_gid))
        disk_params_src = {'source_file': src_file_path}
        params["source_file"] = src_file_path
        src_file_list.append(src_file_path)
        params["source_file_list"] = src_file_list
    elif disk_src_protocol == 'rbd':
        mon_host = params.get("mon_host")
        if image_convert:
            disk_cmd = ("qemu-img convert -f %s -O %s %s rbd:%s:mon_host=%s"
                        % (src_disk_format, disk_format, blk_source,
                           disk_src_name, mon_host))
            process.run(disk_cmd, ignore_status=False)
        disk_params_src = {'source_protocol': disk_src_protocol,
                           'source_name': disk_src_name,
                           'source_host_name': disk_src_host,
                           'source_host_port': disk_src_port,
                           'source_config_file': disk_src_config}
        if disk_snap_name:
            disk_params_src.update({'source_snap_name': disk_snap_name})
            disk_params.update({'readonly': params.get("read_only", "no")})
    else:
        """
        If disk_src_name is given, replace current source file
        Otherwise, use current source file with update params.
        """
        if disk_src_name:
            blk_source = disk_src_name
        disk_params_src = {'source_file': blk_source}

    # Delete disk elements
    disk_deleted = False
    disks = vmxml.get_devices(device_type="disk")
    for disk_ in disks:
        if disk_.target['dev'] == disk_target:
            vmxml.del_device(disk_)
            disk_deleted = True
            continue
        if del_disks:
            vmxml.del_device(disk_)
            disk_deleted = True
    if disk_deleted:
        vmxml.sync()
        vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm.name)

    #Create controller
    if create_controller:
        contr_type = params.get("controller_type", 'scsi')
        contr_model = params.get("controller_model", "virtio-scsi")
        contr_index = params.get("controller_index", "0")
        contr_dict = {'controller_type': contr_type,
                      'controller_model': contr_model,
                      'controller_index': contr_index}
        new_added = create_controller_xml(contr_dict)
        add_controller(vm.name, new_added)
        vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm.name)

    # New disk xml
    new_disk = disk.Disk(type_name=disk_type)
    new_disk.new_disk_source(attrs={'file': blk_source})
    disk_params.update(disk_params_src)
    disk_xml = create_disk_xml(disk_params)
    new_disk.xml = disk_xml
    # Add new disk xml and redefine vm
    vmxml.add_device(new_disk)

    # Update disk address
    if create_controller:
        vmxml.sync()
        vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm.name)
        contr_type_from_address = vmxml.get_disk_attr(vm.name, disk_target,
                                                      "address", "type")
        if contr_type_from_address == 'pci':
            address_params = {'bus': "%0#4x" % int(contr_index)}
        elif contr_type_from_address == 'drive':
            address_params = {'controller': contr_index}
        elif contr_type_from_address == 'usb':
            address_params = {'bus': contr_index}
        else:
            # TODO: Other controller types
            pass
        if not set_disk_attr(vmxml, disk_target, 'address', address_params):
            raise exceptions.TestFail("Fail to update disk address.")

    # Set domain options
    dom_iothreads = params.get("dom_iothreads")
    if dom_iothreads:
        vmxml.iothreads = int(dom_iothreads)
    logging.debug("The vm xml now is: %s" % vmxml.xmltreefile)
    vmxml.sync()
    vm.start()


def attach_additional_device(vm_name, targetdev, disk_path, params, config=True):
    """
    Create a disk with disksize, then attach it to given vm.

    :param vm_name: Libvirt VM name.
    :param disk_path: path of attached disk
    :param targetdev: target of disk device
    :param params: dict include necessary configurations of device
    """
    logging.info("Attaching disk...")

    # Update params for source file
    params['source_file'] = disk_path
    params['target_dev'] = targetdev

    # Create a file of device
    xmlfile = create_disk_xml(params)

    # To confirm attached device do not exist.
    if config:
        extra = "--config"
    else:
        extra = ""
    virsh.detach_disk(vm_name, targetdev, extra=extra)

    return virsh.attach_device(domain_opt=vm_name, file_opt=xmlfile,
                               flagstr=extra, debug=True)


def device_exists(vm, target_dev):
    """
    Check if given target device exists on vm.
    """
    targets = list(vm.get_blk_devices().keys())
    if target_dev in targets:
        return True
    return False


def create_local_disk(disk_type, path=None,
                      size="10", disk_format="raw",
                      vgname=None, lvname=None, extra=''):
    if disk_type != "lvm" and path is None:
        raise exceptions.TestError("Path is needed for creating local disk")
    if path:
        process.run("mkdir -p %s" % os.path.dirname(path))
    try:
        size = str(float(size)) + "G"
    except ValueError:
        pass
    cmd = ""
    if disk_type == "file":
        cmd = "qemu-img create -f %s %s %s %s" % (disk_format, extra, path, size)
    elif disk_type == "floppy":
        cmd = "dd if=/dev/zero of=%s count=1024 bs=1024" % path
    elif disk_type == "iso":
        cmd = "mkisofs -o %s /root/*.*" % path
    elif disk_type == "lvm":
        if vgname is None or lvname is None:
            raise exceptions.TestError("Both VG name and LV name are needed")
        lv_utils.lv_create(vgname, lvname, size)
        path = "/dev/%s/%s" % (vgname, lvname)
    else:
        raise exceptions.TestError("Unknown disk type %s" % disk_type)
    if cmd:
        process.run(cmd, ignore_status=True, shell=True)
    return path


def delete_local_disk(disk_type, path=None,
                      vgname=None, lvname=None):
    if disk_type in ["file", "floppy", "iso"]:
        if path is None:
            raise exceptions.TestError(
                "Path is needed for deleting local disk")
        else:
            cmd = "rm -f %s" % path
            process.run(cmd, ignore_status=True)
    elif disk_type == "lvm":
        if vgname is None or lvname is None:
            raise exceptions.TestError("Both VG name and LV name needed")
        lv_utils.lv_remove(vgname, lvname)
    else:
        raise exceptions.TestError("Unknown disk type %s" % disk_type)


def create_scsi_disk(scsi_option, scsi_size="2048"):
    """
    Get the scsi device created by scsi_debug kernel module

    :param scsi_option. The scsi_debug kernel module options.
    :return: scsi device if it is created successfully.
    """
    try:
        utils_path.find_command("lsscsi")
    except utils_path.CmdNotFoundError:
        raise exceptions.TestSkipError("Missing command 'lsscsi'.")

    try:
        # Load scsi_debug kernel module.
        # Unload it first if it's already loaded.
        if linux_modules.module_is_loaded("scsi_debug"):
            linux_modules.unload_module("scsi_debug")
        linux_modules.load_module("scsi_debug dev_size_mb=%s %s" %
                                  (scsi_size, scsi_option))
        # Get the scsi device name
        result = process.run("lsscsi|grep scsi_debug|awk '{print $6}'",
                             shell=True)
        scsi_disk = result.stdout_text.strip()
        logging.info("scsi disk: %s" % scsi_disk)
        return scsi_disk
    except Exception as e:
        logging.error(str(e))
        return None


def delete_scsi_disk():
    """
    Delete scsi device by removing scsi_debug kernel module.
    """
    scsi_dbg_check = process.run("lsscsi|grep scsi_debug", shell=True)
    if scsi_dbg_check.exit_status == 0:
        scsi_addr_pattern = '[0-9]+:[0-9]+:[0-9]+:[0-9]+'
        for addr in re.findall(scsi_addr_pattern, scsi_dbg_check.stdout_text):
            process.run("echo 1>/sys/class/scsi_device/{}/device/delete".format(addr),
                        shell=True)

    if linux_modules.module_is_loaded("scsi_debug"):
        linux_modules.unload_module("scsi_debug")


def set_controller_multifunction(vm_name, controller_type='scsi'):
    """
    Set multifunction on for controller device and expand to all function.
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    exist_controllers = vmxml.get_devices("controller")
    # Used to contain controllers in format:
    # domain:bus:slot:func -> controller object
    expanded_controllers = {}
    # The index of controller
    index = 0
    for e_controller in exist_controllers:
        if e_controller.type != controller_type:
            continue
        # Set multifunction on
        address_attrs = e_controller.address.attrs
        address_attrs['multifunction'] = "on"
        domain = address_attrs['domain']
        bus = address_attrs['bus']
        slot = address_attrs['slot']
        all_funcs = ["0x0", "0x1", "0x2", "0x3", "0x4", "0x5", "0x6"]
        for func in all_funcs:
            key = "%s:%s:%s:%s" % (domain, bus, slot, func)
            address_attrs['function'] = func
            # Create a new controller instance
            new_controller = controller.Controller(controller_type)
            new_controller.xml = str(xml_utils.XMLTreeFile(e_controller.xml))
            new_controller.index = index
            new_controller.address = new_controller.new_controller_address(
                attrs=address_attrs)
            # Expand controller to all functions with multifunction
            if key not in list(expanded_controllers.keys()):
                expanded_controllers[key] = new_controller
                index += 1

    logging.debug("Expanded controllers: %s", list(expanded_controllers.values()))
    vmxml.del_controller(controller_type)
    vmxml.set_controller(list(expanded_controllers.values()))
    vmxml.sync()


def attach_disks(vm, path, vgname, params):
    """
    Attach multiple disks.According parameter disk_type in params,
    it will create lvm or file type disks.

    :param path: file type disk's path
    :param vgname: lvm type disk's volume group name
    """
    # Additional disk on vm
    disks_count = int(params.get("added_disks_count", 1)) - 1
    multifunction_on = "yes" == params.get("multifunction_on", "no")
    disk_size = params.get("added_disk_size", "0.1")
    disk_type = params.get("added_disk_type", "file")
    disk_target = params.get("added_disk_target", "virtio")
    disk_format = params.get("added_disk_format", "raw")
    # Whether attaching device with --config
    attach_config = "yes" == params.get("attach_disk_config", "yes")

    def generate_disks_index(count, target="virtio"):
        # Created disks' index
        target_list = []
        # Used to flag progression
        index = 0
        # A list to maintain prefix for generating device
        # ['a','b','c'] means prefix abc
        prefix_list = []
        while count > 0:
            # Out of range for current prefix_list
            if (index // 26) > 0:
                # Update prefix_list to expand disks, such as [] -> ['a'],
                # ['z'] -> ['a', 'a'], ['z', 'z'] -> ['a', 'a', 'a']
                prefix_index = len(prefix_list)
                if prefix_index == 0:
                    prefix_list.append('a')
                # Append a new prefix to list, then update pre-'z' in list
                # to 'a' to keep the progression 1
                while prefix_index > 0:
                    prefix_index -= 1
                    prefix_cur = prefix_list[prefix_index]
                    if prefix_cur == 'z':
                        prefix_list[prefix_index] = 'a'
                        # All prefix in prefix_list are 'z',
                        # it's time to expand it.
                        if prefix_index == 0:
                            prefix_list.append('a')
                    else:
                        # For whole prefix_list, progression is 1
                        prefix_list[prefix_index] = chr(ord(prefix_cur) + 1)
                        break
                # Reset for another iteration
                index = 0
            prefix = "".join(prefix_list)
            suffix_index = index % 26
            suffix = chr(ord('a') + suffix_index)
            index += 1
            count -= 1

            # Generate device target according to driver type
            if target == "virtio":
                target_dev = "vd%s" % (prefix + suffix)
            elif target == "scsi":
                target_dev = "sd%s" % (prefix + suffix)
            elif target == "ide":
                target_dev = "hd%s" % (prefix + suffix)
            target_list.append(target_dev)
        return target_list

    target_list = generate_disks_index(disks_count, disk_target)

    # A dict include disks information: source file and size
    added_disks = {}
    for target_dev in target_list:
        # Do not attach if it does already exist
        if device_exists(vm, target_dev):
            continue

        # Prepare controller for special disks like virtio-scsi
        # Open multifunction to add more controller for disks(150 or more)
        if multifunction_on:
            set_controller_multifunction(vm.name, disk_target)

        disk_params = {}
        disk_params['type_name'] = disk_type
        disk_params['target_dev'] = target_dev
        disk_params['target_bus'] = disk_target
        disk_params['device_type'] = params.get("device_type", "disk")
        device_name = "%s_%s" % (target_dev, vm.name)
        disk_path = os.path.join(os.path.dirname(path), device_name)
        disk_path = create_local_disk(disk_type, disk_path,
                                      disk_size, disk_format,
                                      vgname, device_name)
        added_disks[disk_path] = disk_size
        result = attach_additional_device(vm.name, target_dev, disk_path,
                                          disk_params, attach_config)
        if result.exit_status:
            raise exceptions.TestFail("Attach device %s failed."
                                      % target_dev)
    logging.debug("New VM XML:\n%s", vm.get_xml())
    return added_disks


def define_new_vm(vm_name, new_name):
    """
    Just define a new vm from given name
    """
    try:
        vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
        vmxml.vm_name = new_name
        del vmxml.uuid
        vmxml.define()
        return True
    except xcepts.LibvirtXMLError as detail:
        logging.error(detail)
        return False


def remotely_control_libvirtd(server_ip, server_user, server_pwd,
                              action='restart', status_error='no'):
    """
    Remotely restart libvirt service
    """
    session = None
    try:
        session = remote.wait_for_login('ssh', server_ip, '22',
                                        server_user, server_pwd,
                                        r"[\#\$]\s*$")
        logging.info("%s libvirt daemon\n", action)
        service_libvirtd_control(action, session)
        session.close()
    except (remote.LoginError, aexpect.ShellError, process.CmdError) as detail:
        if session:
            session.close()
        if status_error == "no":
            raise exceptions.TestFail("Failed to %s libvirtd service on "
                                      "server: %s\n", action, detail)
        else:
            logging.info("It is an expect %s", detail)


def connect_libvirtd(uri, read_only="", virsh_cmd="list", auth_user=None,
                     auth_pwd=None, vm_name="", status_error="no",
                     extra="", log_level='LIBVIRT_DEBUG=3', su_user="",
                     patterns_virsh_cmd=r".*Id\s*Name\s*State\s*.*",
                     patterns_extra_dict=None):
    """
    Connect to libvirt daemon

    :param uri: the uri to connect the libvirtd
    :param read_only: the read only option for virsh
    :param virsh_cmd: the virsh command for virsh
    :param auth_user: the user used to connect
    :param auth_pwd: the password for the user
    :param vm_name: the guest name to operate
    :param status_error: if expect error status
    :param extra: extra parameters
    :param log_level: logging level
    :param su_user: the user to su
    :param patterns_virsh_cmd: the pattern to match in virsh command output
    :param patterns_extra_dict: a mapping with extra patterns and responses

    :return: True if success, otherwise False
    """
    patterns_yes_no = r".*[Yy]es.*[Nn]o.*"
    patterns_auth_name_comm = r".*username:.*"
    patterns_auth_name_xen = r".*name.*root.*:.*"
    patterns_auth_pwd = r".*[Pp]assword.*"

    command = "%s %s virsh %s -c %s %s %s" % (extra, log_level, read_only,
                                              uri, virsh_cmd, vm_name)
    # allow specific user to run virsh command
    if su_user != "":
        command = "su %s -c '%s'" % (su_user, command)

    logging.info("Execute %s", command)
    # setup shell session
    session = aexpect.ShellSession(command, echo=True)

    try:
        # requires access authentication
        match_list = [patterns_yes_no, patterns_auth_name_comm,
                      patterns_auth_name_xen, patterns_auth_pwd,
                      patterns_virsh_cmd]
        if patterns_extra_dict:
            match_list = match_list + list(patterns_extra_dict.keys())
        patterns_list_len = len(match_list)

        while True:
            match, text = session.read_until_any_line_matches(match_list,
                                                              timeout=30,
                                                              internal_timeout=1)
            if match == -patterns_list_len:
                logging.info("Matched 'yes/no', details: <%s>", text)
                session.sendline("yes")
                continue
            elif match == -patterns_list_len + 1 or match == -patterns_list_len + 2:
                logging.info("Matched 'username', details: <%s>", text)
                session.sendline(auth_user)
                continue
            elif match == -patterns_list_len + 3:
                logging.info("Matched 'password', details: <%s>", text)
                session.sendline(auth_pwd)
                continue
            elif match == -patterns_list_len + 4:
                logging.info("Expected output of virsh command: <%s>", text)
                break
            if (patterns_list_len > 5):
                extra_len = len(patterns_extra_dict)
                index_in_extra_dict = match + extra_len
                key = list(patterns_extra_dict.keys())[index_in_extra_dict]
                value = patterns_extra_dict.get(key, "")
                logging.info("Matched '%s', details:<%s>", key, text)
                session.sendline(value)
                continue
            else:
                logging.error("The real prompt text: <%s>", text)
                break

        log = session.get_output()
        session.close()
        return (True, log)
    except (aexpect.ShellError, aexpect.ExpectError) as details:
        log = session.get_output()
        session.close()
        logging.error("Failed to connect libvirtd: %s\n%s", details, log)
        return (False, log)


def get_all_vol_paths():
    """
    Get all volumes' path in host
    """
    vol_path = []
    sp = libvirt_storage.StoragePool()
    for pool_name in list(sp.list_pools().keys()):
        if sp.list_pools()[pool_name]['State'] != "active":
            logging.warning(
                "Inactive pool '%s' cannot be processed" % pool_name)
            continue
        pv = libvirt_storage.PoolVolume(pool_name)
        for path in list(pv.list_volumes().values()):
            vol_path.append(path)
    return set(vol_path)


def do_migration(vm_name, uri, extra, auth_pwd, auth_user="root",
                 options="--verbose", virsh_patterns=r".*100\s%.*",
                 su_user="", timeout=30, extra_opt=""):
    """
    Migrate VM to target host.
    """
    patterns_yes_no = r".*[Yy]es.*[Nn]o.*"
    patterns_auth_name = r".*name:.*"
    patterns_auth_pwd = r".*[Pp]assword.*"

    command = "%s virsh %s migrate %s %s %s" % (extra, extra_opt,
                                                vm_name, options, uri)
    # allow specific user to run virsh command
    if su_user != "":
        command = "su %s -c '%s'" % (su_user, command)

    logging.info("Execute %s", command)
    # setup shell session
    session = aexpect.ShellSession(command, echo=True)

    try:
        # requires access authentication
        match_list = [patterns_yes_no, patterns_auth_name,
                      patterns_auth_pwd, virsh_patterns]
        while True:
            match, text = session.read_until_any_line_matches(match_list,
                                                              timeout=timeout,
                                                              internal_timeout=1)
            if match == -4:
                logging.info("Matched 'yes/no', details: <%s>", text)
                session.sendline("yes")
            elif match == -3:
                logging.info("Matched 'username', details: <%s>", text)
                session.sendline(auth_user)
            elif match == -2:
                logging.info("Matched 'password', details: <%s>", text)
                session.sendline(auth_pwd)
            elif match == -1:
                logging.info("Expected output of virsh migrate: <%s>", text)
                break
            else:
                logging.error("The real prompt text: <%s>", text)
                break
        log = session.get_output()
        session.close()
        return (True, log)

    except (aexpect.ShellError, aexpect.ExpectError) as details:
        log = session.get_output()
        session.close()
        logging.error("Failed to migrate %s: %s\n%s", vm_name, details, log)
        return (False, log)


def update_vm_disk_driver_cache(vm_name, driver_cache="none", disk_index=0):
    """
    Update disk driver cache of the VM

    :param vm_name: vm name
    :param driver_cache: new vm disk driver cache mode, default to none if not provided
    :param disk_index: vm disk index to be updated, the index of first disk is 0.
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)

    try:
        # Get the disk to be updated
        devices = vmxml.devices
        device_index = devices.index(devices.by_device_tag('disk')[disk_index])
        disk = devices[device_index]

        # Update disk driver cache mode
        driver_dict = disk.driver
        driver_dict['cache'] = driver_cache
        disk.driver = driver_dict
        logging.debug("The new vm disk driver cache is %s", disk.driver['cache'])

        vmxml.devices = devices

        # SYNC VM XML change
        logging.debug("The new VM XML:\n%s", vmxml)
        vmxml.sync()
        return True
    except Exception as e:
        logging.error("Can't update disk driver cache!! %s", e)
        return False


def update_vm_disk_source(vm_name, disk_source_path,
                          disk_image_name="",
                          source_type="file"):
    """
    Update disk source path of the VM

    :param source_type: it may be 'dev' or 'file' type, which is default
    """
    if not os.path.isdir(disk_source_path):
        logging.error("Require disk source path!!")
        return False

    # Prepare to update VM first disk source file
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    devices = vmxml.devices
    disk_index = devices.index(devices.by_device_tag('disk')[0])
    disks = devices[disk_index]
    # Generate a disk image name if it doesn't exist
    if not disk_image_name:
        disk_source = disks.source.get_attrs().get(source_type)
        logging.debug("The disk source file of the VM: %s", disk_source)
        disk_image_name = os.path.basename(disk_source)

    new_disk_source = os.path.join(disk_source_path, disk_image_name)
    logging.debug("The new disk source file of the VM: %s", new_disk_source)

    # Update VM disk source file
    try:
        disks.source = disks.new_disk_source(**{'attrs': {'%s' % source_type:
                                                          "%s" % new_disk_source}})
        # SYNC VM XML change
        vmxml.devices = devices
        logging.debug("The new VM XML:\n%s", vmxml.xmltreefile)
        vmxml.sync()
        return True
    except Exception as e:
        logging.error("Can't update disk source!! %s", e)
        return False


def exec_virsh_edit(source, edit_cmd, connect_uri="qemu:///system"):
    """
    Execute edit command.

    :param source : virsh edit's option.
    :param edit_cmd: Edit command list to execute.
    :return: True if edit is successful, False if edit is failure.
    """
    logging.info("Trying to edit xml with cmd %s", edit_cmd)
    session = aexpect.ShellSession("sudo -s")
    try:
        session.sendline("virsh -c %s edit %s" % (connect_uri, source))
        for cmd in edit_cmd:
            session.sendline(cmd)
        session.send('\x1b')
        session.send('ZZ')
        remote.handle_prompts(session, None, None, r"[\#\$]\s*$", debug=True)
        session.close()
        return True
    except Exception as e:
        session.close()
        logging.error("Error occurred: %s", e)
        return False


def new_disk_vol_name(pool_name):
    """
    According to BZ#1138523, the new volume name must be the next
    created partition(sdb1, etc.), so we need to inspect the original
    partitions of the disk then count the new partition number.

    :param pool_name: Disk pool name
    :return: New volume name or none
    """
    poolxml = pool_xml.PoolXML.new_from_dumpxml(pool_name)
    if poolxml.get_type(pool_name) != "disk":
        logging.error("This is not a disk pool")
        return None
    disk = poolxml.get_source().device_path[5:]
    part_num = len(list(filter(lambda s: s.startswith(disk),
                               utils_misc.utils_disk.get_parts_list())))
    return disk + str(part_num)


def update_polkit_rule(params, pattern, new_value):
    """
    This function help to update the rule during testing.

    :param params: Test run params
    :param pattern: Regex pattern for updating
    :param new_value: New value for updating
    """
    polkit = test_setup.LibvirtPolkitConfig(params)
    polkit_rules_path = polkit.polkit_rules_path
    try:
        polkit_f = open(polkit_rules_path, 'r+')
        rule = polkit_f.read()
        new_rule = re.sub(pattern, new_value, rule)
        polkit_f.seek(0)
        polkit_f.truncate()
        polkit_f.write(new_rule)
        polkit_f.close()
        logging.debug("New polkit config rule is:\n%s", new_rule)
        polkit.polkitd.restart()
    except IOError as e:
        logging.error(e)


def get_vol_list(pool_name, vol_check=True, timeout=5):
    """
    This is a wrapper to get all volumes of a pool, especially for
    iscsi type pool as the volume may not appear immediately after
    iscsi target login.

    :param pool_name: Libvirt pool name
    :param vol_check: Check if volume and volume path exist
    :param timeout: Timeout in seconds.
    :return: A dict include volumes' name(key) and path(value).
    """
    poolvol = libvirt_storage.PoolVolume(pool_name=pool_name)
    vols = utils_misc.wait_for(poolvol.list_volumes, timeout,
                               text='Waiting for volume show up')
    if not vol_check:
        return vols

    # Check volume name
    if not vols:
        raise exceptions.TestError("No volume in pool %s" % pool_name)

    # Check volume
    for vol_path in six.itervalues(vols):
        if not utils_misc.wait_for(lambda: os.path.exists(vol_path), timeout,
                                   text='Waiting for %s show up' % vol_path):
            raise exceptions.TestError("Volume path %s not exist" % vol_path)

    return vols


def get_iothreadsinfo(vm_name, options=None):
    """
    Parse domain iothreadinfo.

    :param vm_name: Domain name
    :return: The dict of domain iothreads

    ::
        # virsh iothreadinfo vm2
        IOThread ID CPU Affinity
        ---------------------------------------------------
        2 3
        1 0-4
        4 0-7
        3 0-7

    The function return a dict like:

    ::
        {'2': '3', '1': '0-4', '4': '0-7', '3': '0-7'}
    """
    info_dict = {}
    ret = virsh.iothreadinfo(vm_name, options,
                             debug=True, ignore_status=True)
    if ret.exit_status:
        logging.warning(ret.stderr_text.strip())
        return info_dict
    info_list = re.findall(r"(\d+) +(\S+)", ret.stdout_text, re.M)
    for info in info_list:
        info_dict[info[0]] = info[1]

    return info_dict


def virsh_cmd_has_option(cmd, option, raise_skip=True):
    """
    Check whether virsh command support given option.

    :param cmd: Virsh command name
    :param option: Virsh command option
    :raise_skip: Whether raise exception when option not find
    :return: True/False or raise TestSkipError
    """
    found = False
    if virsh.has_command_help_match(cmd, option):
        found = True
    msg = "command '%s' has option '%s': %s" % (cmd, option, str(found))
    if not found and raise_skip:
        raise exceptions.TestSkipError(msg)
    else:
        logging.debug(msg)
        return found


def create_secret(params, remote_args=None):
    """
    Create a secret with 'virsh secret-define'

    :param params: Test run params
    :param remote_args: Parameters for remote host
    :return: UUID of the secret
    """
    sec_usage_type = params.get("sec_usage", "volume")
    sec_desc = params.get("sec_desc", "secret_description")
    sec_ephemeral = params.get("sec_ephemeral", "no") == "yes"
    sec_private = params.get("sec_private", "no") == "yes"
    sec_uuid = params.get("sec_uuid", "")
    sec_volume = params.get("sec_volume", "/path/to/volume")
    sec_name = params.get("sec_name", "secret_name")
    sec_target = params.get("sec_target", "secret_target")

    supporting_usage_types = ['volume', 'ceph', 'iscsi', 'tls', 'vtpm']
    if sec_usage_type not in supporting_usage_types:
        raise exceptions.TestError("Supporting secret usage types are: %s" %
                                   supporting_usage_types)

    # prepare secret xml
    sec_xml = secret_xml.SecretXML("no", "yes")
    # set common attributes
    sec_xml.description = sec_desc
    sec_xml.usage = sec_usage_type
    if sec_ephemeral:
        sec_xml.secret_ephmeral = "yes"
    if sec_private:
        sec_xml.secret_private = "yes"
    if sec_uuid:
        sec_xml.uuid = sec_uuid
    sec_xml.usage = sec_usage_type
    # set specific attributes for different usage type
    if sec_usage_type in ['volume']:
        sec_xml.volume = sec_volume
    if sec_usage_type in ['ceph', 'tls', 'vtpm']:
        sec_xml.usage_name = sec_name
    if sec_usage_type in ['iscsi']:
        sec_xml.target = sec_target
    sec_xml.xmltreefile.write()
    logging.debug("The secret xml is: %s" % sec_xml)

    # define the secret and get its uuid
    if remote_args:
        server_ip = remote_args.get("remote_ip", "")
        server_user = remote_args.get("remote_user", "")
        server_pwd = remote_args.get("remote_pwd", "")
        if not all([server_ip, server_user, server_pwd]):
            raise exceptions.TestError("remote_[ip|user|pwd] are necessary!")
        remote_virsh_session = virsh.VirshPersistent(**remote_args)
        remote.scp_to_remote(server_ip, '22', server_user, server_pwd,
                             sec_xml.xml, sec_xml.xml, limit="",
                             log_filename=None, timeout=600, interface=None)
        ret = remote_virsh_session.secret_define(sec_xml.xml)
        remote_virsh_session.close_session()
    else:
        ret = virsh.secret_define(sec_xml.xml)
    check_exit_status(ret)
    try:
        sec_uuid = re.findall(r".+\S+(\ +\S+)\ +.+\S+",
                              ret.stdout_text)[0].lstrip()
    except IndexError:
        raise exceptions.TestError("Fail to get newly created secret uuid")

    return sec_uuid


def modify_vm_iface(vm_name, oper, iface_dict, index=0):
    """
    Modify interface xml and do operations

    :param vm_name: name of vm
    :param oper: Operation need to do, current we have 2 choice
                 1. "update_iface": modify iface according to dict and updated in vm
                 2. "get_xml": modify iface according to dict and return xml
    :param iface_dict: The dict restore need updated items like iface_driver,
                       driver_host, driver_guest and so on
    :param index: interface index in xml
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    xml_devices = vmxml.devices
    iface_type = iface_dict.get('type')

    try:
        iface_index = xml_devices.index(
            xml_devices.by_device_tag("interface")[index])
        iface = xml_devices[iface_index]
    except IndexError:
        iface = interface.Interface(iface_type)

    iface_driver = iface_dict.get('driver')
    driver_host = iface_dict.get('driver_host')
    driver_guest = iface_dict.get('driver_guest')
    iface_model = iface_dict.get('model')
    iface_rom = iface_dict.get('rom')
    iface_inbound = iface_dict.get('inbound')
    iface_outbound = iface_dict.get('outbound')
    iface_link = iface_dict.get('link')
    iface_source = iface_dict.get('source')
    iface_target = iface_dict.get('target')
    iface_addr = iface_dict.get('addr')
    iface_filter = iface_dict.get('filter')
    boot_order = iface_dict.get('boot')
    iface_backend = iface_dict.get('backend')
    iface_mac = iface_dict.get('mac')
    iface_mtu = iface_dict.get('mtu')
    iface_alias = iface_dict.get('alias')
    iface_teaming = iface_dict.get('teaming')
    iface_virtualport_type = iface_dict.get('virtualport_type')
    iface_filter_parameters = iface_dict.get('filter_parameters')
    iface_port = iface_dict.get('port')
    del_addr = iface_dict.get('del_addr')
    del_rom = iface_dict.get('del_rom')
    del_filter = iface_dict.get('del_filter')
    del_port = iface_dict.get('del_port')
    del_mac = "yes" == iface_dict.get('del_mac', "no")
    if iface_type:
        iface.type_name = iface_type
    if iface_driver:
        iface.driver = iface.new_driver(
            driver_attr=eval(iface_driver),
            driver_host=eval(driver_host) if driver_host else {},
            driver_guest=eval(driver_guest) if driver_guest else {})
    if iface_model:
        iface.model = iface_model
    if del_rom:
        iface.del_rom()
    if iface_rom:
        iface.rom = eval(iface_rom)
    if iface_inbound:
        iface.bandwidth = iface.new_bandwidth(
            inbound=eval(iface_inbound),
            outbound=eval(iface_outbound) if iface_outbound else {})
    if iface_link:
        iface.link_state = iface_link
    if iface_source:
        iface.source = eval(iface_source)
    if iface_target:
        iface.target = eval(iface_target)
    if iface_addr:
        iface.address = iface.new_iface_address(
            **{"attrs": eval(iface_addr)})
    if del_addr:
        iface.del_address()
    if del_filter:
        iface.del_filterref()
    if del_port:
        iface.del_port()
    if del_mac:
        iface.del_mac_address()
    if iface_filter:
        if iface_filter_parameters:
            iface.filterref = iface.new_filterref(name=iface_filter, parameters=iface_filter_parameters)
        else:
            iface.filterref = iface.new_filterref(name=iface_filter)
    if boot_order:
        iface.boot = boot_order
    if iface_backend:
        iface.backend = eval(iface_backend)
    if iface_mac:
        iface.mac_address = iface_mac
    if iface_mtu:
        iface.mtu = eval(iface_mtu)
    if iface_alias:
        iface.alias = eval(iface_alias)
    if iface_teaming:
        iface.teaming = eval(iface_teaming)
    if iface_virtualport_type:
        iface.virtualport_type = iface_virtualport_type
    if iface_port:
        iface.port = eval(iface_port)
    if oper == "update_iface":
        vmxml.devices = xml_devices
        vmxml.xmltreefile.write()
        vmxml.sync()
    elif oper == "get_xml":
        logging.info("iface xml is %s", iface)
        return iface.xml


def change_boot_order(vm_name, device_tag, boot_order, index=0):
    """
    Change the order for disk/interface device

    :param vm_name: name of vm
    :param device_tag: the device tag in xml
    :param boot_order: the boot order need to be changed to
    :param index: which device to change
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    vmxml.remove_all_boots()
    xml_devices = vmxml.devices
    device_index = xml_devices.index(xml_devices.by_device_tag(device_tag)[index])
    device = xml_devices[device_index]
    device.boot = boot_order
    vmxml.devices = xml_devices
    vmxml.xmltreefile.write()
    vmxml.sync()


def check_machine_type_arch(machine_type):
    """
    Determine if one case for special machine
    type can be run on host

    :param machine_type: the machine type the case is designed for
    :raise exceptions.TestSkipError: Skip if the host arch does
                                     not match the machine type
    """
    if not machine_type:
        return
    arch_machine_map = {'x86_64': ['pc', 'q35'],
                        'ppc64le': ['pseries'],
                        's390x': ['s390-ccw-virtio']}
    arch = platform.machine()
    if machine_type not in arch_machine_map[arch]:
        raise exceptions.TestSkipError("This machine type '%s' is not "
                                       "supported on the host with "
                                       "arch '%s'" % (machine_type,
                                                      arch))


def customize_libvirt_config(params,
                             config_type="virtqemud",
                             remote_host=False,
                             extra_params=None,
                             is_recover=False,
                             config_object=None):
    """
    Customize configuration files for libvirt
    on local and remote host if needed

    :param params: A dict used to configure
    :param config_type: "libvirtd" for /etc/libvirt/libvirtd.conf
                        "qemu" for /etc/libvirt/qemu.conf
                        "sysconfig" for /etc/sysconfig/libvirtd
                        "guestconfig" for /etc/sysconfig/libvirt-guests
    :param remote_host True for setting up for remote host, too.
                       False for not setting up
    :param extra_params: Parameters for remote host
    :param is_recover: True for recovering the configuration and
                               config_object should be provided
                       False for configuring specified libvirt configuration
    :param config_object: an existing utils_config.LibvirtConfigCommon object
    :return: utils_config.LibvirtConfigCommon object
    """
    # Hardcode config_type to virtqemud under modularity daemon mode when config_type="libvirtd"
    # On the contrary, hardcode it to "libvirtd" when config_type="virt*d".
    # Otherwise accept config_type as it is.
    if utils_split_daemons.is_modular_daemon():
        if config_type in ["libvirtd"]:
            config_type = "virtqemud"
    else:
        if config_type in ["virtqemud", "virtproxyd", "virtnetworkd",
                           "virtstoraged", "virtinterfaced", "virtnodedevd",
                           "virtnwfilterd", "virtsecretd"]:
            config_type = "libvirtd"
    config_list_support = ["libvirtd", "qemu", "sysconfig", "guestconfig",
                           "virtqemud", "virtproxyd", "virtnetworkd",
                           "virtstoraged", "virtinterfaced", "virtnodedevd",
                           "virtnwfilterd", "virtsecretd", "libvirt"]
    if config_type not in config_list_support:
        logging.debug("'%s' is not in the support list '%s'",
                      config_type, config_list_support)
        return None
    else:
        logging.debug("The '%s' config file will be updated.", config_type)

    if not is_recover:
        target_conf = None
        # Handle local
        if not params or not isinstance(params, dict):
            return None
        target_conf = utils_config.get_conf_obj(config_type)
        #if params and isinstance(params, dict):
        for key, value in params.items():
            target_conf[key] = value
        logging.debug("The '%s' config file is updated with:\n %s",
                      target_conf.conf_path, params)

        libvirtd = utils_libvirtd.Libvirtd()
        libvirtd.restart()
        obj_conf = target_conf
    else:
        if not isinstance(config_object, utils_config.LibvirtConfigCommon):
            return None
        # Handle local libvirtd
        config_object.restore()
        libvirtd = utils_libvirtd.Libvirtd()
        libvirtd.restart()
        obj_conf = config_object

    if remote_host:
        server_ip = extra_params.get("server_ip", "")
        server_user = extra_params.get("server_user", "")
        server_pwd = extra_params.get("server_pwd", "")
        local_path = obj_conf.conf_path
        remote.scp_to_remote(server_ip, '22', server_user, server_pwd,
                             local_path, local_path, limit="",
                             log_filename=None, timeout=600, interface=None)
        remotely_control_libvirtd(server_ip, server_user,
                                  server_pwd, action='restart',
                                  status_error='no')

    return obj_conf


def check_logfile(search_str, log_file, str_in_log=True,
                  cmd_parms=None, runner_on_target=None):
    """
    Check if the given string exists in the log file

    :param search_str: the string to be searched
    :param log_file: the given file
    :param str_in_log: Ture if the file should include the given string,
                        otherwise, False
    :param cmd_parms: The parms for remote executing
    :param runner_on_target:  Remote runner
    :raise: test.fail when the result is not expected
    """
    cmd = "grep -E '%s' %s" % (search_str, log_file)
    if not (cmd_parms and runner_on_target):
        cmdRes = process.run(cmd, shell=True, ignore_status=True)
    else:
        cmdRes = remote_old.run_remote_cmd(cmd, cmd_parms, runner_on_target)
    if str_in_log == bool(int(cmdRes.exit_status)):
        raise exceptions.TestFail("The string '{}' {} included in {}"
                                  .format(search_str, "is not" if str_in_log else "is",
                                          log_file))


def check_qemu_cmd_line(content, err_ignore=False,
                        remote_params=None, runner_on_target=None):
    """
    Check the specified content in the qemu command line
    :param content: the desired string to search
    :param err_ignore: True to return False when fail
                       False to raise exception when fail
    :param remote_params: The params for remote executing
    :param runner_on_target:  Remote runner
    :return: True if exist, False otherwise
    """
    cmd = 'pgrep -a qemu'
    if not(remote_params or runner_on_target):
        qemu_line = process.run(cmd, shell=True).stdout_text
    else:
        cmd_result = remote_old.run_remote_cmd(cmd, remote_params, runner_on_target)
        qemu_line = cmd_result.stdout
    if not re.search(r'%s' % content, qemu_line):
        if err_ignore:
            return False
        else:
            raise exceptions.TestFail("Expected '%s' was not found in "
                                      "qemu command line" % content)
    return True


def check_cmd_output(cmd, content, err_ignore=False, session=None):
    """
    Check the specified content in the output of the cmd
    :param cmd: the cmd wants to check
    :param content: the desired string or list to search
    :param err_ignore: True to return False when fail
                       False to raise exception when fail
    :param session: ShellSession object of VM or remote host
    :return: True if exist, False otherwise
    :raise: exceptions.TestFail when content is not found in the output of cmd
    """
    if cmd is None:
        raise exceptions.TestFail("cmd can not be None")
    s, cmd_output = utils_misc.cmd_status_output(cmd, shell=True,
                                                 ignore_status=err_ignore, session=session)
    pattern_list = [content] if not isinstance(content, list) else content
    for item in pattern_list:
        if not re.search(r'%s' % item, cmd_output):
            if err_ignore:
                return False
            else:
                raise exceptions.TestFail("Expected '%s' was not found in "
                                          "output of '%s'" % (item, cmd))


def get_disk_alias(vm, source_file=None):
    """
    Get alias name of disk with given source file

    :param vm: VM object
    :param source_file: domain disk source file
    :return: None if not find, else return alias name
    """
    if vm.is_alive():
        ori_vmxml = vm_xml.VMXML.new_from_dumpxml(vm.name)
        disks = ori_vmxml.devices.by_device_tag('disk')
        for disk in disks:
            find_source = disk.xmltreefile.find('source') is not None
            try:
                if ((find_source and disk.source.attrs['file'] == source_file) or
                        (not find_source and not source_file)):
                    logging.info("Get alias name %s", disk.alias['name'])
                    return disk.alias['name']
            except KeyError as e:
                logging.info("Ignore error of source attr getting for file: %s" % e)
                pass
    return None


def check_domuuid_compliant_with_rfc4122(dom_uuid_value):
    """
    Check the domain uuid format comply with RFC4122.
    xxxxxxxx-xxxx-Axxx-Bxxx-xxxxxxxxxxxx
    A should be RFC version number, since the compliant RFC version is 4122,
    so it should be number 4.
    B should be one of "8, 9, a or b".

    :param dom_uuid_value: value of domain uuid
    :return: True or False indicate whether it is compliant with RFC 4122.
    """
    dom_uuid_segments = dom_uuid_value.split('-')
    return dom_uuid_segments[2].startswith('4') and dom_uuid_segments[3][0] in '89ab'


def check_dumpxml(vm, content, err_ignore=False):
    """
    Check the specified content in the VM dumpxml

    :param vm: VM object
    :param content: the desired string to search
    :param err_ignore: True to return False when fail
                       False to raise exception when fail
    :return: True if exist, False otherwise
    """
    v_xml = vm_xml.VMXML.new_from_dumpxml(vm.name)
    with open(v_xml.xml) as xml_f:
        if content not in xml_f.read():
            if err_ignore:
                return False
            else:
                raise exceptions.TestFail("Expected '%s' was not found in "
                                          "%s's xml" % (content, vm.name))
    return True
