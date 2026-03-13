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

    def _parse_ignored_params(self, ignored_params):
        """
        Parse ignored parameters string into a list of 'key=value' pairs.

        :param ignored_params: string contains parameters to ignore
        :return: list of 'key=value' strings
        """
        ignored_list = []
        if not ignored_params:
            return ignored_list

        pattern = r'(\w+)=(?:["\']([^"\']*)["\']|(.*?))(?=\s+\w+=|$)'
        matches = re.findall(pattern, ignored_params)
        ignored_list = ["%s=%s" % (k, (q or u).strip()) for k, q, u in matches]
        return ignored_list

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
            module_ignored_parameters = self.params.get(
                "%s_module_ignored_parameters" % param_prefix
            )
            ignored_list = self._parse_ignored_params(module_ignored_parameters)
            kvm_module.restore(ignored_list)


class KSMSetup(Setuper):
    def setup(self):
        if self.params.get("setup_ksm") == "yes":
            ksm = test_setup.KSMConfig(self.params, self.env)
            ksm.setup(self.env)

    def cleanup(self):
        if self.params.get("setup_ksm") == "yes":
            ksm = test_setup.KSMConfig(self.params, self.env)
            ksm.cleanup(self.env)
