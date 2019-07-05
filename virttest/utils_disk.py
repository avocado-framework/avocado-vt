"""
Virtualization test - Virtual disk related utility functions

:copyright: Red Hat Inc.
"""
import os
import glob
import shutil
import stat
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
from avocado.utils.service import SpecificServiceManager
from avocado.utils import path as utils_path

from virttest import error_context
from virttest import utils_numeric
from virttest import utils_misc
from virttest.compat_52lts import decode_to_text
from virttest.compat_52lts import results_stdout_52lts

PARTITION_TABLE_TYPE_MBR = "msdos"
PARTITION_TABLE_TYPE_GPT = "gpt"
PARTITION_TYPE_PRIMARY = "primary"
PARTITION_TYPE_EXTENDED = "extended"
PARTITION_TYPE_LOGICAL = "logical"

# Whether to print all shell commands called
DEBUG = False


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
    :param options: mount options should be seperated by ","
    :param session: check within the session if given

    :return: True if mounted, else return False
    """
    mount_str = "%s %s %s" % (src, dst, fstype)
    mount_str = mount_str.replace('None', '').strip()
    mount_list_cmd = 'cat /proc/mounts'

    if session:
        mount_result = session.cmd_output_safe(mount_list_cmd)
    else:
        mount_result = decode_to_text(process.system_output(mount_list_cmd, shell=True))
    if verbose:
        logging.debug("/proc/mounts contents:\n%s", mount_result)

    for result in mount_result.splitlines():
        if mount_str in result:
            if options:
                options = options.split(",")
                options_result = result.split()[3].split(",")
                for op in options:
                    if op not in options_result:
                        if verbose:
                            logging.info("%s is not mounted with given"
                                         " option %s", src, op)
                        return False
            if verbose:
                logging.info("%s is mounted", src)
            return True
    if verbose:
        logging.info("%s is not mounted", src)
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
            logging.error("%s is not available/installed for fuser", package)
        fuser_cmd = "fuser -km %s" % dst
        umount_cmd = "umount %s" % dst
        if session:
            session.cmd_output_safe(fuser_cmd)
            return session.cmd_status(umount_cmd, safe=True) == 0
        process.system(fuser_cmd, ignore_status=True, verbose=True, shell=True)
        return process.system(umount_cmd, ignore_status=True, verbose=True) == 0
    return True


def get_dev_major_minor(dev):
    """
    Get the major and minor numbers of the device
    @return: Tuple(major, minor) numbers of the device
    """
    try:
        rdev = os.stat(dev).st_rdev
        return (os.major(rdev), os.minor(rdev))
    except IOError as details:
        raise exceptions.TestError("Fail to get major and minor numbers of the "
                                   "device %s:\n%s" % (dev, details))


def get_free_disk(session, mount):
    """
    Get FreeSpace for given mount point.

    :param session: shell Object.
    :param mount: mount point(eg. C:, /mnt)

    :return string: freespace M-bytes
    """
    if re.match(r"[a-zA-Z]:", mount):
        cmd = "wmic logicaldisk where \"DeviceID='%s'\" " % mount
        cmd += "get FreeSpace"
        output = session.cmd_output(cmd)
        free = "%sK" % re.findall(r"\d+", output)[0]
    else:
        cmd = "df -h %s" % mount
        output = session.cmd_output(cmd)
        free = re.findall(r"\b([\d.]+[BKMGPETZ])\b",
                          output, re.M | re.I)[2]
    free = float(utils_misc.normalize_data_size(free, order_magnitude="M"))
    return int(free)


def get_win_disk_vol(session, condition="VolumeName='WIN_UTILS'"):
    """
    Getting logicaldisk drive letter in windows guest.

    :param session: session Object.
    :param condition: supported condition via cmd "wmic logicaldisk list".

    :return: volume ID.
    """
    cmd = "wmic logicaldisk where (%s) get DeviceID" % condition
    output = session.cmd(cmd, timeout=120)
    device = re.search(r'(\w):', output, re.M)
    if not device:
        return ""
    return device.group(1)


def get_winutils_vol(session, label="WIN_UTILS"):
    """
    Return Volume ID of winutils CDROM ISO file should be create via command
    ``mkisofs -V $label -o winutils.iso``.

    :param session: session Object.
    :param label: volume label of WIN_UTILS.iso.

    :return: volume ID.
    """
    return get_win_disk_vol(session, condition="VolumeName='%s'" % label)


def check_qemu_image_lock_support():
    """
    Check qemu-img whether supporting image lock or not
    :return: The boolean of checking result
    """
    cmd = "qemu-img"
    binary_path = utils_path.find_command(cmd)
    cmd_result = process.run(binary_path + ' -h', ignore_status=True,
                             shell=True, verbose=False)
    return b'-U' in cmd_result.stdout


def get_linux_drive_path(session, did, timeout=120):
    """
    Get drive path in guest by drive serial or wwn

    :param session: session object to guest.
    :param did: drive serial or wwn.
    :return String: drive path
    """
    cmd = 'for dev_path in `ls -d /sys/block/*`; do '
    cmd += 'echo `udevadm info -q property -p $dev_path`; done'
    status, output = session.cmd_status_output(cmd, timeout=timeout)
    if status != 0:
        logging.error("Can not get drive infomation:\n%s" % output)
        return ""
    p = r"DEVNAME=([^\s]+)\s.*(?:ID_SERIAL|ID_SERIAL_SHORT|ID_WWN)=%s" % did
    dev = re.search(p, output, re.M)
    if dev:
        return dev.groups()[0]
    logging.error("Can not get drive path by id '%s', "
                  "command output:\n%s" % (did, output))
    return ""


def get_image_info(image_file):
    """
    Get image information and put it into a dict. Image information like this:

    ::

        *******************************
        image: /path/vm1_6.3.img
        file format: raw
        virtual size: 10G (10737418240 bytes)
        disk size: 888M
        ....
        image: /path/vm2_6.3.img
        file format: raw
        virtual size: 1.0M (1024000 bytes)
        disk size: 196M
        ....
        image: n3.qcow2
        file format: qcow2
        virtual size: 1.0G (1073741824 bytes)
        disk size: 260K
        cluster_size: 512
        Format specific information:
            compat: 1.1
            lazy refcounts: false
            refcount bits: 16
            corrupt: false
        ....
        *******************************

    And the image info dict will be like this

    ::

        image_info_dict = {'format':'raw',
                           'vsize' : '10737418240',
                           'dsize' : '931135488',
                           'csize' : '65536'}
    """
    try:
        cmd = "qemu-img info %s" % image_file
        if check_qemu_image_lock_support():
            # Currently the qemu lock is introduced in qemu-kvm-rhev/ma,
            # The " -U" is to avoid the qemu lock.
            cmd += " -U"
        image_info = decode_to_text(process.system_output(cmd, ignore_status=False)).strip()
        image_info_dict = {}
        vsize = None
        if image_info:
            for line in image_info.splitlines():
                if line.find("file format") != -1:
                    image_info_dict['format'] = line.split(':')[-1].strip()
                elif line.find("virtual size") != -1 and vsize is None:
                    # Use the value in (xxxxxx bytes) since it's the more
                    # realistic value. For a "1000k" disk, qemu-img will
                    # show 1.0M and 1024000 bytes. The 1.0M will translate
                    # into 1048576 bytes which isn't necessarily correct
                    vsize = line.split("(")[-1].strip().split(" ")[0]
                    image_info_dict['vsize'] = int(vsize)
                elif line.find("disk size") != -1:
                    dsize = line.split(':')[-1].strip()
                    image_info_dict['dsize'] = int(float(
                        utils_misc.normalize_data_size(dsize, order_magnitude="B", factor=1024)))
                elif line.find("cluster_size") != -1:
                    csize = line.split(':')[-1].strip()
                    image_info_dict['csize'] = int(csize)
                elif line.find("compat") != -1:
                    compat = line.split(':')[-1].strip()
                    image_info_dict['compat'] = compat
                elif line.find("lazy refcounts") != -1:
                    lazy_refcounts = line.split(':')[-1].strip()
                    image_info_dict['lcounts'] = lazy_refcounts
        return image_info_dict
    except (KeyError, IndexError, process.CmdError) as detail:
        raise exceptions.TestError("Fail to get information of %s:\n%s" %
                                   (image_file, detail))


def get_windows_drive_letters(session):
    """
    Get drive letters has been assigned

    :param session: session object to guest
    :return list: letters has been assigned
    """
    list_letters_cmd = "fsutil fsinfo drives"
    drive_letters = re.findall(
        r'(\w+):\\', session.cmd_output(list_letters_cmd), re.M)

    return drive_letters


def list_linux_guest_disks(session, partition=False):
    """
    List all disks OR disks with no partition in linux guest.

    :param session: session object to guest
    :param partition: if true, list all disks; otherwise,
                      list only disks with no partition.
    :return: the disks set.
    """
    cmd = "ls /dev/[vhs]d*"
    if not partition:
        cmd = "%s | grep -v [0-9]$" % cmd
    status, output = session.cmd_status_output(cmd)
    if status != 0:
        raise exceptions.TestFail("Get disks failed with output %s" % output)
    return set(output.split())


def get_all_disks_did(session, partition=False):
    """
    Get all disks did lists in a linux guest, each disk list
    include disk kname, serial and wwn.

    :param session: session object to guest.
    :param partition: if true, get all disks did lists; otherwise,
                      get the ones with no partition.
    :return: a dict with all disks did lists each include disk
             kname, serial and wwn.
    """
    disks = list_linux_guest_disks(session, partition)
    logging.debug("Disks detail: %s" % disks)
    all_disks_did = {}
    for line in disks:
        kname = line.split('/')[2]
        get_disk_info_cmd = "udevadm info -q property -p /sys/block/%s" % kname
        output = session.cmd_output_safe(get_disk_info_cmd)
        re_str = r"(?<=DEVNAME=/dev/)(.*)|(?<=ID_SERIAL=)(.*)|"
        re_str += "(?<=ID_SERIAL_SHORT=)(.*)|(?<=ID_WWN=)(.*)"
        did_list_group = re.finditer(re_str, output, re.M)
        did_list = [match.group() for match in did_list_group if match]
        all_disks_did[kname] = did_list

    return all_disks_did


def format_windows_disk(session, did, mountpoint=None, size=None,
                        fstype="ntfs", force=False):
    """
    Create a partition on disk in windows guest and format it.

    :param session: session object to guest.
    :param did: disk index which show in 'diskpart list disk'.
    :param mountpoint: mount point for the disk.
    :param size: partition size.
    :param fstype: filesystem type for the disk.
    :return Boolean: disk usable or not.
    """
    list_disk_cmd = "echo list disk > disk && "
    list_disk_cmd += "echo exit >> disk && diskpart /s disk"
    disks = session.cmd_output(list_disk_cmd, timeout=120)

    if size:
        size = int(float(utils_misc.normalize_data_size(size, order_magnitude="M")))

    for disk in disks.splitlines():
        if re.search(r"DISK %s" % did, disk, re.I | re.M):
            cmd_header = 'echo list disk > disk &&'
            cmd_header += 'echo select disk %s >> disk &&' % did
            cmd_footer = '&& echo exit>> disk && diskpart /s disk'
            cmd_footer += '&& del /f disk'
            detail_cmd = 'echo detail disk >> disk'
            detail_cmd = ' '.join([cmd_header, detail_cmd, cmd_footer])
            logging.debug("Detail for 'Disk%s'" % did)
            details = session.cmd_output(detail_cmd)

            pattern = "DISK %s.*Offline" % did
            if re.search(pattern, details, re.I | re.M):
                online_cmd = 'echo online disk>> disk'
                online_cmd = ' '.join([cmd_header, online_cmd, cmd_footer])
                logging.info("Online 'Disk%s'" % did)
                session.cmd(online_cmd)

            if re.search("Read.*Yes", details, re.I | re.M):
                set_rw_cmd = 'echo attributes disk clear readonly>> disk'
                set_rw_cmd = ' '.join([cmd_header, set_rw_cmd, cmd_footer])
                logging.info("Clear readonly bit on 'Disk%s'" % did)
                session.cmd(set_rw_cmd)

            if re.search(r"Volume.*%s" % fstype, details, re.I | re.M) and not force:
                logging.info("Disk%s has been formated, cancel format" % did)
                continue

            if not size:
                mkpart_cmd = 'echo create partition primary >> disk'
            else:
                mkpart_cmd = 'echo create partition primary size=%s '
                mkpart_cmd += '>> disk'
                mkpart_cmd = mkpart_cmd % size
            mkpart_cmd = ' '.join([cmd_header, mkpart_cmd, cmd_footer])
            logging.info("Create partition on 'Disk%s'" % did)
            session.cmd(mkpart_cmd)
            logging.info("Format the 'Disk%s' to %s" % (did, fstype))
            format_cmd = 'echo list partition >> disk && '
            format_cmd += 'echo select partition 1 >> disk && '
            if not mountpoint:
                format_cmd += 'echo assign >> disk && '
            else:
                format_cmd += 'echo assign letter=%s >> disk && ' % mountpoint
            format_cmd += 'echo format fs=%s quick >> disk ' % fstype
            format_cmd = ' '.join([cmd_header, format_cmd, cmd_footer])
            session.cmd(format_cmd, timeout=300)

            return True

    return False


def format_linux_disk(session, did, all_disks_did, partition=False,
                      mountpoint=None, size=None, fstype="ext3"):
    """
    Create a partition on disk in linux guest and format and mount it.

    :param session: session object to guest.
    :param did: disk kname, serial or wwn.
    :param all_disks_did: all disks did lists each include
                          disk kname, serial and wwn.
    :param partition: if true, can format all disks; otherwise,
                      only format the ones with no partition originally.
    :param mountpoint: mount point for the disk.
    :param size: partition size.
    :param fstype: filesystem type for the disk.
    :return Boolean: disk usable or not.
    """
    disks = list_linux_guest_disks(session, partition)
    logging.debug("Disks detail: %s" % disks)
    for line in disks:
        kname = line.split('/')[2]
        did_list = all_disks_did[kname]
        if did not in did_list:
            # Continue to search target disk
            continue
        if not size:
            size_output = session.cmd_output_safe("lsblk -oKNAME,SIZE|grep %s"
                                                  % kname)
            size = size_output.splitlines()[0].split()[1]
        all_disks_before = list_linux_guest_disks(session, True)
        devname = line
        logging.info("Create partition on disk '%s'" % devname)
        mkpart_cmd = "parted -s %s mklabel gpt mkpart "
        mkpart_cmd += "primary 0 %s"
        mkpart_cmd = mkpart_cmd % (devname, size)
        session.cmd_output_safe(mkpart_cmd)
        session.cmd_output_safe("partprobe %s" % devname)
        all_disks_after = list_linux_guest_disks(session, True)
        partname = (all_disks_after - all_disks_before).pop()
        logging.info("Format partition to '%s'" % fstype)
        format_cmd = "yes|mkfs -t %s %s" % (fstype, partname)
        session.cmd_output_safe(format_cmd)
        if not mountpoint:
            session.cmd_output_safe("mkdir /mnt/%s" % kname)
            mountpoint = os.path.join("/mnt", kname)
        logging.info("Mount the disk to '%s'" % mountpoint)
        mount_cmd = "mount -t %s %s %s" % (fstype, partname, mountpoint)
        session.cmd_output_safe(mount_cmd)
        return True

    return False


def format_guest_disk(session, did, all_disks_did, ostype, partition=False,
                      mountpoint=None, size=None, fstype=None):
    """
    Create a partition on disk in guest and format and mount it.

    :param session: session object to guest.
    :param did: disk ID in guest.
    :param all_disks_did: a dict contains all disks did lists each
                          include disk kname, serial and wwn for linux guest.
    :param ostype: guest os type 'windows' or 'linux'.
    :param partition: if true, can format all disks; otherwise,
                      only format the ones with no partition originally.
    :param mountpoint: mount point for the disk.
    :param size: partition size.
    :param fstype: filesystem type for the disk; when it's the default None,
                   it will use the default one for corresponding ostype guest
    :return Boolean: disk usable or not.
    """
    default_fstype = "ntfs" if (ostype == "windows") else "ext3"
    fstype = fstype or default_fstype
    if ostype == "windows":
        return format_windows_disk(session, did, mountpoint, size, fstype)
    return format_linux_disk(session, did, all_disks_did, partition,
                             mountpoint, size, fstype)


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
    list_disk_cmd = "lsblk -o KNAME,SIZE,TYPE,SERIAL,WWN"
    get_disk_name_cmd = "lsblk -no pkname /dev/%s"
    output = session.cmd_output(list_disk_cmd)
    devs = output.splitlines()
    disks_dict = {}
    part_dict = {}
    for dev in devs:
        dev = dev.split()
        if "disk" in dev:
            disks_dict[dev[0]] = dev
        if "part" in dev:
            part_dict[dev[0]] = dev
    if partition:
        disks_dict = dict(disks_dict, **part_dict)
    else:
        for part in part_dict.keys():
            output = session.cmd_output(get_disk_name_cmd % part)
            disk = output.splitlines()[0].strip()
            if disk in disks_dict.keys():
                disks_dict.pop(disk)
    return disks_dict


def get_windows_disks_index(session, image_size):
    """
    Get all disks index which show in 'diskpart list disk'.
    except for system disk.
    in diskpart: if disk size < 8GB: it displays as MB
                 else: it displays as GB

    :param session: session object to guest.
    :param image_size: image size. e.g. 40M
    :return: a list with all disks index except for system disk.
    """
    disk = "disk_" + ''.join(random.sample(string.ascii_letters + string.digits, 4))
    disk_indexs = []
    list_disk_cmd = "echo list disk > " + disk
    list_disk_cmd += " && echo exit >> " + disk
    list_disk_cmd += " && diskpart /s " + disk
    list_disk_cmd += " && del /f " + disk
    disks = session.cmd_output(list_disk_cmd)
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
        logging.info("Detail for 'Disk%s'" % did)
        details = session.cmd_output(detail_cmd % did)
        if re.search("Read.*Yes", details, re.I | re.M):
            logging.info("Clear readonly bit on 'Disk%s'" % did)
            status, output = session.cmd_status_output(set_rw_cmd % did,
                                                       timeout=timeout)
            if status != 0:
                logging.error("Can not clear readonly bit: %s" % output)
                return False
        if re.search("Status.*Offline", details, re.I | re.M):
            logging.info("Online 'Disk%s'" % did)
            status, output = session.cmd_status_output(online_cmd % did,
                                                       timeout=timeout)
            if status != 0:
                logging.error("Can not online disk: %s" % output)
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
    """
    size = utils_numeric.normalize_data_size(size, order_magnitude="M") + "M"
    start = utils_numeric.normalize_data_size(start, order_magnitude="M") + "M"
    end = str(float(start[:-1]) + float(size[:-1])) + size[-1]
    partprobe_cmd = "partprobe /dev/%s" % did
    mkpart_cmd = 'parted -s "%s" mkpart %s %s %s'
    mkpart_cmd %= ("/dev/%s" % did, part_type, start, end)
    session.cmd(mkpart_cmd)
    session.cmd(partprobe_cmd, timeout=timeout)


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
    """
    size = utils_numeric.normalize_data_size(size, order_magnitude="M")
    start = utils_numeric.normalize_data_size(start, order_magnitude="M")
    size = int(float(size) - float(start))
    mkpart_cmd = " echo create partition %s size=%s"
    mkpart_cmd = _wrap_windows_cmd(mkpart_cmd)
    session.cmd(mkpart_cmd % (did, part_type, size), timeout=timeout)


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
    """
    if ostype == "windows":
        create_partition_windows(session, did, size, start, part_type, timeout)
    else:
        create_partition_linux(session, did, size, start, part_type, timeout)


def delete_partition_linux(session, partition_name, timeout=360):
    """
    remove single partition for one disk.

    :param session: session object to guest.
    :param partition_name: partition name. e.g. sdb1
    :param timeout: Timeout for cmd execution in seconds.
    """
    get_kname_cmd = "lsblk -no pkname /dev/%s"
    kname = session.cmd_output(get_kname_cmd % partition_name)
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
        logging.info("no partition to clean on %s" % did)
    else:
        partition_numbers = partition_numbers.splitlines()
        for number in partition_numbers:
            logging.info("remove partition %s on %s" % (number, did))
            session.cmd(rm_cmd % (did, number))
        session.cmd("partprobe /dev/%s" % did, timeout=timeout)


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


def create_filesystem_windows(session, partition_name, fstype, timeout=360):
    """
    create file system in windows guest.

    :param session: session object to guest.
    :param partition_name: partition name that to be formatted. e.g. D
    :param fstype: file system type for the disk.
    :param timeout: Timeout for cmd execution in seconds.
    """
    disk = "disk_" + ''.join(random.sample(string.ascii_letters + string.digits, 4))
    format_cmd = "echo select volume %s > " + disk
    format_cmd += " && echo format fs=%s quick >> " + disk
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


def set_drive_letter(session, did, partition_no=1):
    """
    set drive letter for partition in windows guest.

    :param session: session object to guest.
    :param did: disk index
    :param partition_no: partition number
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
                                 timeout=360):
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
        create_filesystem_windows(session, mountpoint[i], fstype, timeout)
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
        pre_partition = get_linux_disks(session, partition=True).keys()
        if i == 0:
            create_partition_linux(session, did, str(partition_size) + size[-1],
                                   str(start) + size[-1], timeout=timeout)
        else:
            if part_type == PARTITION_TYPE_EXTENDED:
                create_partition_linux(session, did, str(extended_size) + size[-1],
                                       str(start) + size[-1], part_type, timeout)
                pre_partition = get_linux_disks(session, partition=True).keys()
                part_type = PARTITION_TYPE_LOGICAL
                create_partition_linux(session, did, str(partition_size) + size[-1],
                                       str(start) + size[-1], part_type, timeout)
            else:
                create_partition_linux(session, did, str(partition_size) + size[-1],
                                       str(start) + size[-1], part_type, timeout)
        start += partition_size
        post_partition = get_linux_disks(session, partition=True).keys()
        new_partition = list(set(post_partition) - set(pre_partition))[0]
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
        parts_out = results_stdout_52lts(process.run(parts_cmd))
    parts = []
    if parts_out:
        for line in parts_out.rsplit("\n"):
            if line.startswith("major") or line == "":
                continue
            parts_line = line.rsplit()
            if len(parts_line) == 4:
                parts.append(parts_line[3])
    logging.debug("Find parts: %s", parts)
    return parts


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
            logging.debug("Disk %s has serial %s", disk, serial_str)
            return disk


class Disk(object):

    """
    Abstract class for Disk objects, with the common methods implemented.
    """

    def __init__(self):
        self.path = None

    def get_answer_file_path(self, filename):
        return os.path.join(self.mount, filename)

    def copy_to(self, src):
        logging.debug("Copying %s to disk image mount", src)
        dst = os.path.join(self.mount, os.path.basename(src))
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        elif os.path.isfile(src):
            shutil.copyfile(src, dst)

    def close(self):
        os.chmod(self.path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP |
                 stat.S_IROTH | stat.S_IXOTH)
        cleanup(self.mount)
        logging.debug("Disk %s successfully set", self.path)


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
            logging.error("Error during floppy initialization: %s" % e)
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
        logging.debug("Copying %s to floppy image", src)
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
            logging.debug(
                "No virtio floppy present, not needed for this OS anyway")


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
        2) If floppy is availabe while cdrom is not, mount the floppy and copy
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
            logging.debug(
                "No virtio floppy/cdrom present, not needed for this OS anyway")

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
        logging.debug("unattended install CD image %s successfully created",
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
        logging.debug("unattended install CD image %s successfully created",
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
        logging.debug("Launch the disk %s, wait..." % self.disk)
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
                        logging.info(msg % (root, mp_dev[1], mp_dev[0]))
                        self.g.mount(mp_dev[1], mp_dev[0])
                    except RuntimeError as err_msg:
                        logging.info("%s (ignored)" % err_msg)
        else:
            raise exceptions.TestError(
                "inspect_vm: no operating systems found")

    def umount_all(self):
        logging.debug("Umount all device partitions")
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
