"""
Kdump utility functions for guest crash dump testing.

This module provides utilities for:
- Kdump service setup and configuration across multiple Linux distributions
- Crash triggering and vmcore management
- Crash utility analysis
- Multi-distro support (RHEL, Fedora, Ubuntu, SLES)
"""

import logging
import time

from aexpect.exceptions import ShellProcessTerminatedError

LOG = logging.getLogger("avocado." + __name__)


def get_distro_info(session):
    """
    Get normalized distro information and distro-specific kdump commands.

    Detects the guest OS distribution and returns a dictionary containing
    distro-specific commands for package management, kdump service control,
    GRUB configuration, and crash utility paths.

    Supported distributions: RHEL, Fedora, Ubuntu, SLES/SUSE

    :param session: Guest session object
    :return: Dict with normalized distro metadata including:
             - name: Distribution name (rhel, fedora, ubuntu, sles, unknown)
             - family: Distribution family (redhat, debian, suse)
             - pkg_query_cmd: Command to query if package is installed
             - pkg_glob_query_cmd: Command to query packages with glob pattern
             - pkg_install_cmd: Command to install packages
             - kdump_status_cmd: Command to check kdump service status
             - kdump_enable_cmd: Command to enable kdump service
             - kdump_start_cmd: Command to start/restart kdump service
             - kdump_service_name: Name of kdump service
             - grub_update_cmd: Command to update GRUB configuration
             - default_grub_file: Path to GRUB config file
             - grub_cmdline_key: GRUB cmdline key for kernel parameters
             - vmlinux_path_template: Path template for vmlinux debug symbols
             - kdump_packages: List of required kdump packages
             - crash_debug_packages: List of crash utility debug packages
             - crash_debug_package_templates: Package name templates with {kernel}
    """
    distro_details = session.cmd("cat /etc/os-release").lower()
    distro_info = {
        "details": distro_details,
        "name": None,
        "family": None,
        "pkg_query_cmd": None,
        "pkg_glob_query_cmd": None,
        "pkg_install_cmd": None,
        "kdump_status_cmd": None,
        "kdump_enable_cmd": None,
        "kdump_start_cmd": None,
        "kdump_service_name": None,
        "grub_update_cmd": None,
        "default_grub_file": "/etc/default/grub",
        "grub_cmdline_key": None,
        "vmlinux_path_template": None,
        "kdump_packages": [],
        "crash_debug_packages": [],
        "crash_debug_package_templates": [],
    }

    if "sles" in distro_details or "suse" in distro_details:
        distro_info.update(
            {
                "name": "sles",
                "family": "suse",
                "pkg_query_cmd": "rpm -q {package}",
                "pkg_glob_query_cmd": "rpm -qa {pattern}",
                "pkg_install_cmd": "zypper --non-interactive install {packages}",
                "kdump_status_cmd": "systemctl status kdump",
                "kdump_enable_cmd": "systemctl enable kdump",
                "kdump_start_cmd": "systemctl restart kdump",
                "kdump_service_name": "kdump",
                "grub_update_cmd": "grub2-mkconfig -o /boot/grub2/grub.cfg",
                "grub_cmdline_key": "GRUB_CMDLINE_LINUX_DEFAULT",
                "vmlinux_path_template": (
                    "/usr/lib/debug/usr/lib/modules/{kernel}/vmlinux.debug"
                    " /boot/vmlinux-{kernel}"
                ),
                "kdump_packages": ["kdump", "kexec-tools"],
                "crash_debug_packages": [
                    "*kdump*",
                    "*kexec-tools*",
                    "*crash*",
                    "*elfutils*",
                    "kernel-default-debuginfo",
                ],
                "crash_debug_package_templates": [],
            }
        )
    elif "ubuntu" in distro_details:
        distro_info.update(
            {
                "name": "ubuntu",
                "family": "debian",
                "pkg_query_cmd": "dpkg-query -W {package}",
                "pkg_glob_query_cmd": (
                    "dpkg-query -W -f='${Package}\\n' 2>/dev/null | grep -E '^{pattern}$'"
                ),
                "pkg_install_cmd": (
                    "DEBIAN_FRONTEND=noninteractive apt-get update && "
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y {packages}"
                ),
                "kdump_status_cmd": "kdump-config status",
                "kdump_enable_cmd": "systemctl enable kdump-tools",
                "kdump_start_cmd": "systemctl restart kdump-tools",
                "kdump_service_name": "kdump-tools",
                "grub_update_cmd": "update-grub",
                "grub_cmdline_key": "GRUB_CMDLINE_LINUX_DEFAULT",
                "vmlinux_path_template": "/usr/lib/debug/boot/vmlinux-{kernel}",
                "kdump_packages": ["kdump-tools", "kexec-tools"],
                "crash_debug_packages": [
                    "*linux-crashdump*",
                    "*kdump-tools*",
                    "*crash*",
                    "*elfutils*",
                ],
                "crash_debug_package_templates": [],
            }
        )
    elif "fedora" in distro_details:
        distro_info.update(
            {
                "name": "fedora",
                "family": "redhat",
                "pkg_query_cmd": "rpm -q {package}",
                "pkg_glob_query_cmd": "rpm -qa {pattern}",
                "pkg_install_cmd": "dnf install -y {packages}",
                "kdump_status_cmd": "kdumpctl status",
                "kdump_enable_cmd": "systemctl enable kdump",
                "kdump_start_cmd": "systemctl restart kdump",
                "kdump_service_name": "kdump",
                "grub_update_cmd": "grub2-mkconfig -o /boot/grub2/grub.cfg",
                "grub_cmdline_key": "GRUB_CMDLINE_LINUX",
                "vmlinux_path_template": "/usr/lib/debug/lib/modules/{kernel}/vmlinux",
                "kdump_packages": ["kexec-tools"],
                "crash_debug_packages": [
                    "*kexec-tools*",
                    "*elfutils*",
                    "*crash*",
                    "*kdump-utils*",
                ],
                "crash_debug_package_templates": ["kernel-debuginfo-{kernel}"],
            }
        )
    elif "rhel" in distro_details or "red hat" in distro_details:
        distro_info.update(
            {
                "name": "rhel",
                "family": "redhat",
                "pkg_query_cmd": "rpm -q {package}",
                "pkg_glob_query_cmd": "rpm -qa {pattern}",
                "pkg_install_cmd": "yum install -y {packages}",
                "kdump_status_cmd": "kdumpctl status",
                "kdump_enable_cmd": "systemctl enable kdump",
                "kdump_start_cmd": "systemctl restart kdump",
                "kdump_service_name": "kdump",
                "grub_update_cmd": "grub2-mkconfig -o /boot/grub2/grub.cfg",
                "grub_cmdline_key": "GRUB_CMDLINE_LINUX",
                "vmlinux_path_template": "/usr/lib/debug/lib/modules/{kernel}/vmlinux",
                "kdump_packages": ["kexec-tools"],
                "crash_debug_packages": [
                    "*kexec-tools*",
                    "*elfutils*",
                    "*crash*",
                    "*kdump-utils*",
                ],
                "crash_debug_package_templates": ["kernel-debuginfo-{kernel}"],
            }
        )
    else:
        distro_info["name"] = "unknown"

    return distro_info


def ensure_kdump_packages(vm, distro_info, install_missing=True, test=None):
    """
    Ensure kdump packages are installed in guest.

    Checks if required kdump packages are installed and optionally installs
    missing packages. Returns True if any packages were installed.

    :param vm: VM object
    :param distro_info: Distro metadata dict from get_distro_info()
    :param install_missing: Whether to install missing packages (default: True)
    :param test: Test object for error/fail reporting (optional)
    :return: True if packages were installed, False otherwise
    :raises: TestError if packages missing and install_missing=False
    """
    package_list = distro_info["kdump_packages"]
    if not package_list:
        return False

    session = vm.wait_for_login(timeout=240)
    missing_packages = []
    for package in package_list:
        status, _ = session.cmd_status_output(
            distro_info["pkg_query_cmd"].format(package=package)
        )
        if status:
            missing_packages.append(package)

    if missing_packages and not install_missing:
        session.close()
        if test:
            test.error(
                "Missing required packages in %s: %s" % (vm.name, missing_packages)
            )
        return False

    if missing_packages:
        LOG.info(
            "Installing missing packages in %s: %s", vm.name, missing_packages
        )
        install_cmd = distro_info["pkg_install_cmd"].format(
            packages=" ".join(missing_packages)
        )
        status, output = session.cmd_status_output(install_cmd, timeout=1200)
        if status:
            session.close()
            if test:
                test.fail(
                    "Failed to install packages in %s: %s" % (vm.name, output)
                )
            return False
        session.close()
        return True

    session.close()
    return False


def ensure_crash_utility_packages(
    vm, distro_info, install_missing=True, upstream_kernel=False, test=None
):
    """
    Ensure crash utility and debug packages are installed in guest.

    Installs crash utility and kernel debug symbols required for vmcore analysis.
    For RedHat family with non-upstream kernels, also installs kernel-debuginfo.

    :param vm: VM object
    :param distro_info: Distro metadata dict from get_distro_info()
    :param install_missing: Whether to install missing packages (default: True)
    :param upstream_kernel: Whether guest uses upstream kernel (default: False)
    :param test: Test object for error/fail reporting (optional)
    :raises: TestError if packages missing and install_missing=False
    """
    debug_packages = list(distro_info["crash_debug_packages"])
    if not debug_packages and not distro_info["crash_debug_package_templates"]:
        return

    session = vm.wait_for_login(timeout=240)
    if distro_info["family"] == "redhat" and not upstream_kernel:
        guest_kernel = session.cmd("uname -r").strip()
        debug_packages.extend(
            [
                pkg.format(kernel=guest_kernel)
                for pkg in distro_info["crash_debug_package_templates"]
            ]
        )

    missing_packages = []
    for package in debug_packages:
        get_library_cmd = distro_info["pkg_glob_query_cmd"].format(
            pattern=package if "*" in package else package.replace("*", ".*")
        )
        output = session.cmd_status_output(get_library_cmd)[1].split()
        if not output:
            missing_packages.append(package)

    if missing_packages and not install_missing:
        session.close()
        if test:
            test.error(
                "Missing crash utility packages in %s: %s"
                % (vm.name, missing_packages)
            )
        return

    if missing_packages:
        LOG.info(
            "Installing missing crash utility packages in %s: %s",
            vm.name,
            missing_packages,
        )
        install_cmd = distro_info["pkg_install_cmd"].format(
            packages=" ".join(missing_packages)
        )
        status, output = session.cmd_status_output(install_cmd, timeout=1200)
        if status:
            session.close()
            if test:
                test.fail(
                    "Failed to install crash utility packages in %s: %s"
                    % (vm.name, output)
                )
            return

    session.close()


def configure_kdump(vm, distro_info, crashkernel_value="1024M", test=None):
    """
    Configure kdump service with crashkernel parameter in guest.

    Updates GRUB configuration to add/modify crashkernel parameter, updates
    GRUB, reboots if needed, and enables/starts kdump service.

    :param vm: VM object
    :param distro_info: Distro metadata dict from get_distro_info()
    :param crashkernel_value: Crashkernel memory value (default: "1024M")
    :param test: Test object for fail reporting (optional)
    :return: True if reboot was required, False otherwise
    :raises: TestFail if configuration fails
    """
    session = vm.wait_for_login(timeout=240)
    kdump_changed = False

    cmdline = session.cmd("cat /proc/cmdline").strip()
    active_crashkernel = ""
    for cmdline_arg in cmdline.split():
        if cmdline_arg.startswith("crashkernel="):
            active_crashkernel = cmdline_arg.split("=", 1)[1]
            break

    if active_crashkernel != crashkernel_value:
        grub_file = distro_info["default_grub_file"]
        status, grub_content = session.cmd_status_output("cat %s" % grub_file)
        if status:
            session.close()
            if test:
                test.fail(
                    "Failed to read grub config in %s: %s" % (vm.name, grub_content)
                )
            return False

        grub_cmdline_key = distro_info["grub_cmdline_key"]
        if "%s=" % grub_cmdline_key not in grub_content:
            session.close()
            if test:
                test.fail(
                    "%s entry not found in %s for %s"
                    % (grub_cmdline_key, grub_file, vm.name)
                )
            return False

        update_grub_cmd = (
            "sed -i.bak -E "
            "'/^{grub_cmdline_key}=/ {{ "
            "s/[[:space:]]+crashkernel=[^\"[:space:]]+//g; "
            "s/\"$/ crashkernel={crashkernel_value}\"/; "
            "}}' "
            "{grub_file}"
        ).format(
            grub_file=grub_file,
            grub_cmdline_key=grub_cmdline_key,
            crashkernel_value=crashkernel_value,
        )
        status, output = session.cmd_status_output(update_grub_cmd)
        if status:
            session.close()
            if test:
                test.fail(
                    "Failed to configure crashkernel in %s: %s" % (vm.name, output)
                )
            return False

        status, output = session.cmd_status_output(
            distro_info["grub_update_cmd"], timeout=600
        )
        if status:
            session.close()
            if test:
                test.fail("Failed to update grub in %s: %s" % (vm.name, output))
            return False

        kdump_changed = True

    if kdump_changed:
        session.close()
        LOG.info("Rebooting %s after kdump configuration changes", vm.name)
        vm.reboot(session=None, timeout=240)
        session = vm.wait_for_login(timeout=240)
        new_cmdline = session.cmd("cat /proc/cmdline").strip()
        expected_crashkernel = "crashkernel=%s" % crashkernel_value
        if expected_crashkernel not in new_cmdline:
            session.close()
            if test:
                test.fail(
                    "Crashkernel value did not take effect in %s after reboot: %s"
                    % (vm.name, new_cmdline)
                )
            return True
    else:
        session.close()
        session = vm.wait_for_login(timeout=240)

    status, output = session.cmd_status_output(distro_info["kdump_enable_cmd"])
    if status:
        session.close()
        if test:
            test.fail(
                "Failed to enable kdump service in %s: %s" % (vm.name, output)
            )
        return kdump_changed

    status, output = session.cmd_status_output(
        distro_info["kdump_start_cmd"], timeout=300
    )
    if status:
        session.close()
        if test:
            test.fail(
                "Failed to start kdump service in %s: %s" % (vm.name, output)
            )
        return kdump_changed

    session.close()
    return kdump_changed


def check_kdump_service(vm, distro_info, crashkernel_value=None, test=None):
    """
    Check if kdump service is running and properly configured.

    Verifies kdump service status and optionally checks if crashkernel
    parameter matches expected value.

    :param vm: VM object
    :param distro_info: Distro metadata dict from get_distro_info()
    :param crashkernel_value: Expected crashkernel value to verify (optional)
    :param test: Test object for error/fail reporting (optional)
    :raises: TestError if kdump service is not running
    :raises: TestFail if crashkernel value doesn't match
    """
    LOG.info("Checking for kdump service in guest %s", vm.name)
    session = vm.wait_for_login(timeout=240)

    check_status, check_output = session.cmd_status_output(
        distro_info["kdump_status_cmd"]
    )
    if check_status:
        LOG.debug("Kdump service status: %s", check_output)
        session.close()
        if test:
            test.error("Kdump service is not running in guest %s" % vm.name)
        return

    if crashkernel_value:
        active_cmdline = session.cmd("cat /proc/cmdline").strip()
        expected_crashkernel = "crashkernel=%s" % crashkernel_value
        if expected_crashkernel not in active_cmdline:
            session.close()
            if test:
                test.fail(
                    "Crashkernel value mismatch in %s. Expected %s in %s"
                    % (vm.name, expected_crashkernel, active_cmdline)
                )
            return

    LOG.info("Kdump service is up and running:\n%s", check_output)
    session.close()


def get_vmcores(vm, crash_dir="/var/crash/", test=None):
    """
    Get list of vmcore files in crash directory.

    Searches for vmcore files in the specified crash directory and returns
    a sorted list of their paths.

    :param vm: VM object
    :param crash_dir: Directory where vmcores are stored (default: /var/crash/)
    :param test: Test object for cancel reporting (optional)
    :return: List of vmcore file paths (empty list if none found)
    """
    LOG.info("Getting vmcores in the guest %s", vm.name)
    session = vm.wait_for_login(timeout=100)
    distro_info = get_distro_info(session)
    if distro_info["name"] == "unknown":
        session.close()
        if test:
            test.cancel("Guest distro not supported")
        return []

    get_vmcores_cmd = (
        "find {crash_dir} -type f -name vmcore 2>/dev/null | sort"
    ).format(crash_dir=crash_dir.rstrip("/"))
    status, output = session.cmd_status_output(get_vmcores_cmd)
    session.close()
    if status:
        return []
    return output.split()


def trigger_crash(
    vm,
    session=None,
    enable_sysrq_cmd="echo 1 > /proc/sys/kernel/sysrq",
    trigger_crash_cmd="echo c > /proc/sysrq-trigger",
    wait_time=120,
    test=None,
):
    """
    Trigger sysrq crash in guest.

    Enables sysrq and triggers a kernel crash using sysrq-trigger mechanism.
    Handles the expected shell termination after crash.

    :param vm: VM object
    :param session: Guest session (will create new if None)
    :param enable_sysrq_cmd: Command to enable sysrq
    :param trigger_crash_cmd: Command to trigger crash
    :param wait_time: Time to wait after crash trigger (default: 120 seconds)
    :param test: Test object for fail reporting (optional)
    :raises: TestFail if sysrq enable fails
    """
    LOG.info("Triggering sysrq crash in guest %s", vm.name)
    if session is None:
        session = vm.wait_for_login(timeout=100)

    status, output = session.cmd_status_output(enable_sysrq_cmd)
    if status:
        session.close()
        if test:
            test.fail("Failed to enable sysrq in guest %s: %s" % (vm.name, output))
        return

    try:
        session.cmd(trigger_crash_cmd)
    except ShellProcessTerminatedError:
        time.sleep(wait_time)
    session.close()


def analyze_vmcore_with_crash(
    vm, distro_info, vmcore_file, upstream_kernel=False, vmlinux_path=None, test=None
):
    """
    Analyze vmcore using crash utility.

    Runs crash utility on the specified vmcore file with appropriate vmlinux
    debug symbols. Executes 'ps' command to verify crash utility works.

    :param vm: VM object
    :param distro_info: Distro metadata dict from get_distro_info()
    :param vmcore_file: Path to vmcore file in guest
    :param upstream_kernel: Whether guest uses upstream kernel (default: False)
    :param vmlinux_path: Custom vmlinux path (overrides distro default)
    :param test: Test object for fail/cancel reporting (optional)
    :raises: TestFail if crash utility cannot analyze vmcore
    :raises: TestCancel if distro not supported
    """
    LOG.info("Debugging %s vmcore using crash utility", vm.name)
    if distro_info["name"] == "unknown":
        if test:
            test.cancel("Guest distro not supported")
        return

    session = vm.wait_for_login(timeout=100)
    guest_kernel = session.cmd("uname -r").strip()

    vmlinux = distro_info["vmlinux_path_template"].format(kernel=guest_kernel)
    if upstream_kernel and vmlinux_path:
        vmlinux = vmlinux_path
    elif vmlinux_path:
        vmlinux = vmlinux_path

    crash_cmd = "printf 'ps\\nquit\\n' | crash %s %s" % (vmlinux, vmcore_file)
    LOG.debug("Crash command: %s", crash_cmd)
    crash_status, crash_log = session.cmd_status_output(crash_cmd, timeout=300)
    if crash_status and not crash_log:
        crash_log = session.get_output()
    session.close()

    LOG.debug("Crash utility output: %s", crash_log)
    if "PID" not in crash_log or "crash>" not in crash_log:
        if test:
            test.fail(
                "Failed to debug %s vmcore using crash utility" % vm.name
            )


def check_guest_status(vm):
    """
    Check if guest is in running state.

    :param vm: VM object
    :return: 0 if guest is running, 1 if not running
    """
    LOG.info("Checking domstate of guest %s", vm.name)
    if vm.state() != "running":
        LOG.debug("Domain is not running: %s", vm.state())
        return 1
    return 0


class KdumpManager:
    """
    High-level kdump management class for easier test integration.

    Provides a convenient interface for common kdump operations including
    setup, crash triggering, and vmcore verification.

    Example usage:
        kdump_mgr = KdumpManager(vm, params, test)
        kdump_mgr.setup()
        kdump_mgr.trigger_crash()
        kdump_mgr.verify_vmcore_generated()
        kdump_mgr.analyze_vmcore()
    """

    def __init__(self, vm, params, test=None):
        """
        Initialize KdumpManager.

        :param vm: VM object
        :param params: Test parameters dict
        :param test: Test object for error/fail reporting (optional)
        """
        self.vm = vm
        self.params = params
        self.test = test
        self.crashkernel_value = params.get("crashkernel_value", "1024M")
        self.crash_dir = params.get("crash_dir", "/var/crash/")
        self.install_missing_packages = (
            params.get("install_missing_packages", "yes") == "yes"
        )
        self.upstream_kernel = params.get("guest_upstream_kernel", "no") == "yes"
        self.upstream_kernel_vmlinux = params.get("upstream_kernel_vmlinux")
        self.distro_info = None
        self.pre_vmcores = []
        self.post_vmcores = []

    def _get_distro_info(self):
        """Detect and cache distro info for this VM."""
        if self.distro_info is None:
            session = self.vm.wait_for_login(timeout=240)
            self.distro_info = get_distro_info(session)
            session.close()
            if self.distro_info["name"] == "unknown" and self.test:
                self.test.cancel("Guest distro not supported")
        return self.distro_info

    def setup(self, install_packages=True, configure=True):
        """
        Setup kdump: detect distro, install packages, configure, enable service.

        :param install_packages: Whether to install kdump packages (default: True)
        :param configure: Whether to configure kdump (default: True)
        :return: True if reboot was required, False otherwise
        """
        distro_info = self._get_distro_info()
        reboot_required = False

        if install_packages:
            packages_installed = ensure_kdump_packages(
                self.vm,
                distro_info,
                install_missing=self.install_missing_packages,
                test=self.test,
            )
            if packages_installed:
                LOG.info(
                    "Rebooting %s after kdump package installation", self.vm.name
                )
                self.vm.reboot(session=None, timeout=240)

        if configure:
            reboot_required = configure_kdump(
                self.vm,
                distro_info,
                crashkernel_value=self.crashkernel_value,
                test=self.test,
            )

        return reboot_required

    def check_service(self):
        """
        Check if kdump service is running and properly configured.

        :raises: TestError if kdump service is not running
        """
        check_kdump_service(
            self.vm,
            self._get_distro_info(),
            crashkernel_value=self.crashkernel_value,
            test=self.test,
        )

    def get_vmcores_before_crash(self):
        """
        Get and store list of vmcores before triggering crash.

        :return: List of vmcore paths
        """
        self.pre_vmcores = get_vmcores(
            self.vm, crash_dir=self.crash_dir, test=self.test
        )
        LOG.info("%s vmcores before crash: %s", self.vm.name, self.pre_vmcores)
        return self.pre_vmcores

    def trigger_crash(self, wait_time=120):
        """
        Trigger crash in VM.

        :param wait_time: Time to wait after crash trigger (default: 120 seconds)
        """
        trigger_crash(self.vm, wait_time=wait_time, test=self.test)

    def get_vmcores_after_crash(self):
        """
        Get and store list of vmcores after crash.

        :return: List of vmcore paths
        """
        self.post_vmcores = get_vmcores(
            self.vm, crash_dir=self.crash_dir, test=self.test
        )
        LOG.info("%s vmcores after crash: %s", self.vm.name, self.post_vmcores)
        return self.post_vmcores

    def get_new_vmcores(self):
        """
        Get list of newly generated vmcores (difference between post and pre).

        :return: List of new vmcore paths
        """
        return sorted(list(set(self.post_vmcores) - set(self.pre_vmcores)))

    def verify_vmcore_generated(self):
        """
        Verify that new vmcore was generated after crash.

        :raises: TestFail if no new vmcore found
        """
        new_vmcores = self.get_new_vmcores()
        if not new_vmcores:
            if self.test:
                self.test.fail("vmcore not generated in %s" % self.vm.name)

    def setup_crash_utility(self):
        """
        Install crash utility and debug packages.
        """
        ensure_crash_utility_packages(
            self.vm,
            self._get_distro_info(),
            install_missing=self.install_missing_packages,
            upstream_kernel=self.upstream_kernel,
            test=self.test,
        )

    def analyze_vmcore(self, vmcore_file=None):
        """
        Analyze vmcore with crash utility.

        :param vmcore_file: Path to vmcore file (uses latest new vmcore if None)
        :raises: TestFail if crash utility cannot analyze vmcore
        """
        if vmcore_file is None:
            new_vmcores = self.get_new_vmcores()
            if not new_vmcores:
                if self.test:
                    self.test.fail(
                        "No new vmcore available to analyze in %s" % self.vm.name
                    )
                return
            vmcore_file = new_vmcores[-1]

        vmlinux_path = None
        if self.upstream_kernel:
            vmlinux_path = self.upstream_kernel_vmlinux

        analyze_vmcore_with_crash(
            self.vm,
            self._get_distro_info(),
            vmcore_file,
            upstream_kernel=self.upstream_kernel,
            vmlinux_path=vmlinux_path,
            test=self.test,
        )
