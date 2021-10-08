"""
Virtualization test - Virtual disk related utility functions

:copyright: Red Hat Inc.
"""
import os
import glob
import shutil
import stat
import platform
import random
import string
import tempfile
import logging
import re
try:
    import configparser as ConfigParser
except ImportError:
    import ConfigParser
from functools import cmp_to_key

from avocado.core import exceptions
from avocado.utils import process
from avocado.utils import wait
from avocado.utils.service import SpecificServiceManager

from virttest import error_context
from virttest import utils_numeric
from virttest import remote

PARTITION_TABLE_TYPE_MBR = "msdos"
PARTITION_TABLE_TYPE_GPT = "gpt"
PARTITION_TYPE_PRIMARY = "primary"
PARTITION_TYPE_EXTENDED = "extended"
PARTITION_TYPE_LOGICAL = "logical"

SIZE_AVAILABLE = "available size"

# Whether to print all shell commands called
DEBUG = False

LOG = logging.getLogger('avocado.' + __name__)


def copytree(src, dst, overwrite=True, ignore=''):
    """
    Copy dirs from source to target.

    :param src: source directory
    :param dst: destination directory
    :param overwrite: overwrite file if exist or not
    :param ignore: files want to ignore
    """
    ignore = glob.glob(os.path.join(src, ignore))
    for root, dirs, files in os.walk(src):
        dst_dir = root.replace(src, dst)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        for _ in files:
            if _ in ignore:
                continue
            src_file = os.path.join(root, _)
            dst_file = os.path.join(dst_dir, _)
            if os.path.exists(dst_file):
                if overwrite:
                    os.remove(dst_file)
                else:
                    continue
            shutil.copy(src_file, dst_dir)


def is_mount(src, dst=None, fstype=None, options=None, verbose=False,
             session=None):
    """
    Check is src or dst mounted.

    :param src: source device or directory
    :param dst: mountpoint, if None will skip to check
    :param fstype: file system type, if None will skip to check
    :param options: mount options should be separated by ","
    :param session: check within the session if given

    :return: True if mounted, else return False
    """
    mount_str = "%s %s %s" % (src, dst, fstype)
    mount_str = mount_str.replace('None', '').strip()
    mount_list_cmd = 'cat /proc/mounts'

    if session:
        mount_result = session.cmd_output_safe(mount_list_cmd)
    else:
        mount_result = process.run(mount_list_cmd, shell=True).stdout_text
    if verbose:
        LOG.debug("/proc/mounts contents:\n%s", mount_result)

    for result in mount_result.splitlines():
        if mount_str in result:
            if options:
                options = options.split(",")
                options_result = result.split()[3].split(",")
                for op in options:
                    if op not in options_result:
                        if verbose:
                            LOG.info("%s is not mounted with given"
                                     " option %s", src, op)
                        return False
            if verbose:
                LOG.info("%s is mounted", src)
            return True
    if verbose:
        LOG.info("%s is not mounted", src)
    return False


def mount(src, dst, fstype=None, options=None, verbose=False, session=None):
    """
    Mount src under dst if it's really mounted, then remout with options.

    :param src: source device or directory
    :param dst: mountpoint
    :param fstype: filesystem type need to mount
    :param options: mount options
    :param session: mount within the session if given

    :return: if mounted return True else return False
    """
    options = (options and [options] or [''])[0]
    if is_mount(src, dst, fstype, options, verbose, session):
        if 'remount' not in options:
            options = 'remount,%s' % options
    cmd = ['mount']
    if fstype:
        cmd.extend(['-t', fstype])
    if options:
        cmd.extend(['-o', options])
    cmd.extend([src, dst])
    cmd = ' '.join(cmd)
    if session:
        return session.cmd_status(cmd, safe=True) == 0
    return process.system(cmd, verbose=verbose) == 0


def umount(src, dst, fstype=None, verbose=False, session=None):
    """
    Umount src from dst, if src really mounted under dst.

    :param src: source device or directory
    :param dst: mountpoint
    :param fstype: fstype used to check if mounted as expected
    :param session: umount within the session if given

    :return: if unmounted return True else return False
    """
    mounted = is_mount(src, dst, fstype, verbose=verbose, session=session)
    if mounted:
        from . import utils_package
        package = "psmisc"
        # check package is available, if not try installing it
        if not utils_package.package_install(package):
            LOG.error("%s is not available/installed for fuser", package)
        fuser_cmd = "fuser -km %s" % dst
        umount_cmd = "umount %s" % dst
        if session:
            if not isinstance(session, remote.VMManager):
                session.cmd_output_safe(fuser_cmd)
            return session.cmd_status(umount_cmd, safe=True) == 0
        process.system(fuser_cmd, ignore_status=True, verbose=True, shell=True)
        return process.system(umount_cmd, ignore_status=True, verbose=True) == 0
    return True


@error_context.context_aware
def cleanup(folder):
    """
    If folder is a mountpoint, do what is possible to unmount it. Afterwards,
    try to remove it.

    :param folder: Directory to be cleaned up.
    """
    error_context.context(
        "cleaning up unattended install directory %s" % folder)
    umount(None, folder)
    if os.path.isdir(folder):
        shutil.rmtree(folder)


@error_context.context_aware
def clean_old_image(image):
    """
    Clean a leftover image file from previous processes. If it contains a
    mounted file system, do the proper cleanup procedures.

    :param image: Path to image to be cleaned up.
    """
    error_context.context("cleaning up old leftover image %s" % image)
    if os.path.exists(image):
        umount(image, None)
        os.remove(image)


def get_linux_disks(session, partition=False):
    """
    List all disks or disks with no partition.

    :param session: session object to guest
    :param partition: if true, list all disks; otherwise,
                      list only disks with no partition.
    :return: the disks dict.
             e.g. {kname: [kname, size, type, serial, wwn]}
    """
    disks_dict = {}
    parent_disks = set()
    driver = "pci"
    if platform.machine() == "s390x":
        driver = "css0"
    block_info = session.cmd('ls /sys/dev/block -l | grep "/%s"' % driver)
    for matched in re.finditer(r'/block/(\S+)\s^', block_info, re.M):
        knames = matched.group(1).split('/')
        if len(knames) == 2:
            parent_disks.add(knames[0])
        if partition is False and knames[0] in parent_disks:
            if knames[0] in disks_dict:
                del disks_dict[knames[0]]
            continue

        disks_dict[knames[-1]] = [knames[-1]]
        o = session.cmd('lsblk -o KNAME,SIZE | grep "%s "' % knames[-1])
        disks_dict[knames[-1]].append(o.split()[-1])
        o = session.cmd('udevadm info -q all -n %s' % knames[-1])
        for parttern in (r'DEVTYPE=(\w+)\s^', r'ID_SERIAL=(\S+)\s^', r'ID_WWN=(\S+)\s^'):
            searched = re.search(parttern, o, re.M | re.I)
            disks_dict[knames[-1]].append(searched.group(1) if searched else None)
    return disks_dict


def get_windows_disks_index(session, image_size, timeout=60):
    """
    Get all disks index which show in 'diskpart list disk'.
    except for system disk.
    in diskpart: if disk size < 8GB: it displays as MB
                 else: it displays as GB

    :param session: session object to guest.
    :param image_size: image size. e.g. 40M
    :param timeout: timeout for getting disks index.
    :return: a list with all disks index except for system disk.
    """
    disk = "disk_" + ''.join(random.sample(string.ascii_letters + string.digits, 4))
    disk_indexs = []
    list_disk_cmd = "echo list disk > " + disk
    list_disk_cmd += " && echo exit >> " + disk
    list_disk_cmd += " && diskpart /s " + disk
    list_disk_cmd += " && del /f " + disk
    disks = session.cmd_output(list_disk_cmd, timeout)
    size_type = image_size[-1] + "B"
    if size_type == "MB":
        disk_size = image_size[:-1] + " MB"
    elif size_type == "GB" and int(image_size[:-1]) < 8:
        disk_size = str(int(image_size[:-1]) * 1024) + " MB"
    else:
        disk_size = image_size[:-1] + " GB"
    regex_str = 'Disk (\d+).*?%s.*?%s' % (disk_size, disk_size)
    for disk in disks.splitlines():
        if disk.startswith("  Disk"):
            o = re.findall(regex_str, disk, re.I | re.M)
            if o:
                disk_indexs.append(o[0])
    return disk_indexs


def _wrap_windows_cmd(cmd):
    """
    add header and footer for cmd in order to run it in diskpart tool.

    :param cmd: cmd to be wrapped.
    :return: wrapped cmd
    """
    disk = "disk_" + ''.join(random.sample(string.ascii_letters + string.digits, 4))
    cmd_header = "echo list disk > " + disk
    cmd_header += " && echo select disk %s >> " + disk
    cmd_footer = " echo exit >> " + disk
    cmd_footer += " && diskpart /s " + disk
    cmd_footer += " && del /f " + disk
    cmd_list = []
    for i in cmd.split(";"):
        i += " >> " + disk
        cmd_list.append(i)
    cmd = " && ".join(cmd_list)
    return " && ".join([cmd_header, cmd, cmd_footer])


def update_windows_disk_attributes(session, dids, timeout=120):
    """
    Clear readonly for all disks and online them in windows guest.
    It is a workaround update attributes for all disks in one time.
    If configures disk(update attribute -> format) one by one,
    it will hit error.

    :param session: session object to guest.
    :param dids: a list with all disks index which
                 show in 'diskpart list disk'.
                 call function: get_windows_disks_index()
    :param timeout: time for cmd execution
    :return: True or False
    """
    detail_cmd = ' echo detail disk'
    detail_cmd = _wrap_windows_cmd(detail_cmd)
    set_rw_cmd = ' echo attributes disk clear readonly'
    set_rw_cmd = _wrap_windows_cmd(set_rw_cmd)
    online_cmd = ' echo online disk'
    online_cmd = _wrap_windows_cmd(online_cmd)
    for did in dids:
        LOG.info("Detail for 'Disk%s'" % did)
        details = session.cmd_output(detail_cmd % did)
        if re.search("Read.*Yes", details, re.I | re.M):
            LOG.info("Clear readonly bit on 'Disk%s'" % did)
            status, output = session.cmd_status_output(set_rw_cmd % did,
                                                       timeout=timeout)
            if status != 0:
                LOG.error("Can not clear readonly bit: %s" % output)
                return False
        if re.search("Status.*Offline", details, re.I | re.M):
            LOG.info("Online 'Disk%s'" % did)
            status, output = session.cmd_status_output(online_cmd % did,
                                                       timeout=timeout)
            if status != 0:
                LOG.error("Can not online disk: %s" % output)
                return False
    return True


def create_partition_table_linux(session, did, labeltype):
    """
    Create partition table on disk in linux guest.

    :param session: session object to guest.
    :param did: disk kname. e.g. sdb
    :param labeltype: label type for the disk.
    """
    mklabel_cmd = 'parted -s "/dev/%s" mklabel %s' % (did, labeltype)
    session.cmd(mklabel_cmd)


def create_partition_table_windows(session, did, labeltype):
    """
    Create partition table on disk in windows guest.
    mbr is default value, do nothing.

    :param session: session object to guest.
    :param did: disk index which show in 'diskpart list disk'.
    :param labeltype: label type for the disk.
    """
    if labeltype == PARTITION_TABLE_TYPE_GPT:
        mklabel_cmd = ' echo convert gpt'
        mklabel_cmd = _wrap_windows_cmd(mklabel_cmd)
        session.cmd(mklabel_cmd % did)


def create_partition_table(session, did, labeltype, ostype):
    """
    Create partition table on disk in linux or windows guest.

    :param session: session object to guest.
    :param did: disk kname or disk index
    :param labeltype: label type for the disk.
    :param ostype: linux or windows.
    """
    if ostype == "windows":
        create_partition_table_windows(session, did, labeltype)
    else:
        create_partition_table_linux(session, did, labeltype)


def create_partition_linux(session, did, size, start,
                           part_type=PARTITION_TYPE_PRIMARY, timeout=360):
    """
    Create single partition on disk in linux guest.

    :param session: session object to guest.
    :param did: disk kname. e.g. sdb
    :param size: partition size. e.g. 200M
    :param start: partition beginning at start. e.g. 0M
    :param part_type: partition type, primary extended logical
    :param timeout: Timeout for cmd execution in seconds.
    :return: The kname of partition created.
    """
    def _list_disk_partitions():
        driver = "pci"
        if platform.machine() == "s390x":
            driver = "css0"
        o = session.cmd('ls /sys/dev/block -l | grep "/%s" | grep "%s" '
                        '--color=never' % (driver, did))
        return set(o.splitlines())

    size = utils_numeric.normalize_data_size(size, order_magnitude="M") + "M"
    start = utils_numeric.normalize_data_size(start, order_magnitude="M") + "M"
    end = str(float(start[:-1]) + float(size[:-1])) + size[-1]
    orig_disks = _list_disk_partitions()
    partprobe_cmd = "partprobe /dev/%s" % did
    mkpart_cmd = 'parted -s "%s" mkpart %s %s %s'
    mkpart_cmd %= ("/dev/%s" % did, part_type, start, end)
    session.cmd(mkpart_cmd)
    session.cmd(partprobe_cmd, timeout=timeout)
    partition_created = wait.wait_for(lambda: _list_disk_partitions() - orig_disks,
                                      step=0.5, timeout=30)
    if not partition_created:
        raise exceptions.TestError('Failed to create partition.')
    kname = partition_created.pop().split('/')[-1]
    return kname


def create_partition_windows(session, did, size, start,
                             part_type=PARTITION_TYPE_PRIMARY, timeout=360):
    """
    Create single partition on disk in windows guest.

    :param session: session object to guest.
    :param did: disk index
    :param size: partition size. e.g. size 200M
    :param start: partition beginning at start. e.g. 0M
    :param part_type: partition type, primary extended logical
    :param timeout: Timeout for cmd execution in seconds.
    :return: The index of partition created.
    """
    size = utils_numeric.normalize_data_size(size, order_magnitude="M")
    start = utils_numeric.normalize_data_size(start, order_magnitude="M")
    size = int(float(size) - float(start))
    mkpart_cmd = " echo create partition %s size=%s; echo list partition"
    mkpart_cmd = _wrap_windows_cmd(mkpart_cmd)
    output = session.cmd(mkpart_cmd % (did, part_type, size), timeout=timeout)
    return re.search(r'\*\s+Partition\s+(\d+)\s+', output, re.M).group(1)


def create_partition(session, did, size, start, ostype,
                     part_type=PARTITION_TYPE_PRIMARY, timeout=360):
    """
    Create single partition on disk in windows or linux guest.

    :param session: session object to guest.
    :param did: disk kname or disk index
    :param size: partition size. e.g. size 2G
    :param start: partition beginning at start. e.g. 0G
    :param ostype: linux or windows.
    :param part_type: partition type, primary extended logical
    :param timeout: Timeout for cmd execution in seconds.
    :return: The kname of partition created in linux, index in windows.
    """
    if ostype == "windows":
        return create_partition_windows(session, did, size, start, part_type, timeout)
    else:
        return create_partition_linux(session, did, size, start, part_type, timeout)


def delete_partition_linux(session, partition_name, timeout=360):
    """
    remove single partition for one disk.

    :param session: session object to guest.
    :param partition_name: partition name. e.g. sdb1
    :param timeout: Timeout for cmd execution in seconds.
    """
    driver = "pci"
    if platform.machine() == "s390x":
        driver = "css0"
    ls_block_cmd = 'ls /sys/dev/block -l | grep "/%s"' % driver
    regex = r'/block/(\S+)/%s\s^' % partition_name
    kname = re.search(regex, session.cmd(ls_block_cmd), re.M).group(1)
    list_disk_cmd = "lsblk -o KNAME,MOUNTPOINT"
    output = session.cmd_output(list_disk_cmd)
    output = output.splitlines()
    rm_cmd = 'parted -s "/dev/%s" rm %s'
    for line in output:
        partition = re.findall(partition_name, line, re.I | re.M)
        if partition:
            if "/" in line.split()[-1]:
                if not umount("/dev/%s" % partition_name, line.split()[-1], session=session):
                    err_msg = "Failed to umount partition '%s'"
                    raise exceptions.TestError(err_msg % partition_name)
            break
    session.cmd(rm_cmd % (kname, partition[0]))
    session.cmd("partprobe /dev/%s" % kname, timeout=timeout)
    if not wait.wait_for(lambda: not re.search(
            regex, session.cmd(ls_block_cmd), re.M), step=0.5, timeout=30):
        raise exceptions.TestError('Failed to delete partition.')


def delete_partition_windows(session, partition_name, timeout=360):
    """
    remove single partition for one disk.

    :param session: session object to guest.
    :param partition_name: partition name. e.g. D
    :param timeout: Timeout for cmd execution in seconds.
    """
    disk = "disk_" + ''.join(random.sample(string.ascii_letters + string.digits, 4))
    delete_cmd = "echo select volume %s > " + disk
    delete_cmd += " && echo delete volume >> " + disk
    delete_cmd += " && echo exit >> " + disk
    delete_cmd += " && diskpart /s " + disk
    delete_cmd += " && del /f " + disk
    session.cmd(delete_cmd % partition_name, timeout=timeout)


def delete_partition(session, partition_name, ostype, timeout=360):
    """
    remove single partition for one disk in linux or windows guest.

    :param session: session object to guest.
    :param partition_name: partition name.
    :param ostype: linux or windows.
    :param timeout: Timeout for cmd execution in seconds.
    """
    if ostype == "windows":
        delete_partition_windows(session, partition_name, timeout)
    else:
        delete_partition_linux(session, partition_name, timeout)


def clean_partition_linux(session, did, timeout=360):
    """
    clean partition for linux guest.

    :param session: session object to guest.
    :param did: disk ID in guest.
                for linux: disk kname. e.g. 'sdb', 'nvme0n1'
    :param timeout: Timeout for cmd execution in seconds.
    """
    list_disk_cmd = "lsblk -o KNAME,MOUNTPOINT"
    output = session.cmd_output(list_disk_cmd)
    output = output.splitlines()
    regex_str = did + "\w*(\d+)"
    rm_cmd = 'parted -s "/dev/%s" rm %s'
    for line in output:
        partition = re.findall(regex_str, line, re.I | re.M)
        if partition:
            if "/" in line.split()[-1]:
                if not umount("/dev/%s" % line.split()[0], line.split()[-1], session=session):
                    err_msg = "Failed to umount partition '%s'"
                    raise exceptions.TestError(err_msg % line.split()[0])
    list_partition_number = "parted -s /dev/%s print|awk '/^ / {print $1}'"
    partition_numbers = session.cmd_output(list_partition_number % did)
    ignore_err_msg = "unrecognised disk label"
    if ignore_err_msg in partition_numbers:
        LOG.info("no partition to clean on %s" % did)
    else:
        partition_numbers = partition_numbers.splitlines()
        for number in partition_numbers:
            LOG.info("remove partition %s on %s" % (number, did))
            session.cmd(rm_cmd % (did, number))
        session.cmd("partprobe /dev/%s" % did, timeout=timeout)
        regex = r'/block/%s/\S+\s^' % did
        driver = "pci"
        if platform.machine() == "s390x":
            driver = "css0"
        ls_block_cmd = ('ls /sys/dev/block -l | grep "/%s" | grep "%s"' %
                        (driver, did))
        if not wait.wait_for(lambda: not re.search(
                regex, session.cmd(ls_block_cmd), re.M), step=0.5, timeout=30):
            raise exceptions.TestError('Failed to clean the all partitions.')


def clean_partition_windows(session, did, timeout=360):
    """
    clean partition for windows guest.

    :param session: session object to guest.
    :param did: disk ID in guest.
                for windows: disk index which
                             show in 'diskpart list disk'.
                             e.g. 1, 2
    :param timeout: Timeout for cmd execution in seconds.
    """
    clean_cmd = " echo clean "
    clean_cmd = _wrap_windows_cmd(clean_cmd)
    session.cmd(clean_cmd % did, timeout=timeout)


def clean_partition(session, did, ostype, timeout=360):
    """
    clean partition for disk in linux or windows guest.

    :param session: session object to guest.
    :param did: disk ID in guest.
                for linux: disk kname. e.g. 'sdb', 'sdc'
                for windows: disks index which
                             show in 'diskpart list disk'.
                             e.g. 1, 2
    :param ostype: guest os type 'windows' or 'linux'.
    :param timeout: Timeout for cmd execution in seconds.
    """
    if ostype == "windows":
        clean_partition_windows(session, did, timeout)
    else:
        clean_partition_linux(session, did, timeout)


def create_filesyetem_linux(session, partition_name, fstype, timeout=360):
    """
    create file system in linux guest.

    :param session: session object to guest.
    :param partition_name: partition name that to be formatted. e.g. sdb1
    :param fstype: filesystem type for the disk.
    :param timeout: Timeout for cmd execution in seconds.
    """
    if fstype == "xfs":
        mkfs_cmd = "mkfs.%s -f" % fstype
    else:
        mkfs_cmd = "mkfs.%s -F" % fstype
    format_cmd = "yes|%s '/dev/%s'" % (mkfs_cmd, partition_name)
    session.cmd(format_cmd, timeout=timeout)


def create_filesystem_windows(session, partition_name, fstype,
                              timeout=360, quick_format=True):
    """
    create file system in windows guest.

    :param session: session object to guest.
    :param partition_name: partition name that to be formatted. e.g. D
    :param fstype: file system type for the disk.
    :param timeout: Timeout for cmd execution in seconds.
    :param quick_format: Whether use quick format or not.
    """
    disk = "disk_" + ''.join(random.sample(string.ascii_letters + string.digits, 4))
    format_cmd = "echo select volume %s > " + disk
    format_cmd += " && echo format fs=%s "
    if quick_format:
        format_cmd += "quick "
    format_cmd += ">> " + disk
    format_cmd += " && echo exit >> " + disk
    format_cmd += " && diskpart /s " + disk
    format_cmd += " && del /f " + disk
    session.cmd(format_cmd % (partition_name, fstype), timeout=timeout)


def create_filesystem(session, partition_name, fstype, ostype, timeout=360):
    """
    create file system in windows or linux guest.

    :param session: session object to guest.
    :param partition_name: partition name that to be formatted.
    :param fstype: file system type for the disk.
    :param ostype: guest os type 'windows' or 'linux'.
    :param timeout: Timeout for cmd execution in seconds.
    """
    if ostype == "windows":
        create_filesystem_windows(session, partition_name, fstype, timeout)
    else:
        create_filesyetem_linux(session, partition_name, fstype, timeout)


def _get_mpoint_fstype_linux(session, partition):
    """
    Get a partition's file system type and mountpoint.

    :param session: session object to guest.
    :param partition: disk partition, like /dev/sdb1.
    :return: Tuple (mountpoint, fstype)
    """
    mount_list = session.cmd_output('cat /proc/mounts')
    mount_info = re.search(r'%s\s(.+?)\s(.+?)\s' % partition, mount_list)
    return mount_info.groups()


def get_scsi_info(device_source):
    """
    Gets scsi info

    :param device_source: source device path, e.g. /dev/sda
    :raise TestError: if 'lsscsi' output is unexpected
    :return: "scsi_num:bus_num:target_num:unit_num"
    """
    cmd = "lsscsi | grep %s | awk '{print $1}'" % device_source
    cmd_result = process.run(cmd, shell=True)
    scsi_info = re.findall("\d+", str(cmd_result.stdout.strip()))
    if len(scsi_info) != 4:
        raise exceptions.TestError("Got wrong scsi info: %s" % scsi_info)
    return ":".join(scsi_info)


def get_partition_attrs_linux(session, partition):
    """
    Get partition attributes in linux guest.

    :param session: session object to guest.
    :param partition: like /dev/sdb1.
    :return: dict like {'start': '512B', 'end': '16106127359B',
                       'size': '16106126848B', 'type': 'primary'}
    """
    pattern = r'(/dev/.*)p(\d+)' if "nvme" in partition else r'(/dev/.*)(\d+)'
    dev_name, part_num = re.match(pattern, partition).groups()
    parted_cmd = 'parted -s %s unit B print' % dev_name
    pattern = re.compile(r'%s\s+(?P<start>\d+\w+)\s+(?P<end>\d+\w+)\s+'
                         r'(?P<size>\d+\w+)\s+(?P<type>\w+)' % part_num)
    return pattern.search(session.cmd(parted_cmd), re.M).groupdict()


def resize_filesystem_linux(session, partition, size):
    """
    Resize file system in linux guest.
    For ext2, ext3, ext4 filesystem, support enlarge and shrink.
    For xfs filesystem, only support enlarge, not support shrink.

    :param session: session object to guest.
    :param partition: disk partition, like /dev/sdb1.
    :param size: resize file system to size.
                 size unit can be 'B', 'K', 'M', 'G'.
                 support transfer size with SIZE_AVAILABLE,
                 enlarge to maximun available size.
    """
    def get_start_size():
        start_size = get_partition_attrs_linux(session, partition)['start']
        return int(utils_numeric.normalize_data_size(start_size, 'B').split('.')[0])

    def resize_xfs_fs(size):
        if size == SIZE_AVAILABLE:
            resize_fs_cmd = 'xfs_growfs -d %s' % mountpoint
        else:
            output = session.cmd_output('xfs_growfs -n %s' % mountpoint)
            bsize = int(re.findall(r'data\s+=\s+bsize=(\d+)', output, re.M)[0])
            blocks = (int(utils_numeric.normalize_data_size(size, 'B').split('.')[0]) -
                      get_start_size()) // bsize
            resize_fs_cmd = 'xfs_growfs -D %s %s' % (blocks, mountpoint)
        session.cmd(resize_fs_cmd)

    def resize_ext_fs(size):
        flag = False
        if is_mount(partition, dst=mountpoint, fstype=fstype, session=session):
            umount(partition, mountpoint, fstype=fstype, session=session)
            flag = True

        session.cmd('e2fsck -f %s' % partition)

        if size == SIZE_AVAILABLE:
            resize_fs_cmd = 'resize2fs %s' % partition
        else:
            output = session.cmd_output('tune2fs -l %s | grep -i block' % partition)
            bsize = int(re.findall(r'Block size:\s+(\d+)', output, re.M)[0])
            size = ((int(utils_numeric.normalize_data_size(size, 'B').split(".")[0]) -
                     get_start_size()) // bsize) * bsize
            size = utils_numeric.normalize_data_size(str(size).split(".")[0], 'K')
            resize_fs_cmd = 'resize2fs %s %sK' % (partition, int(size.split(".")[0]))
        session.cmd(resize_fs_cmd)
        if flag:
            mount(partition, mountpoint, fstype=fstype, session=session)

    mountpoint, fstype = _get_mpoint_fstype_linux(session, partition)
    if fstype == 'xfs':
        resize_xfs_fs(size)
    elif fstype.startswith("ext"):
        resize_ext_fs(size)
    else:
        raise NotImplementedError


def resize_partition_linux(session, partition, size):
    """
    Resize partition in linux guest.
    Note: not support gpt type resize for linux guest.

    :param session: session object to guest.
    :param partition: partition that to be shrunk, like /dev/sdb1.
    :param size: resize partition to size, unit is B.
    """
    mountpoint, fstype = _get_mpoint_fstype_linux(session, partition)
    flag = False
    if is_mount(partition, dst=mountpoint, fstype=fstype, session=session):
        umount(partition, mountpoint, fstype=fstype, session=session)
        flag = True

    # FIXME: if nvme device need support this function.
    dev_name, part_num = re.match(r'(/dev/.*)(\d+)', partition).groups()
    parted_cmd = 'parted -s %s print' % dev_name
    part_attrs = get_partition_attrs_linux(session, partition)
    start_size = int(utils_numeric.normalize_data_size(part_attrs['start'],
                                                       'B').split('.')[0])
    end_size = (int(utils_numeric.normalize_data_size(size, 'B').split('.')[0])
                - start_size)
    session.cmd(' '.join((parted_cmd, 'rm %s' % part_num)))
    resizepart_cmd = ' '.join((parted_cmd, 'unit B mkpart {0} {1} {2}'))
    session.cmd(resizepart_cmd.format(part_attrs['type'], start_size, end_size))
    session.cmd('partprobe %s' % dev_name)

    if fstype == 'xfs':
        session.cmd('xfs_repair -n %s' % partition)
    elif fstype.startswith("ext"):
        session.cmd('e2fsck -f %s' % partition)
    else:
        raise NotImplementedError

    if flag:
        mount(partition, mountpoint, fstype=fstype, session=session)


def get_disk_size_windows(session, did):
    """
    Get disk size from windows guest.

    :param session: session object to guest.
    :param did: disk index which show in 'diskpart list disk'.
                e.g. 0, 1
    :return: disk size.
    """
    cmd = "wmic diskdrive get size, index"
    return int(re.findall(r'%s\s+(\d+)' % did, session.cmd_output(cmd))[0])


def get_disk_size_linux(session, did):
    """
    Get disk size from linux guest.

    :param session: session object to guest.
    :param did: disk kname. e.g. 'sdb', 'sdc'
    :return: disk size.
    """
    disks_info = get_linux_disks(session, partition=True)
    disk_size = disks_info['%s' % did][1]
    return int(utils_numeric.normalize_data_size(disk_size, 'B').split('.')[0])


def get_disk_size(session, os_type, did):
    """
    Get disk size from guest.

    :param session: session object to guest.
    :param ostype: guest os type 'windows' or 'linux'.
    :param did: disk ID in guest.
    :return: disk size.
    """
    if os_type == "linux":
        return get_disk_size_linux(session, did)
    else:
        return get_disk_size_windows(session, did)


def get_drive_letters(session, did):
    """
    Get drive letters of specified disk in windows guest.

    :param session: Windows VM session.
    :type session: aexpect.ShellSession
    :param did: The disk index.
    :type did: str
    :return: The drive letters.
    :rtype: list
    """
    disk_script = "disk_" + ''.join(
        random.sample(string.ascii_letters + string.digits, 4))
    select_cmd = "echo select disk %s > %s " % (did, disk_script)
    detail_cmd = "echo detail disk >> %s" % disk_script
    diskpart_cmd = "diskpart /s %s" % disk_script
    cmd = ' && '.join((select_cmd, detail_cmd, diskpart_cmd))
    output = session.cmd(cmd)

    letter_offset = 0
    searched_ret = re.search(r"(.*Volume\s+.*Ltr.*)", output, re.I | re.M)
    if searched_ret:
        letter_offset = searched_ret.group(1).index('Ltr') + 1

    if letter_offset:
        vol_details = re.findall(r"(.*Volume\s+\d+.*Partition.*)", output, re.I | re.M)
        return [_[letter_offset] for _ in vol_details if _[letter_offset].isalpha()]
    return []


def set_drive_letter(session, did, partition_no=1, target_letter=None):
    """
    set drive letter for partition in windows guest.

    :param session: session object to guest.
    :param did: disk index
    :param partition_no: partition number
    :param target_letter: target drive letter
    :return drive_letter: drive letter has been set
    """
    drive_letter = ""
    list_partition_cmd = ' echo list partition '
    list_partition_cmd = _wrap_windows_cmd(list_partition_cmd)
    details = session.cmd_output(list_partition_cmd % did)
    for line in details.splitlines():
        if re.search("Reserved", line, re.I | re.M):
            partition_no += int(line.split()[1])
    assign_letter_cmd = ' echo select partition %s ; echo assign '
    if target_letter:
        assign_letter_cmd += 'letter=%s' % target_letter
    assign_letter_cmd = _wrap_windows_cmd(assign_letter_cmd)
    session.cmd(assign_letter_cmd % (did, partition_no))
    detail_cmd = ' echo detail disk '
    detail_cmd = _wrap_windows_cmd(detail_cmd)
    details = session.cmd_output(detail_cmd % did)
    for line in details.splitlines():
        pattern = "\s+Volume\s+\d+"
        if re.search(pattern, line, re.I | re.M):
            drive_letter = line.split()[2]
            break
    if len(drive_letter) == 1 and drive_letter.isalpha():
        if target_letter:
            if target_letter != drive_letter:
                return None
        return drive_letter
    else:
        return None


def drop_drive_letter(session, drive_letter):
    """
    remove drive letter for partition in windows guest.

    :param session: session object to guest.
    :param drive_letter: drive letter to be removed
    """
    disk = "disk_" + ''.join(random.sample(string.ascii_letters + string.digits, 4))
    remove_cmd = "echo select volume %s > " + disk
    remove_cmd += " && echo remove >> " + disk
    remove_cmd += " && echo exit >> " + disk
    remove_cmd += " && diskpart /s " + disk
    remove_cmd += " && del /f " + disk
    session.cmd(remove_cmd % drive_letter)


def configure_empty_windows_disk(session, did, size, start="0M",
                                 n_partitions=1, fstype="ntfs",
                                 labeltype=PARTITION_TABLE_TYPE_MBR,
                                 timeout=360, quick_format=True):
    """
    Create partition on disks in windows guest, format and mount it.
    Only handle an empty disk and will create equal size partitions onto the disk.

    :param session: session object to guest.
    :param did: disk index which show in 'diskpart list disk'.
    :param size: partition size. e.g. 500M
    :param start: partition beginning at start. e.g. 0M
    :param n_partitions: the number of partitions on disk
    :param fstype: filesystem type for the disk.
    :param labeltype: label type for the disk.
    :param timeout: Timeout for cmd execution in seconds.
    :param quick_format: Whether use quick format or not.
    :return a list: mount point list for all partitions.
    """
    mountpoint = []
    create_partition_table_windows(session, did, labeltype)
    start = utils_numeric.normalize_data_size(start, order_magnitude="M") + "M"
    partition_size = float(size[:-1]) / n_partitions
    extended_size = float(size[:-1]) - partition_size
    reserved_size = 5
    if labeltype == PARTITION_TABLE_TYPE_MBR and n_partitions > 1:
        part_type = PARTITION_TYPE_EXTENDED
    else:
        part_type = PARTITION_TYPE_PRIMARY
    for i in range(n_partitions):
        if i == 0:
            create_partition_windows(
                session, did, str(partition_size) + size[-1],
                str(float(start[:-1]) + reserved_size) + start[-1], timeout=timeout)
        else:
            if part_type == PARTITION_TYPE_EXTENDED:
                create_partition_windows(
                    session, did, str(extended_size) + size[-1], start, part_type, timeout)
                part_type = PARTITION_TYPE_LOGICAL
                create_partition_windows(
                    session, did, str(partition_size) + size[-1], start, part_type, timeout)
            else:
                create_partition_windows(
                    session, did, str(partition_size) + size[-1], start, part_type, timeout)
        drive_letter = set_drive_letter(session, did, partition_no=i + 1)
        if not drive_letter:
            return []
        mountpoint.append(drive_letter)
        create_filesystem_windows(session, mountpoint[i], fstype, timeout, quick_format=quick_format)
    return mountpoint


def configure_empty_linux_disk(session, did, size, start="0M", n_partitions=1,
                               fstype="ext4", labeltype=PARTITION_TABLE_TYPE_MBR,
                               timeout=360):
    """
    Create partition on disk in linux guest, format and mount it.
    Only handle an empty disk and will create equal size partitions onto the disk.
    Note: Make sure '/mnt/' is not mount point before run this function,
          in order to avoid unknown exceptions.

    :param session: session object to guest.
    :param did: disk kname. e.g. sdb
    :param size: partition size. e.g. 2G
    :param start: partition beginning at start. e.g. 0G
    :param n_partitions: the number of partitions on disk
    :param fstype: filesystem type for the disk.
    :param labeltype: label type for the disk.
    :param timeout: Timeout for cmd execution in seconds.
    :return a list: mount point list for all partitions.
    """
    mountpoint = []
    create_partition_table_linux(session, did, labeltype)
    size = utils_numeric.normalize_data_size(size, order_magnitude="M") + "M"
    start = float(utils_numeric.normalize_data_size(start, order_magnitude="M"))
    partition_size = float(size[:-1]) / n_partitions
    extended_size = float(size[:-1]) - partition_size
    if labeltype == PARTITION_TABLE_TYPE_MBR and n_partitions > 1:
        part_type = PARTITION_TYPE_EXTENDED
    else:
        part_type = PARTITION_TYPE_PRIMARY
    for i in range(n_partitions):
        if i == 0:
            new_partition = create_partition_linux(
                    session, did, str(partition_size) + size[-1],
                    str(start) + size[-1], timeout=timeout)
        else:
            if part_type == PARTITION_TYPE_EXTENDED:
                create_partition_linux(session, did, str(extended_size) + size[-1],
                                       str(start) + size[-1], part_type, timeout)
                part_type = PARTITION_TYPE_LOGICAL
                new_partition = create_partition_linux(
                        session, did, str(partition_size) + size[-1],
                        str(start) + size[-1], part_type, timeout)
            else:
                new_partition = create_partition_linux(
                        session, did, str(partition_size) + size[-1],
                        str(start) + size[-1], part_type, timeout)
        start += partition_size
        create_filesyetem_linux(session, new_partition, fstype, timeout)
        mount_dst = "/mnt/" + new_partition
        session.cmd("rm -rf %s; mkdir %s" % (mount_dst, mount_dst))
        if not mount("/dev/%s" % new_partition, mount_dst, fstype=fstype, session=session):
            err_msg = "Failed to mount partition '%s'"
            raise exceptions.TestError(err_msg % new_partition)
        mountpoint.append(mount_dst)
    return mountpoint


def configure_empty_disk(session, did, size, ostype, start="0M", n_partitions=1,
                         fstype=None, labeltype=PARTITION_TABLE_TYPE_MBR,
                         timeout=360):
    """
    Create partition on disk in guest, format and mount it.
    Only handle an empty disk and will create equal size partitions onto the disk.

    :param session: session object to guest.
    :param did: disk ID list in guest.
                for linux: disk kname, serial or wwn.
                           e.g. 'sdb'
                for windows: disk index which show in 'diskpart list disk'
                             call function: get_windows_disks_index()
    :param size: partition size. e.g. size 2G
    :param ostype: guest os type 'windows' or 'linux'.
    :param start: partition beginning at start. e.g. 0G
    :param n_partitions: the number of partitions on disk for guest
    :param fstype: filesystem type for the disk; when it's the default None,
                   it will use the default one for corresponding ostype guest
    :param labeltype: label type for the disk.
    :param timeout: Timeout for cmd execution in seconds.
    :return a list: mount point list for all partitions.
    """
    default_fstype = "ntfs" if (ostype == "windows") else "ext4"
    fstype = fstype or default_fstype
    if ostype == "windows":
        return configure_empty_windows_disk(session, did, size, start,
                                            n_partitions, fstype,
                                            labeltype, timeout)
    return configure_empty_linux_disk(session, did, size, start,
                                      n_partitions, fstype,
                                      labeltype, timeout)


def linux_disk_check(session, did):
    """
    Check basic functions for linux guest disk on localhost.
    Create partition on disk, format, mount, create a file and then unmount, clean
    partition

    :param session: VM session
    :param did: Disk Kname in VM. eg. vdb
    """

    mount_point = configure_empty_linux_disk(session, did, "100M")
    try:
        if len(mount_point) != 1:
            raise exceptions.TestError("Incorrect mount point {}".format(mount_point))
        cmd = "echo teststring >  {}/testfile".format(mount_point[0])
        if session.cmd_status(cmd):
            raise exceptions.TestError("Failed to run {}".format(cmd))
    finally:
        clean_partition_linux(session, did)


def get_parts_list(session=None):
    """
    Get all partition lists.
    """
    parts_cmd = "cat /proc/partitions"
    if session:
        _, parts_out = session.cmd_status_output(parts_cmd)
    else:
        parts_out = process.run(parts_cmd).stdout_text
    parts = []
    if parts_out:
        for line in parts_out.rsplit("\n"):
            if line.startswith("major") or line == "":
                continue
            parts_line = line.rsplit()
            if len(parts_line) == 4:
                parts.append(parts_line[3])
    LOG.debug("Find parts: %s", parts)
    return parts


def get_added_parts(session, old_parts):
    """
    Get newly added partition list comparing to old parts

    :param session: the vm session
    :param old_parts: list, the old partition list
    :return: list, the newly added partition list
    """
    new_parts = get_parts_list(session)
    added_parts = list(set(new_parts).difference(set(old_parts)))
    LOG.info("Added parts:%s", added_parts)
    return added_parts


def get_first_disk(session=None):
    """
    Get the first disk device on host or guest

    :param session: the vm session
    :return: str, the disk device, like 'vda' or 'sda'
    """
    first_disk = ""
    disks = get_parts_list(session=session)
    for disk in disks:
        pattern = re.compile('[0-9]+')
        if not pattern.findall(disk):
            first_disk = disk
            break
    return first_disk


def get_disk_by_serial(serial_str, session=None):
    """
    Get disk by serial in VM or host

    :param serial_str: ID_SERIAL of disk, string value
    :param session: VM session or None
    :return: Disk name if find one with serial_str, else None
    """
    parts_list = get_parts_list(session=session)
    for disk in parts_list:
        cmd = ("udevadm info --query=all --name=/dev/{} | grep ID_SERIAL={}"
               .format(disk, serial_str))
        if session:
            status = session.cmd_status(cmd)
        else:
            status = process.run(cmd, shell=True, ignore_status=True).exit_status
        if not status:
            LOG.debug("Disk %s has serial %s", disk, serial_str)
            return disk


def check_remote_vm_disks(params):
    """
    Check disks in remote vm are working well with I/O.

    :param params: the dict used for parameters
    """
    remote_vm_obj = remote.VMManager(params)
    remote_vm_obj.check_network()
    remote_vm_obj.setup_ssh_auth()
    disks = get_linux_disks(remote_vm_obj, False)
    LOG.debug("Get disks in remote VM: %s", disks)

    for disk in disks.keys():
        linux_disk_check(remote_vm_obj, disk)


def dd_data_to_vm_disk(session, disk, bs='1M', seek='0', count='100'):
    """
    Generate some random data to a vm disk

    :param session: The vm session we'll use
    :param disk: The disk of the vm we'll use
    :param bs: The 'bs' param of the 'dd' command
    :param seek: The 'seek' param of the 'dd' command
    :param count: The 'count' param of the 'dd' command
    """
    dd_cmd = "dd if=/dev/urandom of=%s bs=%s seek=%s count=%s; sync"
    dd_cmd %= (disk, bs, seek, count)
    output = session.cmd_output(dd_cmd).strip()
    LOG.debug("Using dd to generate data to %s: %s", disk, output)


class Disk(object):

    """
    Abstract class for Disk objects, with the common methods implemented.
    """

    def __init__(self):
        self.path = None

    def get_answer_file_path(self, filename):
        return os.path.join(self.mount, filename)

    def copy_to(self, src):
        LOG.debug("Copying %s to disk image mount", src)
        dst = os.path.join(self.mount, os.path.basename(src))
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        elif os.path.isfile(src):
            shutil.copyfile(src, dst)

    def close(self):
        os.chmod(self.path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP |
                 stat.S_IROTH | stat.S_IXOTH)
        cleanup(self.mount)
        LOG.debug("Disk %s successfully set", self.path)


class FloppyDisk(Disk):

    """
    Represents a floppy disk. We can copy files to it, and setup it in
    convenient ways.
    """
    @error_context.context_aware
    def __init__(self, path, qemu_img_binary, tmpdir, vfd_size):
        error_context.context(
            "Creating unattended install floppy image %s" % path)
        self.mount = tempfile.mkdtemp(prefix='floppy_virttest_', dir=tmpdir)
        self.path = path
        self.vfd_size = vfd_size
        clean_old_image(path)
        try:
            c_cmd = '%s create -f raw %s %s' % (qemu_img_binary, path,
                                                self.vfd_size)
            process.run(c_cmd, verbose=DEBUG)
            f_cmd = 'mkfs.msdos -s 1 %s' % path
            process.run(f_cmd, verbose=DEBUG)
        except process.CmdError as e:
            LOG.error("Error during floppy initialization: %s" % e)
            cleanup(self.mount)
            raise

    def close(self):
        """
        Copy everything that is in the mountpoint to the floppy.
        """
        pwd = os.getcwd()
        try:
            os.chdir(self.mount)
            path_list = glob.glob('*')
            for path in path_list:
                self.copy_to(path)
        finally:
            os.chdir(pwd)

        cleanup(self.mount)

    def copy_to(self, src):
        LOG.debug("Copying %s to floppy image", src)
        mcopy_cmd = "mcopy -s -o -n -i %s %s ::/" % (self.path, src)
        process.run(mcopy_cmd, verbose=DEBUG)

    def _copy_virtio_drivers(self, virtio_floppy):
        """
        Copy the virtio drivers on the virtio floppy to the install floppy.

        1) Mount the floppy containing the viostor drivers
        2) Copy its contents to the root of the install floppy
        """
        pwd = os.getcwd()
        try:
            m_cmd = 'mcopy -s -o -n -i %s ::/* %s' % (
                virtio_floppy, self.mount)
            process.run(m_cmd, verbose=DEBUG)
        finally:
            os.chdir(pwd)

    def setup_virtio_win2003(self, virtio_floppy, virtio_oemsetup_id):
        """
        Setup the install floppy with the virtio storage drivers, win2003 style.

        Win2003 and WinXP depend on the file txtsetup.oem file to install
        the virtio drivers from the floppy, which is a .ini file.
        Process:

        1) Copy the virtio drivers on the virtio floppy to the install floppy
        2) Parse the ini file with config parser
        3) Modify the identifier of the default session that is going to be
           executed on the config parser object
        4) Re-write the config file to the disk
        """
        self._copy_virtio_drivers(virtio_floppy)
        txtsetup_oem = os.path.join(self.mount, 'txtsetup.oem')

        if not os.path.isfile(txtsetup_oem):
            raise IOError('File txtsetup.oem not found on the install '
                          'floppy. Please verify if your floppy virtio '
                          'driver image has this file')

        parser = ConfigParser.ConfigParser()
        parser.read(txtsetup_oem)

        if not parser.has_section('Defaults'):
            raise ValueError('File txtsetup.oem does not have the session '
                             '"Defaults". Please check txtsetup.oem')

        default_driver = parser.get('Defaults', 'SCSI')
        if default_driver != virtio_oemsetup_id:
            parser.set('Defaults', 'SCSI', virtio_oemsetup_id)
            fp = open(txtsetup_oem, 'w')
            parser.write(fp)
            fp.close()

    def setup_virtio_win2008(self, virtio_floppy):
        """
        Setup the install floppy with the virtio storage drivers, win2008 style.

        Win2008, Vista and 7 require people to point out the path to the drivers
        on the unattended file, so we just need to copy the drivers to the
        driver floppy disk. Important to note that it's possible to specify
        drivers from a CDROM, so the floppy driver copy is optional.
        Process:

        1) Copy the virtio drivers on the virtio floppy to the install floppy,
           if there is one available
        """
        if os.path.isfile(virtio_floppy):
            self._copy_virtio_drivers(virtio_floppy)
        else:
            LOG.debug("No virtio floppy present, not needed for this OS anyway")


class CdromDisk(Disk):

    """
    Represents a CDROM disk that we can master according to our needs.
    """

    def __init__(self, path, tmpdir):
        self.mount = tempfile.mkdtemp(prefix='cdrom_virttest_', dir=tmpdir)
        self.tmpdir = tmpdir
        self.path = path
        clean_old_image(path)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

    def _copy_virtio_drivers(self, virtio_floppy, cdrom_virtio):
        """
        Copy the virtio drivers from floppy or cdrom to install cdrom.

        1) If cdrom is available, mount the cdrom containing the virtio drivers
           and copy its contents to the root of the install cdrom
        2) If floppy is available while cdrom is not, mount the floppy and copy
           its contents to the root of the install cdrom
        """
        if cdrom_virtio:
            pwd = os.getcwd()
            mnt_pnt = tempfile.mkdtemp(prefix='cdrom_virtio_', dir=self.tmpdir)
            mount(cdrom_virtio, mnt_pnt, options='loop,ro', verbose=DEBUG)
            try:
                copytree(mnt_pnt, self.mount, ignore='*.vfd')
            finally:
                os.chdir(pwd)
                umount(None, mnt_pnt, verbose=DEBUG)
                os.rmdir(mnt_pnt)
        elif virtio_floppy:
            cmd = 'mcopy -s -o -n -i %s ::/* %s' % (virtio_floppy, self.mount)
            process.run(cmd, verbose=DEBUG)

    def setup_virtio_win2008(self, virtio_floppy, cdrom_virtio):
        """
        Setup the install cdrom with the virtio storage drivers, win2008 style.

        Win2008, Vista and 7 require people to point out the path to the drivers
        on the unattended file, so we just need to copy the drivers to the
        extra cdrom disk. Important to note that it's possible to specify
        drivers from a CDROM, so the floppy driver copy is optional.
        Process:

        1) Copy the virtio drivers on the virtio floppy/cdrom to the install
           cdrom if there is one available
        """
        if os.path.isfile(cdrom_virtio) or os.path.isfile(virtio_floppy):
            self._copy_virtio_drivers(virtio_floppy, cdrom_virtio)
        else:
            LOG.debug("No virtio floppy/cdrom present, not needed for this OS "
                      "anyway")

    @error_context.context_aware
    def close(self):
        error_context.context(
            "Creating unattended install CD image %s" % self.path)
        g_cmd = ('mkisofs -o %s -max-iso9660-filenames '
                 '-relaxed-filenames -D --input-charset iso8859-1 '
                 '%s' % (self.path, self.mount))
        process.run(g_cmd, verbose=DEBUG)

        os.chmod(self.path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP |
                 stat.S_IROTH | stat.S_IXOTH)
        cleanup(self.mount)
        LOG.debug("unattended install CD image %s successfully created",
                  self.path)


class CdromInstallDisk(Disk):

    """
    Represents a install CDROM disk that we can master according to our needs.
    """

    def __init__(self, path, tmpdir, source_cdrom, extra_params):
        self.mount = tempfile.mkdtemp(prefix='cdrom_unattended_', dir=tmpdir)
        self.path = path
        self.extra_params = extra_params
        self.source_cdrom = source_cdrom
        cleanup(path)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        cp_cmd = ('cp -r %s/isolinux/ %s/' % (source_cdrom, self.mount))
        listdir = os.listdir(self.source_cdrom)
        for i in listdir:
            if i == 'isolinux':
                continue
            os.symlink(os.path.join(self.source_cdrom, i),
                       os.path.join(self.mount, i))
        process.run(cp_cmd)

    def get_answer_file_path(self, filename):
        return os.path.join(self.mount, 'isolinux', filename)

    @error_context.context_aware
    def close(self):
        error_context.context(
            "Creating unattended install CD image %s" % self.path)
        if os.path.exists(os.path.join(self.mount, 'isolinux')):
            # bootable cdrom
            f = open(os.path.join(self.mount, 'isolinux', 'isolinux.cfg'), 'w')
            f.write('default /isolinux/vmlinuz append initrd=/isolinux/'
                    'initrd.img %s\n' % self.extra_params)
            f.close()
            boot = '-b isolinux/isolinux.bin'
        else:
            # Not a bootable CDROM, using -kernel instead (eg.: arm64)
            boot = ''

        m_cmd = ('mkisofs -o %s %s -c isolinux/boot.cat -no-emul-boot '
                 '-boot-load-size 4 -boot-info-table -f -R -J -V -T %s'
                 % (self.path, boot, self.mount))
        process.run(m_cmd)
        os.chmod(self.path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP |
                 stat.S_IROTH | stat.S_IXOTH)
        cleanup(self.mount)
        cleanup(self.source_cdrom)
        LOG.debug("unattended install CD image %s successfully created",
                  self.path)


class GuestFSModiDisk(object):

    """
    class of guest disk using guestfs lib to do some operation(like read/write)
    on guest disk:
    """

    def __init__(self, disk, backend='direct'):
        """
        :params disk: target disk image.
        :params backend: let libguestfs creates/connects to backend daemon
                         by starting qemu directly, or using libvirt to manage
                         an appliance, running User-Mode Linux, or connecting
                         to an already running daemon.
                         'direct', 'appliance', 'libvirt', 'libvirt:null',
                         'libvirt:URI', 'uml', 'unix:path'.
        """
        try:
            import guestfs
        except ImportError:
            from virttest.utils_package import package_install
            if not package_install("python*-libguestfs"):
                raise exceptions.TestSkipError('We need python-libguestfs (or '
                                               'the equivalent for your '
                                               'distro) for this particular '
                                               'feature (modifying guest '
                                               'files with libguestfs)')
            try:
                import guestfs
            except ImportError:
                raise exceptions.TestError("Couldn't import guestfs")

        self.g = guestfs.GuestFS()
        self.disk = disk
        self.g.add_drive(disk)
        self.g.set_backend(backend)
        libvirtd = SpecificServiceManager("libvirtd")
        libvirtd_status = libvirtd.status()
        if libvirtd_status is None:
            raise exceptions.TestError('libvirtd: service not found')
        if (not libvirtd_status) and (not libvirtd.start()):
            raise exceptions.TestError('libvirtd: failed to start')
        LOG.debug("Launch the disk %s, wait..." % self.disk)
        self.g.launch()

    def os_inspects(self):
        self.roots = self.g.inspect_os()
        if self.roots:
            return self.roots
        else:
            return None

    def mounts(self):
        return self.g.mounts()

    def mount_all(self):
        def compare(a, b):
            if len(a[0]) > len(b[0]):
                return 1
            elif len(a[0]) == len(b[0]):
                return 0
            else:
                return -1

        roots = self.os_inspects()
        if roots:
            for root in roots:
                mps = self.g.inspect_get_mountpoints(root)
                mps.sort(key=cmp_to_key(compare))
                for mp_dev in mps:
                    try:
                        msg = "Mount dev '%s' partitions '%s' to '%s'"
                        LOG.info(msg % (root, mp_dev[1], mp_dev[0]))
                        self.g.mount(mp_dev[1], mp_dev[0])
                    except RuntimeError as err_msg:
                        LOG.info("%s (ignored)" % err_msg)
        else:
            raise exceptions.TestError(
                "inspect_vm: no operating systems found")

    def umount_all(self):
        LOG.debug("Umount all device partitions")
        if self.mounts():
            self.g.umount_all()

    def read_file(self, file_name):
        """
        read file from the guest disk, return the content of the file

        :param file_name: the file you want to read.
        """

        try:
            self.mount_all()
            o = self.g.cat(file_name)
            if o:
                return o
            else:
                err_msg = "Can't read file '%s', check is it exist?"
                raise exceptions.TestError(err_msg % file_name)
        finally:
            self.umount_all()

    def write_to_image_file(self, file_name, content, w_append=False):
        """
        Write content to the file on the guest disk.

        When using this method all the original content will be overriding.
        if you don't hope your original data be override set ``w_append=True``.

        :param file_name: the file you want to write
        :param content: the content you want to write.
        :param w_append: append the content or override
        """

        try:
            try:
                self.mount_all()
                if w_append:
                    self.g.write_append(file_name, content)
                else:
                    self.g.write(file_name, content)
            except Exception:
                raise exceptions.TestError("write '%s' to file '%s' error!"
                                           % (content, file_name))
        finally:
            self.umount_all()

    def replace_image_file_content(self, file_name, find_con, rep_con):
        """
        replace file content matches in the file with rep_con.
        support using Regular expression

        :param file_name: the file you want to replace
        :param find_con: the original content you want to replace.
        :param rep_con: the replace content you want.
        """

        try:
            self.mount_all()
            file_content = self.g.cat(file_name)
            if file_content:
                file_content_after_replace = re.sub(find_con, rep_con,
                                                    file_content)
                if file_content != file_content_after_replace:
                    self.g.write(file_name, file_content_after_replace)
            else:
                err_msg = "Can't read file '%s', check is it exist?"
                raise exceptions.TestError(err_msg % file_name)
        finally:
            self.umount_all()

    def close(self):
        """
        Explicitly close the guestfs handle.
        """
        if self.g:
            self.g.close()
