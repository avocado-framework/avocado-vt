import logging

from virttest import virt_vm
from virttest.test_setup.core import Setuper

LOG = logging.getLogger(__name__)


class UnrequestedVMHandler(Setuper):
    def setup(self):
        # Destroy and remove VMs that are no longer needed in the environment or
        # leave them untouched if they have to be disregarded only for this test
        requested_vms = self.params.objects("vms")
        keep_unrequested_vms = self.params.get_boolean("keep_unrequested_vms", False)
        kill_unrequested_vms_gracefully = self.params.get_boolean(
            "kill_unrequested_vms_gracefully", True
        )
        for key in list(self.env.keys()):
            vm = self.env[key]
            if not isinstance(vm, virt_vm.BaseVM):
                continue
            if vm.name not in requested_vms:
                if keep_unrequested_vms:
                    LOG.debug(
                        "The vm %s is registered in the env and disregarded "
                        "in the current test",
                        vm.name,
                    )
                else:
                    vm.destroy(gracefully=kill_unrequested_vms_gracefully)
                    del self.env[key]

    def cleanup(self):
        pass
