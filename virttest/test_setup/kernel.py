from virttest import arch, utils_kernel_module
from virttest.test_setup.core import Setuper


class ReloadKVMModules(Setuper):
    def __init__(self, test, params, env):
        super().__init__(test, params, env)
        self.kvm_module_handlers = []

    def setup(self):
        kvm_modules = arch.get_kvm_module_list()
        for module in reversed(kvm_modules):
            param_prefix = module if module == "kvm" else "kvm_probe"
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
            kvm_module.restore()
