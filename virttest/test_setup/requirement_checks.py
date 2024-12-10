import logging
import os
import re

from avocado.core import exceptions
from avocado.utils import path
from avocado.utils import process as a_process

from virttest import env_process, utils_misc
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
