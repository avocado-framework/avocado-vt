import logging

from avocado.utils import cpu as cpu_utils
from avocado.utils import process as a_process

from virttest import test_setup
from virttest.test_setup.core import Setuper

LOG = logging.getLogger(__name__)


class SwitchSMTOff(Setuper):
    def setup(self):
        # For KVM to work in Power8 and Power9(compat guests)(<DD2.2)
        # systems we need to have SMT=off and it needs to be
        # done as root, here we do a check whether
        # we satisfy that condition, if not try to make it off
        # otherwise throw TestError with respective error message
        cpu_family = "unknown"
        try:
            cpu_family = (
                cpu_utils.get_family()
                if hasattr(cpu_utils, "get_family")
                else cpu_utils.get_cpu_arch()
            )
        except Exception:
            LOG.warning("Could not get host cpu family")
        if cpu_family is not None and "power" in str(cpu_family):
            pvr_cmd = "grep revision /proc/cpuinfo | awk '{print $3}' | head -n 1"
            pvr = float(a_process.system_output(pvr_cmd, shell=True).strip())
            power9_compat = "yes" == self.params.get("power9_compat", "no")

            if "power8" in cpu_family:
                test_setup.switch_smt(state="off")
            elif "power9" in cpu_family and power9_compat and pvr < 2.2:
                test_setup.switch_indep_threads_mode(state="N")
                test_setup.switch_smt(state="off")

    def cleanup(self):
        cpu_family = "unknown"
        try:
            cpu_family = (
                cpu_utils.get_family()
                if hasattr(cpu_utils, "get_family")
                else cpu_utils.get_cpu_arch()
            )
        except Exception:
            LOG.warning("Could not get host cpu family")
        if cpu_family is not None and "power" in str(cpu_family):
            pvr_cmd = "grep revision /proc/cpuinfo | awk '{print $3}' | head -n 1"
            pvr = float(a_process.system_output(pvr_cmd, shell=True).strip())
            # Restore SMT changes in the powerpc host is set
            if self.params.get("restore_smt", "no") == "yes":
                power9_compat = "yes" == self.params.get("power9_compat", "no")
                if "power9" in cpu_family and power9_compat and pvr < 2.2:
                    test_setup.switch_indep_threads_mode(state="Y")
                    test_setup.switch_smt(state="on")
