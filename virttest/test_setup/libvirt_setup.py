from virttest import test_setup
from virttest.test_setup.core import Setuper


class LibvirtdDebugLogConfig(Setuper):
    def setup(self):
        if (
            self.params.get("vm_type") == "libvirt"
            and self.params.get("enable_libvirtd_debug_log", "yes") == "yes"
        ):
            # By default log the info level
            log_level = self.params.get("libvirtd_debug_level", "2")
            log_file = self.params.get("libvirtd_debug_file", "")
            log_filters = self.params.get("libvirtd_debug_filters", f"{log_level}:*")
            log_permission = self.params.get("libvirtd_log_permission")
            libvirtd_debug_log = test_setup.LibvirtdDebugLog(
                self.test, log_level, log_file, log_filters, log_permission
            )
            libvirtd_debug_log.enable()

    def cleanup(self):
        if (
            self.params.get("vm_type") == "libvirt"
            and self.params.get("enable_libvirtd_debug_log", "yes") == "yes"
        ):
            libvirtd_debug_log = test_setup.LibvirtdDebugLog(self.test)
            libvirtd_debug_log.disable()
