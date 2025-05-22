from virttest import test_setup
from virttest.test_setup.core import Setuper


class EGDSetup(Setuper):
    def setup(self):
        if self.params.get("setup_egd") == "yes":
            egd = test_setup.EGDConfig(self.params, self.env)
            egd.setup()

    def cleanup(self):
        if (
            self.params.get("setup_egd") == "yes"
            and self.params.get("kill_vm") == "yes"
        ):
            egd = test_setup.EGDConfig(self.params, self.env)
            egd.cleanup()
