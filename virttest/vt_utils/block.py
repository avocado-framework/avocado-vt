#
# library for the block related helper functions
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
import platform
import re

from avocado.utils import process, wait

from virttest import utils_numeric
from virttest.vt_utils import filesystem

PARTITION_TYPE_PRIMARY = "primary"


def get_disks_info(has_partition=False):
    """
    List all disks or disks with no partition.

    :param has_partition: If true, list disks info;
                          otherwise, list disks info which do NOT have partition.
    :type has_partition: Boolean
    :return: The disks info.( e.g. {kname: [kname, size, type, serial, wwn]} )
    :rtype: dict
    """
    disks_dict = {}
    parent_disks = set()
    driver = "pci"
    if platform.machine() == "s390x":
        driver = "css0"
    block_info = process.run(
        'ls /sys/dev/block -l | grep "/%s"' % driver,
        verbose=False,
        shell=True,
    ).stdout_text
    for matched in re.finditer(r"/block/(\S+)\s^", block_info, re.M):
        knames = matched.group(1).split("/")
        if len(knames) == 2:
            parent_disks.add(knames[0])
        if has_partition is False and knames[0] in parent_disks:
            if knames[0] in disks_dict:
                del disks_dict[knames[0]]
            continue

        disks_dict[knames[-1]] = [knames[-1]]
        o = process.run(
            'lsblk -o KNAME,SIZE | grep "%s "' % knames[-1],
            verbose=False,
            shell=True,
        ).stdout_text
        disks_dict[knames[-1]].append(o.split()[-1])
        o = process.run(
            "udevadm info -q all -n %s" % knames[-1],
            verbose=False,
            shell=True,
        ).stdout_text
        for parttern in (
            r"DEVTYPE=(\w+)\s^",
            r"ID_SERIAL=(\S+)\s^",
            r"ID_WWN=(\S+)\s^",
        ):
            searched = re.search(parttern, o, re.M | re.I)
            disks_dict[knames[-1]].append(searched.group(1) if searched else None)
    return disks_dict


def get_disks_path(partition_path=False):
    """
    List disk path in Linux host.

    :param partition_path: If true, list disk name including partition; otherwise,
                           list disk name excluding partition.
    :type partition_path: Boolean

    :return: The disks path in set(). ( e.g. {'/dev/sda2', '/dev/sda1', '/dev/sda'} or {'/dev/sda'} )
    :rtype: Set
    """
    cmd = "ls /dev/[vhs]d*"
    if not partition_path:
        cmd = "%s | grep -v [0-9]$" % cmd
    status, output = process.getstatusoutput(cmd, shell=True)
    if status != 0:
        raise RuntimeError("Get disks failed with output %s" % output)
    return set(output.split())


def create_partition(did, size, start, part_type=PARTITION_TYPE_PRIMARY, timeout=360):
    """
    Create single partition on disk.

    :param did: disk kname (e.g. sdb)
    :type did: string
    :param size: partition size. (e.g. 200M)
    :type size: string
    :param start: partition beginning at start (e.g. 0M)
    :type start: string
    :param part_type: partition type, primary extended logical
    :type part_type: string
    :param timeout: timeout for cmd execution in seconds
    :type timeout: int
    :return: the kname of partition created
    :rtype: string

    :raise RuntimeError: if creating partition is failed
    """

    def _list_disk_partitions():
        driver = "pci"
        if platform.machine() == "s390x":
            driver = "css0"
        o = process.run(
            'ls /sys/dev/block -l | grep "/%s" | grep "%s" '
            "--color=never" % (driver, did),
            verbose=False,
        ).stdout_text
        return set(o.splitlines())

    size = utils_numeric.normalize_data_size(size, order_magnitude="M") + "M"
    start = utils_numeric.normalize_data_size(start, order_magnitude="M") + "M"
    end = str(float(start[:-1]) + float(size[:-1])) + size[-1]
    orig_disks = _list_disk_partitions()
    partprobe_cmd = "partprobe /dev/%s" % did
    mkpart_cmd = 'parted -s "%s" mkpart %s %s %s'
    mkpart_cmd %= ("/dev/%s" % did, part_type, start, end)
    process.system(mkpart_cmd, verbose=False)
    process.system(partprobe_cmd, timeout=timeout, verbose=False)
    partition_created = wait.wait_for(
        lambda: _list_disk_partitions() - orig_disks, step=0.5, timeout=30
    )
    if not partition_created:
        raise RuntimeError("Failed to create partition.")
    kname = partition_created.pop().split("/")[-1]
    return kname


def get_partition_attrs(partition):
    """
    Get partition attributes.

    :param partition: like /dev/sdb1.
    :return: dict like {'start': '512B', 'end': '16106127359B',
                       'size': '16106126848B', 'type': 'primary'}
    """
    pattern = r"(/dev/.*)p(\d+)" if "nvme" in partition else r"(/dev/.*)(\d+)"
    dev_name, part_num = re.match(pattern, partition).groups()
    parted_cmd = "parted -s %s unit B print" % dev_name
    pattern = re.compile(
        r"%s\s+(?P<start>\d+\w+)\s+(?P<end>\d+\w+)\s+"
        r"(?P<size>\d+\w+)\s+(?P<type>\w+)" % part_num
    )
    return pattern.search(
        process.run(parted_cmd, verbose=False).stdout_text, re.M
    ).groupdict()


def resize_partition(partition, size):
    """
    Resize partition.
    Note: not support gpt type resize for linux guest.

    :param partition: partition that to be shrunk, like /dev/sdb1.
    :param size: resize partition to size, unit is B.
    """
    mountpoint, fstype = filesystem.get_mpoint_fstype(partition)
    if filesystem.is_mounted(partition, dst=mountpoint, fstype=fstype):
        filesystem.umount(partition, mountpoint, fstype=fstype)

    # FIXME: if nvme device need support this function.
    dev_name, part_num = re.match(r"(/dev/.*)(\d+)", partition).groups()
    parted_cmd = "parted -s %s print" % dev_name
    part_attrs = get_partition_attrs(partition)
    start_size = int(
        utils_numeric.normalize_data_size(part_attrs["start"], "B").split(".")[0]
    )
    end_size = (
        int(utils_numeric.normalize_data_size(size, "B").split(".")[0]) - start_size
    )
    process.system(" ".join((parted_cmd, "rm %s" % part_num)), verbose=False)
    resizepart_cmd = " ".join((parted_cmd, "unit B mkpart {0} {1} {2}"))
    process.system(
        resizepart_cmd.format(part_attrs["type"], start_size, end_size), verbose=False
    )
    process.system("partprobe %s" % dev_name, verbose=False)


def get_disk_size(did):
    """
    Get disk size.

    :param did: disk kname. e.g. 'sdb', 'sdc'
    :return: disk size.
    """
    disks_info = get_disks_info(True)
    disk_size = disks_info["%s" % did][1]
    return int(utils_numeric.normalize_data_size(disk_size, "B").split(".")[0])


def get_partitions_list():
    """
    Get all partition list.

    :return: All partition list.
             e.g. ['sda', 'sda1', 'sda2', 'dm-0', 'dm-1', 'dm-2']
    :rtype: List
    """
    parts_cmd = "cat /proc/partitions"
    parts_out = process.run(parts_cmd, verbose=False).stdout_text
    parts = []
    if parts_out:
        for line in parts_out.rsplit("\n"):
            if line.startswith("major") or line == "":
                continue
            parts_line = line.rsplit()
            if len(parts_line) == 4:
                parts.append(parts_line[3])
    return parts


def get_disk_by_serial(serial_str):
    """
    Get disk by serial in host.

    :param serial_str: ID_SERIAL of disk, string value.
    :type serial_str: String
    :return: Disk name if find one with serial_str, else None.
    :rtype: String
    """
    parts_list = get_partitions_list()
    for disk in parts_list:
        cmd = "udevadm info --query=all --name=/dev/{} | grep ID_SERIAL={}".format(
            disk, serial_str
        )
        status = process.run(
            cmd, shell=True, ignore_status=True, verbose=False
        ).exit_status
        if not status:
            return disk
    return None


def get_drive_path(did, timeout=120):
    """
    Get drive path( devname ) on host by drive serial or wwn

    :param did: A drive serial( ID_SERIAL or ID_SERIAL_SHORT )
                or a wwn( ID_WWN ).
    :type did: String
    :param timeout: Time out.
    :type timeout: Integer

    :return: A drive path( devname )
    :rtype: String

    :raises: An RuntimeError will be raised when cmd exit code is NOT 0.
    """
    cmd = "for dev_path in `ls -d /sys/block/*`; do "
    cmd += "echo `udevadm info -q property -p $dev_path`; done"
    status, output = process.getstatusoutput(cmd, timeout=timeout)
    if status != 0:
        raise RuntimeError("Command running was failed. Output: %s" % output)
    p = r"DEVNAME=([^\s]+)\s.*(?:ID_SERIAL|ID_SERIAL_SHORT|ID_WWN)=%s" % did
    dev = re.search(p, output, re.M)
    if dev:
        return dev.groups()[0]
    return ""
