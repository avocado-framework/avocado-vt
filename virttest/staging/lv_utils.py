"""
Utilities to create logical volumes or take snapshots of existing ones.

:author: Plamen Dimitrov
:copyright: Intra2net AG 2012
:license: GPL v2

:param vg_name: Name of the volume group.
:param lv_name: Name of the logical volume.
:param lv_size: Size of the logical volume as string in the form "#G"
                (for example 30G).
:param lv_snapshot_name: Name of the snapshot with origin the logical
                         volume.
:param lv_snapshot_size: Size of the snapshot with origin the logical
                         volume also as "#G".
:param ramdisk_vg_size: Size of the ramdisk virtual group.
:param ramdisk_basedir: Base directory for the ramdisk sparse file.
:param ramdisk_sparse_filename: Name of the ramdisk sparse file.

Sample ramdisk params:

::

    ramdisk_vg_size = "40000"
    ramdisk_basedir = "/tmp"
    ramdisk_sparse_filename = "virtual_hdd"

Sample general params:

::

    vg_name='autotest_vg',
    lv_name='autotest_lv',
    lv_size='1G',
    lv_snapshot_name='autotest_sn',
    lv_snapshot_size='1G'

The ramdisk volume group size is in MB.
"""

import logging
import re
import os
import shutil
import time

from avocado.core import exceptions
from avocado.utils import process

from virttest import error_context

LOG = logging.getLogger('avocado.' + __name__)


@error_context.context_aware
def vg_ramdisk(vg_name, ramdisk_vg_size,
               ramdisk_basedir, ramdisk_sparse_filename):
    """
    Create vg on top of ram memory to speed up lv performance.
    """
    error_context.context("Creating virtual group on top of ram memory",
                          LOG.info)
    vg_size = ramdisk_vg_size
    vg_ramdisk_dir = os.path.join(ramdisk_basedir, vg_name)
    ramdisk_filename = os.path.join(vg_ramdisk_dir,
                                    ramdisk_sparse_filename)

    vg_ramdisk_cleanup(ramdisk_filename,
                       vg_ramdisk_dir, vg_name, "")
    result = ""
    if not os.path.exists(vg_ramdisk_dir):
        os.mkdir(vg_ramdisk_dir)
    try:
        LOG.info("Mounting tmpfs")
        result = process.run("mount -t tmpfs tmpfs " + vg_ramdisk_dir)

        LOG.info("Converting and copying /dev/zero")
        cmd = ("dd if=/dev/zero of=" + ramdisk_filename +
               " bs=1M count=1 seek=" + vg_size)
        result = process.run(cmd, verbose=True)

        LOG.info("Finding free loop device")
        result = process.run("losetup --find", verbose=True)
    except process.CmdError as ex:
        LOG.error(ex)
        vg_ramdisk_cleanup(ramdisk_filename,
                           vg_ramdisk_dir, vg_name, "")
        raise ex

    loop_device = result.stdout_text.rstrip()

    try:
        LOG.info("Creating loop device")
        result = process.run("losetup " + loop_device + " " + ramdisk_filename)
        LOG.info("Creating physical volume %s", loop_device)
        result = process.run("pvcreate " + loop_device)
        LOG.info("Creating volume group %s", vg_name)
        result = process.run("vgcreate " + vg_name + " " + loop_device)
    except process.CmdError as ex:
        LOG.error(ex)
        vg_ramdisk_cleanup(ramdisk_filename, vg_ramdisk_dir, vg_name,
                           loop_device)
        raise ex

    LOG.info(result.stdout_text.rstrip())


def vg_ramdisk_cleanup(ramdisk_filename, vg_ramdisk_dir,
                       vg_name, loop_device):
    """
    Inline cleanup function in case of test error.
    """
    result = process.run("vgremove " + vg_name, ignore_status=True)
    if result.exit_status == 0:
        LOG.info(result.stdout_text.rstrip())
    else:
        LOG.debug("%s -> %s", result.command, result.stderr_text)

    result = process.run("pvremove " + loop_device, ignore_status=True)
    if result.exit_status == 0:
        LOG.info(result.stdout_text.rstrip())
    else:
        LOG.debug("%s -> %s", result.command, result.stderr_text)

    for _ in range(10):
        time.sleep(0.1)
        result = process.run("losetup -d " + loop_device, ignore_status=True)
        if b"resource busy" not in result.stderr:
            if result.exit_status != 0:
                LOG.debug("%s -> %s", result.command, result.stderr_text)
            else:
                LOG.info("Loop device %s deleted", loop_device)
            break

    if os.path.exists(ramdisk_filename):
        os.unlink(ramdisk_filename)
        LOG.info("Ramdisk filename %s deleted", ramdisk_filename)

    process.run("umount " + vg_ramdisk_dir, ignore_status=True)
    if result.exit_status == 0:
        if loop_device != "":
            LOG.info("Loop device %s unmounted", loop_device)
    else:
        LOG.debug("%s -> %s", result.command, result.stderr_text)

    if os.path.exists(vg_ramdisk_dir):
        try:
            shutil.rmtree(vg_ramdisk_dir)
            LOG.info("Ramdisk directory %s deleted", vg_ramdisk_dir)
        except OSError:
            pass


def vg_check(vg_name):
    """
    Check whether provided volume group exists.
    """
    cmd = "vgdisplay " + vg_name
    try:
        process.run(cmd)
        LOG.debug("Provided volume group exists: " + vg_name)
        return True
    except process.CmdError:
        return False


def vg_list():
    """
    List available volume groups.
    """
    cmd = "vgs --all"
    vgroups = {}
    result = process.run(cmd)

    lines = result.stdout_text.strip().splitlines()
    if len(lines) > 1:
        columns = lines[0].split()
        lines = lines[1:]
    else:
        return vgroups

    for line in lines:
        details = line.split()
        details_dict = {}
        index = 0
        for column in columns:
            if re.search("VG", column):
                vg_name = details[index]
            else:
                details_dict[column] = details[index]
            index += 1
        vgroups[vg_name] = details_dict
    return vgroups


@error_context.context_aware
def vg_create(vg_name, pv_list):
    """
    Create a volume group by using the block special devices
    """
    error_context.context(
        "Creating volume group '%s' by using '%s'" %
        (vg_name, pv_list), LOG.info)

    if vg_check(vg_name):
        raise exceptions.TestError("Volume group '%s' already exist" % vg_name)
    # Update cached state before create VG
    cmd = "vgscan --cache"
    result = process.run(cmd, ignore_status=True)
    cmd = "vgcreate %s %s" % (vg_name, pv_list)
    result = process.run(cmd)
    LOG.info(result.stdout_text.rstrip())


@error_context.context_aware
def vg_remove(vg_name):
    """
    Remove a volume group.
    """
    error_context.context("Removing volume '%s'" % vg_name, LOG.info)

    if not vg_check(vg_name):
        raise exceptions.TestError(
            "Volume group '%s' could not be found" % vg_name)
    cmd = "vgremove -f %s" % vg_name
    result = process.run(cmd)
    LOG.info(result.stdout_text.rstrip())
    # Update cached state after remove VG
    cmd = "vgscan --cache"
    result = process.run(cmd, ignore_status=True)


def lv_check(vg_name, lv_name):
    """
    Check whether provided logical volume exists.
    """
    cmd = "lvdisplay"
    result = process.run(cmd, ignore_status=True)

    # unstable approach but currently works
    lvpattern = r"LV Path\s+/dev/" + vg_name + r"/" + lv_name + "\s+"
    match = re.search(lvpattern, result.stdout_text.rstrip())
    if match:
        LOG.debug("Provided logical volume exists: /dev/" +
                  vg_name + "/" + lv_name)
        return True
    else:
        return False


@error_context.context_aware
def lv_remove(vg_name, lv_name):
    """
    Remove a logical volume.
    """
    error_context.context("Removing volume /dev/%s/%s" %
                          (vg_name, lv_name), LOG.info)

    if not vg_check(vg_name):
        raise exceptions.TestError("Volume group could not be found")
    if not lv_check(vg_name, lv_name):
        raise exceptions.TestError("Logical volume could not be found")

    cmd = "lvremove -f " + vg_name + "/" + lv_name
    result = process.run(cmd)
    LOG.info(result.stdout_text.rstrip())


@error_context.context_aware
def lv_create(vg_name, lv_name, lv_size, force_flag=True):
    """
    Create a logical volume in a volume group.

    The volume group must already exist.
    """
    error_context.context("Creating original lv to take a snapshot from",
                          LOG.info)

    if not vg_check(vg_name):
        raise exceptions.TestError("Volume group could not be found")
    if lv_check(vg_name, lv_name) and not force_flag:
        raise exceptions.TestError("Logical volume already exists")
    elif lv_check(vg_name, lv_name) and force_flag:
        lv_remove(vg_name, lv_name)

    cmd = ("lvcreate --size " + lv_size + " --name " + lv_name + " " + vg_name)
    result = process.run(cmd)
    LOG.info(result.stdout_text.rstrip())


@error_context.context_aware
def lv_take_snapshot(vg_name, lv_name,
                     lv_snapshot_name, lv_snapshot_size):
    """
    Take a snapshot of the original logical volume.
    """
    error_context.context("Taking snapshot from original logical volume",
                          LOG.info)

    if not vg_check(vg_name):
        raise exceptions.TestError("Volume group could not be found")
    if lv_check(vg_name, lv_snapshot_name):
        raise exceptions.TestError("Snapshot already exists")
    if not lv_check(vg_name, lv_name):
        raise exceptions.TestError("Snapshot's origin could not be found")

    cmd = ("lvcreate --size " + lv_snapshot_size + " --snapshot " +
           " --name " + lv_snapshot_name + " /dev/" + vg_name + "/" + lv_name)
    try:
        result = process.run(cmd)
    except process.CmdError as ex:
        if ('Logical volume "%s" already exists in volume group "%s"' %
            (lv_snapshot_name, vg_name) in ex.result.stderr_text and
            re.search(re.escape(lv_snapshot_name + " [active]"),
                      process.run("lvdisplay").stdout_text)):
            # the above conditions detect if merge of snapshot was postponed
            LOG.warning(("Logical volume %s is still active! " +
                         "Attempting to deactivate..."), lv_name)
            lv_reactivate(vg_name, lv_name)
            result = process.run(cmd)
        else:
            raise ex
    LOG.info(result.stdout_text.rstrip())


@error_context.context_aware
def lv_revert(vg_name, lv_name, lv_snapshot_name):
    """
    Revert the origin to a snapshot.
    """
    error_context.context("Reverting original logical volume to snapshot",
                          LOG.info)
    try:
        if not vg_check(vg_name):
            raise exceptions.TestError("Volume group could not be found")
        if not lv_check(vg_name, lv_snapshot_name):
            raise exceptions.TestError("Snapshot could not be found")
        if (not lv_check(vg_name, lv_snapshot_name) and
                not lv_check(vg_name, lv_name)):
            raise exceptions.TestError(
                "Snapshot and its origin could not be found")
        if (lv_check(vg_name, lv_snapshot_name) and
                not lv_check(vg_name, lv_name)):
            raise exceptions.TestError("Snapshot origin could not be found")

        cmd = ("lvconvert --merge /dev/%s/%s" % (vg_name, lv_snapshot_name))
        result = process.run(cmd)
        if ("Merging of snapshot %s will start next activation." %
                lv_snapshot_name) in result.stdout_text:
            raise exceptions.TestError("The logical volume %s is still "
                                       "active" % lv_name)
        result = result.stdout_text.rstrip()

    except exceptions.TestError as ex:
        # detect if merge of snapshot was postponed
        # and attempt to reactivate the volume.
        ex_str = str(ex)
        if (('Snapshot could not be found' in ex_str and
             re.search(re.escape(lv_snapshot_name + " [active]"),
                       process.run("lvdisplay").stdout_text)) or
                ("The logical volume %s is still active" % lv_name) in ex_str):
            LOG.warning(("Logical volume %s is still active! " +
                         "Attempting to deactivate..."), lv_name)
            lv_reactivate(vg_name, lv_name)
            result = "Continuing after reactivation"
        elif 'Snapshot could not be found' in ex_str:
            LOG.error(ex)
            result = "Could not revert to snapshot"
        else:
            raise ex
    LOG.info(result)


@error_context.context_aware
def lv_revert_with_snapshot(vg_name, lv_name,
                            lv_snapshot_name, lv_snapshot_size):
    """
    Perform logical volume merge with snapshot and take a new snapshot.

    """
    error_context.context("Reverting to snapshot and taking a new one",
                          LOG.info)

    lv_revert(vg_name, lv_name, lv_snapshot_name)
    lv_take_snapshot(vg_name, lv_name, lv_snapshot_name, lv_snapshot_size)


@error_context.context_aware
def lv_reactivate(vg_name, lv_name, timeout=10):
    """
    In case of unclean shutdowns some of the lvs is still active and merging
    is postponed. Use this function to attempt to deactivate and reactivate
    all of them to cause the merge to happen.
    """
    try:
        process.run("lvchange -an /dev/%s/%s" % (vg_name, lv_name))
        time.sleep(timeout)
        process.run("lvchange -ay /dev/%s/%s" % (vg_name, lv_name))
        time.sleep(timeout)
    except process.CmdError:
        LOG.error(("Failed to reactivate %s - please, " +
                   "nuke the process that uses it first."), lv_name)
        raise exceptions.TestError(
            "The logical volume %s is still active" % lv_name)


def gen_lvmap_mpath(session=None):
    """
    Return the name mapping between logical volume and device
    mapper multipathed device.
    :param session: When session is given, it means VM session
                    Otherwise default value means it work for host
    :return: None or a dict like:
            {"lv_name": dm_name}
    """
    names_map = None
    cmd = ("lvdisplay|awk '/LV Name/{n=$3} "
           "/Block device/{d=$3; sub(\".*:\", \"dm-\", d); print n,d;}'")

    if session:
        output = session.cmd_output(cmd).strip()
    else:
        output = process.run(cmd, shell=True).stdout_text
    lines = output.splitlines()
    if len(lines) >= 1:
        names_map = {}
        for line in lines:
            values = line.split()
            lv_name, mpath_name = values[0], values[1]
            names_map.update({lv_name: mpath_name})
    return names_map


def get_vg_mapped_blk_target(vg_name, session=None):
    """
    Get vg mapped blk target with pvs Command
    :param vg_name: Volume group Name
    :param session: When session is given, it means VM session
                    Otherwise default value means it work for host
    :return: The mapped blk target or None
    """
    cmd = "pvs | grep %s" % vg_name
    blk_target = None
    if session:
        output = session.cmd_output(cmd).strip()
    else:
        output = process.run(cmd, shell=True).stdout_text
    if output:
        # PV normally present as /dev/sda1
        pv_name = output.split()[0]
        blk_target = re.findall(r"[a-z]+", pv_name.split("/dev/")[1])[0]
    return blk_target
