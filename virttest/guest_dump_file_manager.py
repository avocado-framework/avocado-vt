# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2026
# Authors: Houqi (Nick) Zuo <hzuo@redhat.com>

import logging
import os
import shutil

from avocado.utils import process

from virttest import utils_misc

LOG = logging.getLogger(__name__)


class BaseDumpObject:
    """Base interface for all dump objects."""

    def __init__(self, manager):
        """
        Initialize the dump object.

        :param manager: Reference to GuestDumpFileManager for common methods/attributes
        """
        self._manager = manager

    def dump_memory(self, params, res_dir, image_path=None):
        """
        Extract dump files from guest.

        :param params: Test parameters
        :param res_dir: Directory to store extracted dump files
        :param image_path: Path to disk image (for offline methods)
        """
        raise NotImplementedError


class GuestDumpFileManager(object):
    """
    Base class for managing dump files from guest.

    Manages different memory dump objects (e.g. nbd_dump, qmp_dump, backup_image_dump).
    Users determine the dump method via vm_memory_dump_method param.
    """

    def __init__(self):
        """
        Initialize the GuestDumpFileManager.

        Sets up common attributes like guest type, filesystem support mapping,
        and directories to scan for dump files.
        """
        self._mount_pt = "/mnt/guest"  # Default mount point
        self._guest_type = ""  # linux or windows
        self._fs_support_mapping = {
            "ntfs": self._ntfs,
            "LVM2_member": self._lvm2_member,
        }
        self._dmp_dirs_scaned = {
            "windows": [
                "%s/Windows" % self._mount_pt,
                "%s/Windows/Minidump" % self._mount_pt,
                "%s/Windows/Temp" % self._mount_pt,
                "%s/Windows/LiveKernelReports" % self._mount_pt,
                "%s/Windows/ProgramData/Microsoft/Windows/WER" % self._mount_pt,
            ],
            "linux": [],
        }
        self._os_type_mapping = {
            "windows": "Microsoft basic data",
            "linux": "Linux LVM",
        }

    def get_dump_object(self, params):
        """
        Get appropriate dump object based on params.

        :param params: Cartesian params containing vm_memory_dump_method
        :return: Dump object instance, or None if vm_memory_dump_method not set

        Subclasses must implement this to return VM-specific dump objects.
        """
        raise NotImplementedError

    def extract_dump_files(self, params, res_dir, image_path=None):
        """
        Extract dump files from guest using appropriate dump method.

        This method is optional - only executes if vm_memory_dump_method is set.
        If vm_memory_dump_method is not set in params, this method returns early
        without doing anything.

        :param params: Parameters optionally containing vm_memory_dump_method and os_type
        :param res_dir: Directory to store extracted dump files
        :param image_path: Path to guest disk image (required for offline methods)

        Example with dump extraction:
            manager = get_dump_file_mgr("qemu")
            params = {"vm_memory_dump_method": "nbd", "os_type": "windows"}
            manager.extract_dump_files(params, "/tmp/results", "/path/to/image.qcow2")

        Example without dump extraction (skips silently):
            manager = get_dump_file_mgr("qemu")
            params = {"os_type": "windows"}  # No vm_memory_dump_method
            manager.extract_dump_files(params, "/tmp/results", "/path/to/image.qcow2")
            # Returns immediately without doing anything
        """
        # Skip if vm_memory_dump_method is not set
        if not params.get("vm_memory_dump_method"):
            return

        dump_obj = self.get_dump_object(params)
        if dump_obj:
            dump_obj.dump_memory(params, res_dir, image_path)

    def _process_dump_file_from_guest(self, res_dir):
        """
        Process dump files from mounted guest filesystem.

        Searches for dump files in predefined directories and copies
        them to the results directory. Called by dump objects after
        mounting the guest filesystem.

        :param res_dir: Directory where results should be stored
        """
        _dirs = []
        for item in self._dmp_dirs_scaned[self._guest_type]:
            if os.path.isdir(item):
                _dirs.append(item)
        if _dirs:
            _dirs = " ".join(_dirs)
            _cmd = 'find %s -maxdepth 1 -type f -iname "*.dmp"' % _dirs
            _find_dmp_in_path = process.run(_cmd, ignore_status=True).stdout_text
            if _find_dmp_in_path:
                _find_dmp_in_path = _find_dmp_in_path.strip().splitlines()
                LOG.debug("Found .dmp files at: %s", _find_dmp_in_path)
                res_dir = os.path.join(res_dir, "dump_file_from_guest")
                if not os.path.exists(res_dir):
                    os.makedirs(res_dir)
                for _idx, _path in enumerate(_find_dmp_in_path, 1):
                    _basename = os.path.basename(_path)
                    _dst = os.path.join(res_dir, "%02d_%s" % (_idx, _basename))
                    LOG.debug("Copy %s to %s", _path, _dst)
                    shutil.copy2(_path, _dst)
        else:
            LOG.debug("No dump directories found for guest type %s", self._guest_type)

    def _ntfs(self):
        """
        Get the filesystem type for NTFS partitions.

        :return: String representing the NTFS filesystem type ("ntfs").
        """
        # NOTE:
        # ntfs-3g permission means rw
        # ntfs permission means read-only
        return "ntfs"

    def _lvm2_member(self):
        """
        Get the filesystem type for LVM2 partitions.

        Note: LVM2_member cannot be mounted directly.

        :return: None (not yet implemented).
        """
        # The lvm2_member type (guest type is Linux) is generated by vt default
        # TODO: Support the linux guest. lvm2_member can NOT be used directly. And some steps are needed.
        return None


class QemuNBDDump(BaseDumpObject):
    """
    Extract dump files from guest disk image using NBD (offline).
    VM must be stopped.
    """

    def __init__(self, manager):
        super().__init__(manager)
        # NBD-specific attributes
        self._mount_pt = "/mnt/guest"
        self._nbd_dev = ""
        self._nbd_dev_partition_path = ""
        self._nbd_dev_cmd = "lsblk --output NAME,SIZE,MOUNTPOINT --noheadings"
        self._partition_list = []
        self._partition_fstype = ""

    def dump_memory(self, params, res_dir, image_path):
        """
        Extract dump files using NBD mount.

        The process includes:
        1. Finding an available NBD device
        2. Detecting partitions on NBD device
        3. Determining guest type and appropriate partition
        4. Detecting filesystem type
        5. Mounting the partition
        6. Processing dump files
        7. Cleanup (unmounting and disconnecting NBD)

        :param params: Parameters containing os_type
        :param res_dir: Directory to store extracted dump files
        :param image_path: Path to the QEMU disk image
        """
        # Find available NBD device
        _output = process.run(self._nbd_dev_cmd).stdout_text
        for row in _output.strip().splitlines()[::-1]:
            if "nbd" in row and "0B" in row and "/" not in row:
                self._nbd_dev = row.split()[0]
                break
        LOG.debug("Find the available nbd device: %s", self._nbd_dev)

        try:
            # Connect image to NBD
            qemu_nbd_cmd = "qemu-nbd -c /dev/%s %s" % (self._nbd_dev, image_path)
            process.run(qemu_nbd_cmd)
            LOG.debug("Connect the nbd device and image: %s", image_path)

            # Detect partitions
            self._manager._guest_type = params.get("os_type").lower()
            _output = (
                process.run("fdisk -l /dev/%s" % self._nbd_dev)
                .stdout_text.strip()
                .splitlines()
            )
            for row in _output:
                if row.startswith("/dev/%sp" % self._nbd_dev):
                    self._partition_list.append(row.split()[0])
                if self._manager._os_type_mapping[self._manager._guest_type] in row:
                    self._nbd_dev_partition_path = row.split()[0]

            LOG.debug("Detect the nbd partition list: %s", self._partition_list)
            LOG.debug("Detect the guest type: %s", self._manager._guest_type)
            LOG.debug("Detect the nbd partition path: %s", self._nbd_dev_partition_path)

            # Detect filesystem
            self._partition_fstype = process.run(
                "blkid -o value -s TYPE %s" % self._nbd_dev_partition_path
            ).stdout_text.strip()
            LOG.debug("Detect the guest fs type: %s", self._partition_fstype)

            if not os.path.exists(self._mount_pt):
                os.makedirs(self._mount_pt)

            # Mount and process
            utils_misc.mount(
                "%s" % self._nbd_dev_partition_path,
                self._mount_pt,
                fstype=self._manager._fs_support_mapping[self._partition_fstype](),
            )
            self._manager._process_dump_file_from_guest(res_dir)
        except KeyError:
            LOG.debug("Unsupported os_type: %s.", self._manager._guest_type)
        except Exception as e:
            LOG.debug("The exception happens.", exc_info=e)
        finally:
            # Cleanup
            try:
                utils_misc.umount(
                    "%s" % self._nbd_dev_partition_path, self._mount_pt, None
                )
            except Exception as e:
                LOG.debug("Failed to unmount: %s", e)

            try:
                process.run("qemu-nbd -d /dev/%s" % self._nbd_dev)
            except Exception as e:
                LOG.debug("Failed to disconnect NBD: %s", e)


class QemuQMPDump(BaseDumpObject):
    """
    Extract dump files from running guest using QMP/guest-agent (online).
    VM must be running with guest-agent.
    """

    def __init__(self, manager):
        super().__init__(manager)

    def dump_memory(self, params, res_dir, image_path=None):
        """
        Extract dump files using QMP/guest-agent.

        :param params: Parameters containing os_type
        :param res_dir: Directory to store extracted dump files
        :param image_path: Not used for online dump
        """
        raise NotImplementedError(
            "Online dump-file collection via QMP is not implemented"
        )


class QemuBackupImageDump(BaseDumpObject):
    """
    Extract dump files from a backup image using NBD (offline).
    Similar to QemuNBDDump but operates on backup image.
    """

    def __init__(self, manager):
        super().__init__(manager)
        # Similar to NBD but with different mount point
        self._mount_pt = "/mnt/guest_backup"
        self._nbd_dev = ""
        self._nbd_dev_partition_path = ""
        self._nbd_dev_cmd = "lsblk --output NAME,SIZE,MOUNTPOINT --noheadings"
        self._partition_list = []
        self._partition_fstype = ""

    def dump_memory(self, params, res_dir, image_path):
        """
        Extract dump files from backup image.

        :param params: Parameters containing os_type
        :param res_dir: Directory to store extracted dump files
        :param image_path: Path to the backup disk image
        """
        raise NotImplementedError("Backup image dump is not implemented")


class QemuDumpFileManager(GuestDumpFileManager):
    """
    Dump file manager for QEMU/KVM virtual machines.

    Manages different QEMU dump objects (NBD, QMP, BackupImage).
    """

    def __init__(self):
        """
        Initialize the QemuDumpFileManager.
        """
        super(QemuDumpFileManager, self).__init__()

    def get_dump_object(self, params):
        """
        Get QEMU-specific dump object.

        :param params: Cartesian params containing vm_memory_dump_method
        :return: QEMU dump object instance, or None if vm_memory_dump_method not set
        """
        # Get dump method from params
        dump_method = params.get("vm_memory_dump_method")

        if not dump_method:
            return None

        # Map to dump object classes
        dump_object_mapping = {
            "nbd": QemuNBDDump,
            "qmp": QemuQMPDump,
            "backup_image": QemuBackupImageDump,
        }

        if dump_method not in dump_object_mapping:
            raise ValueError(f"Unsupported dump_method: {dump_method}")

        # Return dump object instance with reference to self (manager)
        return dump_object_mapping[dump_method](self)


class LibvirtNBDDump(BaseDumpObject):
    """
    Extract dump files from libvirt guest disk using NBD (offline).
    VM must be stopped.
    """

    def __init__(self, manager):
        super().__init__(manager)

    def dump_memory(self, params, res_dir, image_path):
        """
        Extract dump files using NBD mount for libvirt.

        :param params: Parameters containing os_type
        :param res_dir: Directory to store extracted dump files
        :param image_path: Path to the disk image
        """
        raise NotImplementedError("Libvirt NBD dump is not implemented")


class LibvirtQMPDump(BaseDumpObject):
    """
    Extract dump files from running libvirt guest using QMP/guest-agent (online).
    VM must be running with guest-agent.
    """

    def __init__(self, manager):
        super().__init__(manager)

    def dump_memory(self, params, res_dir, image_path=None):
        """
        Extract dump files using QMP/guest-agent for libvirt.

        :param params: Parameters containing os_type
        :param res_dir: Directory to store extracted dump files
        :param image_path: Not used for online dump
        """
        raise NotImplementedError("Libvirt QMP dump is not implemented")


class LibvirtBackupImageDump(BaseDumpObject):
    """
    Extract dump files from a libvirt backup image (offline).
    """

    def __init__(self, manager):
        super().__init__(manager)

    def dump_memory(self, params, res_dir, image_path):
        """
        Extract dump files from libvirt backup image.

        :param params: Parameters containing os_type
        :param res_dir: Directory to store extracted dump files
        :param image_path: Path to the backup disk image
        """
        raise NotImplementedError("Libvirt backup image dump is not implemented")


class LibvirtDumpFileManager(GuestDumpFileManager):
    """
    Dump file manager for libvirt virtual machines.

    Manages different Libvirt dump objects.
    """

    def __init__(self):
        """
        Initialize the LibvirtDumpFileManager.
        """
        super(LibvirtDumpFileManager, self).__init__()

    def get_dump_object(self, params):
        """
        Get Libvirt-specific dump object.

        :param params: Cartesian params containing vm_memory_dump_method
        :return: Libvirt dump object instance, or None if vm_memory_dump_method not set
        """
        # Get dump method from params
        dump_method = params.get("vm_memory_dump_method")

        if not dump_method:
            return None

        # Map to dump object classes
        dump_object_mapping = {
            "nbd": LibvirtNBDDump,
            "qmp": LibvirtQMPDump,
            "backup_image": LibvirtBackupImageDump,
        }

        if dump_method not in dump_object_mapping:
            raise ValueError(f"Unsupported dump_method: {dump_method}")

        # Return dump object instance with reference to self (manager)
        return dump_object_mapping[dump_method](self)


class DumpFileManagerFactory(object):
    """
    Factory class for creating dump file manager instances.

    Implements the singleton pattern to ensure only one instance
    of each manager type is created.
    """

    _GDF_MGR_INS = {}

    @classmethod
    def get_mgr(cls, vm_type):
        """
        Get the dump file manager instance for the specified VM type.

        :param vm_type: Type of virtual machine ("qemu" or "libvirt").
        :type vm_type: str
        :return: Instance of the appropriate dump file manager.
        """
        _type_mgr_mapping = {
            "qemu": QemuDumpFileManager,
            "libvirt": LibvirtDumpFileManager,
        }
        if vm_type not in _type_mgr_mapping:
            raise ValueError(f"Unsupported vm_type: {vm_type}")
        if vm_type not in cls._GDF_MGR_INS:
            cls._GDF_MGR_INS[vm_type] = _type_mgr_mapping[vm_type]()
        return cls._GDF_MGR_INS[vm_type]


def get_dump_file_mgr(vm_type):
    """
    Get dump file manager instance for the specified VM type.

    This is a convenience function that delegates to the
    DumpFileManagerFactory.

    :param vm_type: Type of virtual machine ("qemu" or "libvirt").
    :type vm_type: str
    :return: Instance of the appropriate dump file manager.
    """
    return DumpFileManagerFactory.get_mgr(vm_type)
