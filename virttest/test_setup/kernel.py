import re

from virttest import arch, test_setup, utils_kernel_module
from virttest.test_setup.core import Setuper


class ReloadKVMModules(Setuper):
    def __init__(self, test, params, env):
        super().__init__(test, params, env)
        self.kvm_module_handlers = []

    def _get_param_prefix(self, module_name):
        """Determine parameter prefix based on module name."""
        return "kvm" if module_name == "kvm" else "kvm_probe"

    def setup(self):
        kvm_modules = arch.get_kvm_module_list()
        for module in reversed(kvm_modules):
            param_prefix = self._get_param_prefix(module)
            module_force_load = self.params.get_boolean(
                "%s_module_force_load" % param_prefix
            )
            module_parameters = self.params.get(
                "%s_module_parameters" % param_prefix, ""
            )
            module_handler = utils_kernel_module.reload(
                module, module_force_load, module_parameters
            )
            if module_handler is not None:
                self.kvm_module_handlers.append(module_handler)

    def cleanup(self):
        for kvm_module in self.kvm_module_handlers:
            param_prefix = self._get_param_prefix(kvm_module.module_name)
            ignored_dict = self.params.get_dict(
                "%s_module_ignored_parameters" % param_prefix, delimiter=";"
            )
            kvm_module.restore(ignored_dict)


class KSMSetup(Setuper):
    def setup(self):
        if self.params.get("setup_ksm") == "yes":
            ksm = test_setup.KSMConfig(self.params, self.env)
            ksm.setup(self.env)

    def cleanup(self):
        if self.params.get("setup_ksm") == "yes":
            ksm = test_setup.KSMConfig(self.params, self.env)
            ksm.cleanup(self.env)
