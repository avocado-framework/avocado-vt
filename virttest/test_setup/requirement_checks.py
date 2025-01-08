import logging
import os
import re

from avocado.core import exceptions
from avocado.utils import path
from avocado.utils import process as a_process

from virttest import data_dir, env_process, utils_misc
from virttest.test_setup.core import Setuper
from virttest.utils_version import VersionInterval

LOG = logging.getLogger(__name__)

version_info = {}


class CheckInstalledCMDs(Setuper):
    def setup(self):
        # throw a TestSkipError exception if command requested by test is not
        # installed.
        if self.params.get("cmds_installed_host"):
            for cmd in self.params.get("cmds_installed_host").split():
                try:
                    path.find_command(cmd)
                except path.CmdNotFoundError as msg:
                    raise exceptions.TestSkipError(msg)

    def cleanup(self):
        pass


class CheckRunningAsRoot(Setuper):
    def setup(self):
        # Verify if this test does require root or not. If it does and the
        # test suite is running as a regular user, we shall just throw a
        # TestSkipError exception, which will skip the test.
        if self.params.get("requires_root", "no") == "yes":
            utils_misc.verify_running_as_root()

    def cleanup(self):
        pass


class CheckKernelVersion(Setuper):
    def setup(self):
        # Get the KVM kernel module version
        if os.path.exists("/dev/kvm"):
            kvm_version = os.uname()[2]
        else:
            warning_msg = "KVM module not loaded"
            if self.params.get("enable_kvm", "yes") == "yes":
                self.test.cancel(warning_msg)
            LOG.warning(warning_msg)
            kvm_version = "Unknown"

        LOG.debug("KVM version: %s" % kvm_version)
        version_info["kvm_version"] = str(kvm_version)

        # Checking required kernel, if not satisfied, cancel test
        if self.params.get("required_kernel"):
            required_kernel = self.params.get("required_kernel")
            LOG.info("Test requires kernel version: %s" % required_kernel)
            match = re.search(r"[0-9]+\.[0-9]+\.[0-9]+(\-[0-9]+)?", kvm_version)
            if match is None:
                self.test.cancel("Can not get host kernel version.")
            host_kernel = match.group(0)
            if host_kernel not in VersionInterval(required_kernel):
                self.test.cancel(
                    "Got host kernel version:%s, which is not in %s"
                    % (host_kernel, required_kernel)
                )

    def cleanup(self):
        pass


class CheckQEMUVersion(Setuper):
    @staticmethod
    def _get_qemu_version(qemu_cmd):
        """
        Return normalized qemu version

        :param qemu_cmd: Path to qemu binary
        """
        version_output = a_process.run(
            "%s -version" % qemu_cmd, verbose=False
        ).stdout_text
        version_line = version_output.split("\n")[0]
        matches = re.match(env_process.QEMU_VERSION_RE, version_line)
        if matches:
            return "%s (%s)" % matches.groups()
        else:
            return "Unknown"

    def setup(self):
        # Get the KVM userspace version
        kvm_userspace_ver_cmd = self.params.get("kvm_userspace_ver_cmd", "")
        if kvm_userspace_ver_cmd:
            try:
                kvm_userspace_version = a_process.run(
                    kvm_userspace_ver_cmd, shell=True
                ).stdout_text.strip()
            except a_process.CmdError:
                kvm_userspace_version = "Unknown"
        else:
            qemu_path = utils_misc.get_qemu_binary(self.params)
            kvm_userspace_version = self._get_qemu_version(qemu_path)
            qemu_dst_path = utils_misc.get_qemu_dst_binary(self.params)
            if qemu_dst_path and qemu_dst_path != qemu_path:
                LOG.debug(
                    "KVM userspace dst version(qemu): %s",
                    self._get_qemu_version(qemu_dst_path),
                )

        LOG.debug("KVM userspace version(qemu): %s", kvm_userspace_version)
        version_info["qemu_version"] = str(kvm_userspace_version)

        # Checking required qemu, if not satisfied, cancel test
        if self.params.get("required_qemu"):
            required_qemu = self.params.get("required_qemu")
            LOG.info("Test requires qemu version: %s" % required_qemu)
            match = re.search(
                r"[0-9]+\.[0-9]+\.[0-9]+(\-[0-9]+)?", kvm_userspace_version
            )
            if match is None:
                self.test.cancel("Can not get host qemu version.")
            host_qemu = match.group(0)
            if host_qemu not in VersionInterval(required_qemu):
                self.test.cancel(
                    "Got host qemu version:%s, which is not in %s"
                    % (host_qemu, required_qemu)
                )

    def cleanup(self):
        pass


class LogBootloaderVersion(Setuper):
    def setup(self):
        # Get the version of bootloader
        vm_bootloader_ver_cmd = self.params.get("vm_bootloader_ver_cmd", "")
        if vm_bootloader_ver_cmd:
            try:
                vm_bootloader_ver = a_process.run(
                    vm_bootloader_ver_cmd, shell=True
                ).stdout_text.strip()
            except a_process.CmdError:
                vm_bootloader_ver = "Unknown"
            version_info["vm_bootloader_version"] = str(vm_bootloader_ver)
            LOG.debug("vm bootloader version: %s", vm_bootloader_ver)

    def cleanup(self):
        pass


class CheckVirtioWinVersion(Setuper):
    def setup(self):
        # Checking required virtio-win version, if not satisfied, cancel test
        if self.params.get("required_virtio_win") or self.params.get(
            "required_virtio_win_prewhql"
        ):
            if self.params.get("cdrom_virtio"):
                cdrom_virtio = self.params["cdrom_virtio"]
                cdrom_virtio_path = os.path.basename(
                    utils_misc.get_path(data_dir.get_data_dir(), cdrom_virtio)
                )
                virtio_win_range = (
                    self.params.get("required_virtio_win_prewhql")
                    if re.search("prewhql", cdrom_virtio_path)
                    else self.params.get("required_virtio_win")
                )
                if virtio_win_range:
                    LOG.info(
                        "Checking required virtio-win version: %s" % virtio_win_range
                    )
                    match = re.search(
                        "virtio-win-(?:prewhql-)?(\d+\.\d+(?:\.\d+)?-\d+)",
                        cdrom_virtio_path,
                    )
                    if match.group(1) is None:
                        self.test.error(
                            'Can not get virtio-win version from "cdrom_virtio": %s'
                            % cdrom_virtio
                        )
                    cdrom_virtio_version = re.sub("-", ".", match.group(1))
                    if cdrom_virtio_version not in VersionInterval(virtio_win_range):
                        self.test.cancel(
                            "Got virtio-win version:%s, which is not in %s"
                            % (cdrom_virtio_version, virtio_win_range)
                        )
                else:
                    self.test.error(
                        "The limitation for virtio-win is not suitable for the cdrom_virtio"
                    )
            else:
                LOG.warning(
                    "required_virtio_win(prewhql) can not take effect without cdrom_virtio"
                )

    def cleanup(self):
        pass


class CheckLibvirtVersion(Setuper):
    def setup(self):
        # Get the Libvirt version
        vm_type = self.params.get("vm_type")
        if vm_type == "libvirt":
            libvirt_ver_cmd = self.params.get(
                "libvirt_ver_cmd", "libvirtd -V|awk -F' ' '{print $3}'"
            )
            try:
                libvirt_version = a_process.run(
                    libvirt_ver_cmd, shell=True
                ).stdout_text.strip()
            except a_process.CmdError:
                libvirt_version = "Unknown"
            version_info["libvirt_version"] = str(libvirt_version)
            LOG.debug("KVM userspace version(libvirt): %s" % libvirt_version)

    def cleanup(self):
        pass


class LogVersionInfo(Setuper):
    def setup(self):
        # Write package version info dict as a keyval
        self.test.write_test_keyval(version_info)

    def cleanup(self):
        pass
