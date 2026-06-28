# Copyright 2013-2021 Intranet AG and contributors
#
# avocado-i2n is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# avocado-i2n is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with avocado-i2n.  If not, see <http://www.gnu.org/licenses/>.

"""
Module for the LVM state management backend.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

..warning:: This state backend is mostly legacy and is not fully
    maintained (only tested in isolation) but kept here for backwards
    portability as well as completeness in case there is interest to
    revive it by contributors that actually need it.

INTERFACE
------------------------------------------------------

"""

import os
import re
import logging
import shutil
import time
from typing import Any

from avocado.core import exceptions
from avocado.utils import process
from avocado.utils import lv_utils
from virttest import env_process
from virttest.utils_params import Params

from .setup import StateBackend


class LVMBackend(StateBackend):
    """Backend manipulating states as logical volume snapshots."""

    @classmethod
    def _get_image_mount_loc(cls, params: Params) -> str:
        """
        Get the path to the mount location for the logical volume.

        :param params: configuration parameters
        :returns: mount location for the logical volume or empty string if a
                  raw image device is used
        """
        if params.get_boolean("image_raw_device", True):
            return ""
        image_name = params["image_name"]
        if os.path.isabs(image_name):
            return os.path.dirname(image_name)
        else:
            return params["images_base_dir"]

    @classmethod
    def show(cls, params: Params, object: Any = None) -> list[str]:
        """
        Return a list of available states of a specific type.

        All arguments match the base class.
        """
        return lv_utils.lv_list(params["vg_name"])

    @classmethod
    def get(cls, params: Params, object: Any = None) -> None:
        """
        Retrieve a state disregarding the current changes.

        All arguments match the base class.
        """
        vm_name = params["vms"]
        mount_loc = cls._get_image_mount_loc(params)
        params["lv_snapshot_name"] = params["get_state"]
        if mount_loc:
            # mount to avoid not-mounted errors
            try:
                lv_utils.lv_mount(
                    params["vg_name"], params["lv_pointer_name"], mount_loc
                )
            except lv_utils.LVException:
                pass
            lv_utils.lv_umount(params["vg_name"], params["lv_pointer_name"])
        try:
            logging.info("Restoring %s to state %s", vm_name, params["get_state"])
            lv_utils.lv_remove(params["vg_name"], params["lv_pointer_name"])
            lv_utils.lv_take_snapshot(
                params["vg_name"], params["lv_snapshot_name"], params["lv_pointer_name"]
            )
        finally:
            if mount_loc:
                lv_utils.lv_mount(
                    params["vg_name"], params["lv_pointer_name"], mount_loc
                )

    @classmethod
    def set(cls, params: Params, object: Any = None) -> None:
        """
        Store a state saving the current changes.

        All arguments match the base class.
        """
        vm_name = params["vms"]
        params["lv_snapshot_name"] = params["set_state"]
        logging.info("Taking a snapshot '%s' of %s", params["set_state"], vm_name)
        lv_utils.lv_take_snapshot(
            params["vg_name"], params["lv_pointer_name"], params["lv_snapshot_name"]
        )

    @classmethod
    def unset(cls, params: Params, object: Any = None) -> None:
        """
        Remove a state with previous changes.

        All arguments match the base class and in addition:

        :raises: :py:class:`ValueError` if LV pointer state was used
        """
        vm_name = params["vms"]
        lv_pointer = params["lv_pointer_name"]
        if params["unset_state"] == lv_pointer:
            raise ValueError("Cannot unset built-in state '%s'" % lv_pointer)
        params["lv_snapshot_name"] = params["unset_state"]
        logging.info("Removing snapshot %s of %s", params["lv_snapshot_name"], vm_name)
        lv_utils.lv_remove(params["vg_name"], params["lv_snapshot_name"])

    @classmethod
    def check_root(cls, params: Params, object: Any = None) -> bool:
        """
        Check whether a root state or essentially the object exists.

        All arguments match the base class.
        """
        vm_name = params["vms"]
        image_name = params["image_name"]
        logging.debug("Checking whether %s exists (root state requested)", vm_name)
        if lv_utils.lv_check(params["vg_name"], params["lv_name"]):
            logging.info(
                "The required virtual machine %s's %s (%s) exists",
                vm_name,
                image_name,
                params["lv_name"],
            )
            return True
        else:
            logging.info(
                "The required virtual machine %s's %s (%s) doesn't exist",
                vm_name,
                image_name,
                params["lv_name"],
            )
            return False

    @classmethod
    def set_root(cls, params: Params, object: Any = None) -> None:
        """
        Set a root state to provide object existence.

        All arguments match the base class.

        Create a disk, virtual group, thin pool and logical volume
        for each object.
        """
        vm_name = params["vms"]
        mount_loc = cls._get_image_mount_loc(params)
        logging.info("Creating original logical volume for %s", vm_name)
        vg_setup(
            params["vg_name"],
            params["disk_vg_size"],
            params["disk_basedir"],
            params["disk_sparse_filename"],
            params["use_tmpfs"] == "yes",
        )
        lv_utils.lv_create(
            params["vg_name"],
            params["lv_name"],
            params["lv_size"],
            # NOTE: call by key to keep good argument order which wasn't
            # accepted upstream for backward API compatibility
            pool_name=params["lv_pool_name"],
            pool_size=params["lv_pool_size"],
        )
        lv_utils.lv_take_snapshot(
            params["vg_name"], params["lv_name"], params["lv_pointer_name"]
        )
        if mount_loc:
            if not os.path.exists(mount_loc):
                os.mkdir(mount_loc)
            lv_utils.lv_mount(
                params["vg_name"],
                params["lv_pointer_name"],
                mount_loc,
                create_filesystem="ext4",
            )
            # TODO: it is not correct for the LVM backend to expect QCOW2 images
            # but at the moment we have no better way to provide on states with
            # base image to take snapshots of
            if object is not None and object.is_alive():
                object.destroy(gracefully=params.get_boolean("soft_boot", True))
            image_path = params["image_name"]
            if not os.path.isabs(image_path):
                image_path = os.path.join(params["images_base_dir"], image_path)
            image_format = params.get("image_format")
            image_format = "" if image_format in ["raw", ""] else "." + image_format
            if not os.path.exists(image_path + image_format):
                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                logging.info("Creating image %s for %s", image_path, vm_name)
                params.update({"create_image": "yes", "force_create_image": "yes"})
                env_process.preprocess_image(None, params, image_path)

    @classmethod
    def unset_root(cls, params: Params, object: Any = None) -> None:
        """
        Unset a root state to prevent object existence.

        All arguments match the base class and in addition:

        :raises: :py:class:`exceptions.TestWarn` if permanent vm was detected

        Remove the disk, virtual group, thin pool and logical volume
        of each object.
        """
        vm_name = params["vms"]
        mount_loc = cls._get_image_mount_loc(params)
        logging.info("Removing original logical volume for %s", vm_name)
        try:
            if mount_loc:
                if lv_utils.vg_check(params["vg_name"]):
                    # mount to avoid not-mounted errors
                    try:
                        lv_utils.lv_mount(
                            params["vg_name"], params["lv_pointer_name"], mount_loc
                        )
                    except lv_utils.LVException:
                        pass
                    lv_utils.lv_umount(params["vg_name"], params["lv_pointer_name"])
                if os.path.exists(mount_loc):
                    try:
                        os.rmdir(mount_loc)
                    except OSError as ex:
                        logging.warning(
                            "No permanent vm can be removed automatically. If "
                            "this is not a permanent test object, see the debug."
                        )
                        raise exceptions.TestWarn(
                            "Permanent vm %s was detected but cannot be "
                            "removed automatically" % vm_name
                        )
            vg_cleanup(
                params["disk_sparse_filename"],
                os.path.join(params["disk_basedir"], params["vg_name"]),
                params["vg_name"],
                None,
                params["use_tmpfs"] == "yes",
            )
        except exceptions.TestError as ex:
            logging.error(ex)


def vg_setup(
    vg_name: str,
    disk_vg_size: str,
    disk_basedir: str,
    disk_sparse_filename: str,
    use_tmpfs: bool = True,
) -> tuple[str, str, str, str]:
    """
    Create volume group on top of ram memory to speed up LV performance.

    When disk is specified the size of the physical volume is taken from
    existing disk space.

    :param vg_name: name of the volume group
    :param disk_vg_size: size of the disk virtual group (MB)
    :param disk_basedir: base directory for the disk sparse file
    :param disk_sparse_filename: name of the disk sparse file
    :param use_tmpfs: whether to use RAM or slower storage
    :returns: disk_filename, vg_disk_dir, vg_name, loop_device
    :raises: :py:class:`lv_utils.LVException` on failure at any stage

    Sample disk params:
    - disk_vg_size = "40000"
    - disk_basedir = "/tmp"
    - disk_sparse_filename = "virtual_hdd"

    Sample general params:
    - vg_name='autotest_vg',
    - lv_name='autotest_lv',
    - lv_size='1G',
    - lv_snapshot_name='autotest_sn',
    - lv_snapshot_size='1G'

    The disk volume group size is in MB.
    """
    vg_size = disk_vg_size
    vg_disk_dir = os.path.join(disk_basedir, vg_name)
    disk_filename = os.path.join(vg_disk_dir, disk_sparse_filename)
    # Try to cleanup the disk before defining it
    try:
        vg_cleanup(disk_filename, vg_disk_dir, vg_name, use_tmpfs)
    except lv_utils.LVException:
        pass
    if not os.path.exists(vg_disk_dir):
        os.makedirs(vg_disk_dir)
    try:
        if use_tmpfs:
            logging.debug("Mounting tmpfs")
            process.run("mount -t tmpfs tmpfs %s" % vg_disk_dir, sudo=True)

        logging.debug("Converting and copying /dev/zero")

        # Initializing sparse file with extra few bytes
        cmd = "dd if=/dev/zero of=%s bs=1M count=1 seek=%s" % (disk_filename, vg_size)
        process.run(cmd)
        logging.debug("Finding free loop device")
        result = process.run("losetup --find", sudo=True)
    except process.CmdError as ex:
        logging.error(ex)
        vg_cleanup(disk_filename, vg_disk_dir, vg_name, use_tmpfs)
        raise lv_utils.LVException("Fail to create vg_disk: %s" % ex)
    loop_device = result.stdout_text.rstrip()
    try:
        logging.debug("Creating loop device")
        process.run("losetup %s %s" % (loop_device, disk_filename), sudo=True)
        logging.debug("Creating physical volume %s", loop_device)
        process.run("pvcreate -y %s" % loop_device, sudo=True)
        logging.debug("Creating volume group %s", vg_name)
        process.run("vgcreate %s %s" % (vg_name, loop_device), sudo=True)
    except process.CmdError as ex:
        logging.error(ex)
        vg_cleanup(disk_filename, vg_disk_dir, vg_name, loop_device, use_tmpfs)
        raise lv_utils.LVException("Fail to create vg_disk: %s" % ex)
    return disk_filename, vg_disk_dir, vg_name, loop_device


def vg_cleanup(
    disk_filename: str = None,
    vg_disk_dir: str = None,
    vg_name: str = None,
    loop_device: str = None,
    use_tmpfs: bool = True,
) -> None:
    """
    Clean up any stage of the VG disk setup in case of test error.

    This detects whether the components were initialized and if so tries
    to remove them. In case of failure it raises summary exception.

    :param disk_filename: name of the disk sparse file
    :param vg_disk_dir: location of the disk file
    :param vg_name: name of the volume group
    :param loop_device: name of the disk or loop device
    :param use_tmpfs: whether to use RAM or slower storage
    :raises: :py:class:`lv_utils.LVException` on intolerable failure at any stage
    """
    errs = []
    if vg_name is not None:
        loop_device = re.search(
            r"([/\w-]+) +%s +lvm2" % vg_name, process.run("pvs", sudo=True).stdout_text
        )
        if loop_device is not None:
            loop_device = loop_device.group(1)
        process.run("vgremove -f %s" % vg_name, ignore_status=True, sudo=True)

    if loop_device is not None:
        result = process.run("pvremove %s" % loop_device, ignore_status=True, sudo=True)
        if result.exit_status != 0:
            errs.append("wipe pv")
            logging.error("Failed to wipe pv from %s: %s", loop_device, result)

        losetup_all = process.run("losetup --all", sudo=True).stdout_text
        if loop_device in losetup_all:
            disk_filename = re.search(
                r"%s: \[\d+\]:\d+ \(([/\w]+)\)" % loop_device, losetup_all
            )
            if disk_filename is not None:
                disk_filename = disk_filename.group(1)

            for _ in range(10):
                result = process.run(
                    "losetup -d %s" % loop_device, ignore_status=True, sudo=True
                )
                if b"resource busy" not in result.stderr:
                    if result.exit_status != 0:
                        errs.append("remove loop device")
                        logging.error(
                            "Unexpected failure when removing loop"
                            "device %s, check the log",
                            loop_device,
                        )
                    break
                time.sleep(0.1)

    if disk_filename is not None:
        if os.path.exists(disk_filename):
            os.unlink(disk_filename)
            logging.debug("Disk filename %s deleted", disk_filename)
            vg_disk_dir = os.path.dirname(disk_filename)

    if vg_disk_dir is not None:
        if use_tmpfs and not process.system(
            "mountpoint %s" % vg_disk_dir, ignore_status=True
        ):
            for _ in range(10):
                result = process.run(
                    "umount %s" % vg_disk_dir, ignore_status=True, sudo=True
                )
                time.sleep(0.1)
                if result.exit_status == 0:
                    break
            else:
                errs.append("umount")
                logging.error(
                    "Unexpected failure unmounting %s, check the " "log", vg_disk_dir
                )

        if os.path.exists(vg_disk_dir):
            try:
                shutil.rmtree(vg_disk_dir)
                logging.debug("Disk directory %s deleted", vg_disk_dir)
            except OSError as details:
                errs.append("rm-disk-dir")
                logging.error("Failed to remove disk_dir: %s", details)
    if errs:
        raise lv_utils.LVException("vg_cleanup failed: %s" % ", ".join(errs))
