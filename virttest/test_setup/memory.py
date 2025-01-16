from virttest import env_process, test_setup, utils_libvirtd
from virttest.test_setup.core import Setuper


class HugePagesSetup(Setuper):
    def setup(self):
        # If guest is configured to be backed by hugepages, setup hugepages in host
        if self.params.get("hugepage") == "yes":
            self.params["setup_hugepages"] = "yes"
        if self.params.get("setup_hugepages") == "yes":
            h = test_setup.HugePageConfig(self.params)
            env_process._pre_hugepages_surp = h.ext_hugepages_surp
            suggest_mem = h.setup()
            if suggest_mem is not None:
                self.params["mem"] = suggest_mem
            if not self.params.get("hugepage_path"):
                self.params["hugepage_path"] = h.hugepage_path
            if self.params.get("vm_type") == "libvirt":
                utils_libvirtd.Libvirtd().restart()

    def cleanup(self):
        if self.params.get("setup_hugepages") == "yes":
            h = test_setup.HugePageConfig(self.params)
            h.cleanup()
            if self.params.get("vm_type") == "libvirt":
                utils_libvirtd.Libvirtd().restart()
            env_process._post_hugepages_surp = h.ext_hugepages_surp
