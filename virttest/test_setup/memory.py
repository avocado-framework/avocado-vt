from virttest import test_setup, utils_libvirtd
from virttest.test_setup.core import Setuper


class HugePagesSetup(Setuper):
    def __init__(self, test, params, env):
        super().__init__(test, params, env)
        # default num of surplus hugepages, in order to compare the values
        # before and after the test when 'setup_hugepages = yes'
        self._pre_hugepages_surp = 0

    def setup(self):
        # If guest is configured to be backed by hugepages, setup hugepages in host
        if self.params.get("hugepage") == "yes":
            self.params["setup_hugepages"] = "yes"
        if self.params.get("setup_hugepages") == "yes":
            h = test_setup.HugePageConfig(self.params)
            self._pre_hugepages_surp = h.ext_hugepages_surp
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
            post_hugepages_surp = h.ext_hugepages_surp
            if post_hugepages_surp > self._pre_hugepages_surp:
                leak_num = post_hugepages_surp - self._pre_hugepages_surp
                raise test_setup.HugePagesLeakError("%d huge pages leaked!" % leak_num)
