#
# library for the filesystem related helper functions
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; specifically version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat (c) 2023 and Avocado contributors
# Author: Houqi Zuo <hzuo@redhat.com>
import os
import re

from avocado.utils import process

from virttest import utils_numeric
from virttest.vt_utils import block

PARTITION_TYPE_PRIMARY = "primary"
SIZE_AVAILABLE = "available size"


def is_mounted(src, dst=None, fstype=None, options=None):
    """
    Check whether the src or dst is mounted or not.

    :param src: source device or directory
    :type src: string
    :param dst: mountpoint, it will be replaced to ''( nothing ) if it's None
    :type dst: string
    :param fstype: filesystem type, it will be replaced to ''( nothing )
                   if it's None
    :type fstype: string
    :param options: mount options, which should be separated by ","
                    between each options
    :type options: string

    :return: True if mounted, else return False
    :rtype: boolean
    """
    mount_str = "%s %s %s" % (src, dst, fstype)
    mount_str = mount_str.replace("None", "").strip()
    mount_list_cmd = "cat /proc/mounts"

    mount_result = process.run(mount_list_cmd, shell=True, verbose=False).stdout_text

    for result in mount_result.splitlines():
        if mount_str in result:
            if options:
                options = options.split(",")
                options_result = result.split()[3].split(",")
                for op in options:
                    if op not in options_result:
                        return False
            return True
    return False


def mount(src, dst, fstype=None, options=None):
    """
    Mount src under dst. Even if it has been mounted already,
    remout will be done with options.

    :param src: source device or directory
    :type src: string
    :param dst: mountpoint
    :type dst: string
    :param fstype: filesystem type
    :type fstype: string
    :param options: mount options, which should be separated by ","
                    between each options
    :type options: string

    :return: if mounted successfully, return True. Otherwise, return False
    :rtype: boolean
    """
    options = "" if options is None else options
    if is_mounted(src, dst, fstype, options):
        if "remount" not in options:
            options = "remount,%s" % options
    cmd = ["mount"]
    if fstype:
        cmd.extend(["-t", fstype])
    if options:
        cmd.extend(["-o", options])
    cmd.extend([src, dst])
    cmd = " ".join(cmd)
    return process.system(cmd, verbose=False) == 0


def umount(src, dst, fstype=None):
    """
    Umount src from dst, if src really mounted under dst.

    :param src: source device or directory
    :type src: string
    :param dst: mountpoint
    :type dst: string
    :param fstype: filesystem type
    :type fstype: string

    :return: if umount successfully, return True. Otherwise, return False
    :rtype: boolean
    """
    mounted = is_mounted(src, dst, fstype)
    if mounted:
        from virttest import utils_package

        package = "psmisc"
        # check package is available, if not try installing it
        if not utils_package.package_install(package):
            raise RuntimeError("%s is not available/installed for fuser", package)
        fuser_cmd = "fuser -km %s" % dst
        umount_cmd = "umount %s" % dst
        process.system(fuser_cmd, ignore_status=True, shell=True, verbose=False)
        return process.system(umount_cmd, ignore_status=True, verbose=False) == 0
    return True


def create_filesyetem(partition, fstype, timeout=360):
    """
    create file system.

    :param partition: partition name that to be formatted. e.g. /dev/sdb1
    :param fstype: filesystem type for the disk.
    :param timeout: Timeout for cmd execution in seconds.
    """
    if fstype == "xfs":
        mkfs_cmd = "mkfs.%s -f" % fstype
    else:
        mkfs_cmd = "mkfs.%s -F" % fstype
    format_cmd = "yes|%s '%s'" % (mkfs_cmd, partition)
    process.run(format_cmd, timeout=timeout, verbose=False)


def resize_filesystem(partition, size):
    """
    Resize file system.
    For ext2, ext3, ext4 filesystem, support enlarge and shrink.
    For xfs filesystem, only support enlarge, not support shrink.

    :param partition: disk partition, like /dev/sdb1.
    :param size: resize file system to size.
                 size unit can be 'B', 'K', 'M', 'G'.
                 support transfer size with SIZE_AVAILABLE,
                 enlarge to maximum available size.
    """

    def get_start_size():
        start_size = block.get_partition_attrs(partition)["start"]
        return int(utils_numeric.normalize_data_size(start_size, "B").split(".")[0])

    def resize_xfs_fs(size):
        if size == SIZE_AVAILABLE:
            resize_fs_cmd = "xfs_growfs -d %s" % mountpoint
        else:
            output = process.run(
                "xfs_growfs -n %s" % mountpoint, verbose=False
            ).stdout_text
            bsize = int(re.findall(r"data\s+=\s+bsize=(\d+)", output, re.M)[0])
            blocks = (
                int(utils_numeric.normalize_data_size(size, "B").split(".")[0])
                - get_start_size()
            ) // bsize
            resize_fs_cmd = "xfs_growfs -D %s %s" % (blocks, mountpoint)
        process.system(resize_fs_cmd, verbose=False)

    def resize_ext_fs(size):
        flag = False
        if is_mounted(partition, dst=mountpoint, fstype=fstype):
            umount(partition, mountpoint, fstype=fstype)
            flag = True

        process.system("e2fsck -f %s" % partition, verbose=False)

        if size == SIZE_AVAILABLE:
            resize_fs_cmd = "resize2fs %s" % partition
        else:
            output = process.run(
                "tune2fs -l %s | grep -i block" % partition, verbose=False
            ).stdout_text
            bsize = int(re.findall(r"Block size:\s+(\d+)", output, re.M)[0])
            size = (
                (
                    int(utils_numeric.normalize_data_size(size, "B").split(".")[0])
                    - get_start_size()
                )
                // bsize
            ) * bsize
            size = utils_numeric.normalize_data_size(str(size).split(".")[0], "K")
            resize_fs_cmd = "resize2fs %s %sK" % (partition, int(size.split(".")[0]))
        process.run(resize_fs_cmd, verbose=False)
        if flag:
            mount(partition, mountpoint, fstype=fstype)

    mountpoint, fstype = get_mpoint_fstype(partition)
    if fstype == "xfs":
        resize_xfs_fs(size)
    elif fstype.startswith("ext"):
        resize_ext_fs(size)
    else:
        raise NotImplementedError("%s type is NOT supported yet!" % fstype)


def get_mpoint_fstype(partition):
    """
    Get a partition's file system type and mountpoint.

    :param partition: disk partition, like /dev/sdb1.
    :return: Tuple (mountpoint, fstype)
    """
    mount_list = process.run("cat /proc/mounts", verbose=False).stdout_text
    mount_info = re.search(r"%s\s(.+?)\s(.+?)\s" % partition, mount_list)
    return mount_info.groups()


def format_disk(
    did,
    all_disks_did,
    partition=False,
    mountpoint=None,
    size=None,
    fstype="ext3",
):
    """
    Create a partition on disk in Linux host and format and mount it.

    :param did: Disk kname, serial or wwn.
    :type did: String
    :param all_disks_did: All disks did lists each include disk kname,
                          serial and wwn.
    :type all_disks_did: List
    :param partition: If true, can format all disks; otherwise,
                      only format the ones with no partition originally.
    :type partition: Boolean
    :param mountpoint: Mount point for the disk.
    :type mountpoint: String
    :param size: Partition size( such as 6G, 500M ).
    :type size: String
    :param fstype: Filesystem type for the disk.
    :type fstype: String

    :return: If disk is usable, return True. Otherwise, return False.
    :rtype: Boolean
    """
    disks = block.get_disks_path(partition)
    for line in disks:
        kname = line.split("/")[-1]
        did_list = all_disks_did[kname]
        if did not in did_list:
            # Continue to search target disk
            continue
        if not size:
            size_output = process.run(
                "lsblk -o KNAME,SIZE|grep %s" % kname,
                verbose=False,
                shell=True,
            ).stdout_text
            size = size_output.splitlines()[0].split()[1]
        all_disks_before = block.get_disks_path(True)
        devname = line
        block.create_partition(
            devname.split("/")[-1],
            size,
            "0M",
        )
        all_disks_after = block.get_disks_path(True)
        partname = (all_disks_after - all_disks_before).pop()
        create_filesyetem(partname, fstype)
        if not mountpoint:
            process.run("mkdir /mnt/%s" % kname)
            mountpoint = os.path.join("/mnt", kname)
        mount(src=partname, dst=mountpoint, fstype=fstype)
        if is_mounted(src=partname, dst=mountpoint, fstype=fstype):
            return True
        return False
