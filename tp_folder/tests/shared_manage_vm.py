"""

SUMMARY
------------------------------------------------------
Perform vm management functions like booting, running a code on the guest,
rebooting or shutting down a vm.

Copyright: Intra2net AG


INTERFACE
------------------------------------------------------

"""

import time
import os
import logging

# avocado imports
from aexpect import remote_door as door
from avocado.core import exceptions
from virttest import error_context
from avocado_i2n.states import setup as ss

# custom imports
pass


log = logging.getLogger('avocado.test.log')


###############################################################################
# TEST MAIN
###############################################################################


@error_context.context_aware
def run(test, params, env):
    """
    Main test run.

    :param test: test object
    :type test: :py:class:`avocado_vt.test.VirtTest`
    :param params: extended dictionary of parameters
    :type params: :py:class:`virttest.utils_params.Params`
    :param env: environment object
    :type env: :py:class:`virttest.utils_env.Env`
    """
    vmnet = env.get_vmnet()

    if params.get("vm_action", "run") == "boot":
        vmnet.start_all_sessions()
    elif params.get("vm_action", "run") == "run":
        for vm in vmnet.get_ordered_vms():
            if params.get("os_type", "linux") in ["windows"]:
                raise exceptions.TestError(f"Cannot run control files on an {params['os_type']} vm")
            if vm.name == params.get("main_vm"):
                session = vmnet.nodes[vm.name].get_session()
                door.SRC_CONTROL_DIR = os.path.join(vm.params["original_test_data_path"], "..", "controls")
                door.DUMP_CONTROL_DIR = test.logdir
                logging.info("Running custom control file on %s", vm.name)
                control_path = door.set_subcontrol_parameter_object(vm.params["control_file"], "virttest.utils_params.Params", vm.params)
                door.run_subcontrol(session, control_path)
                extra_timeout = int(params.get("extra_timeout", "0"))
                logging.info("Parameters will be available for extra %s seconds", extra_timeout)
                time.sleep(extra_timeout)
                break
    elif params.get("vm_action", "run") == "download":
        if params.get("os_type", "linux") in ["android"]:
            raise NotImplementedError("No data exchange is currently possible for Android")
        for vm in vmnet.get_ordered_vms():
            to_dir = os.path.join(test.logdir)
            for f in vm.params.objects("files"):
                log.info(f"Downloading {f} to {to_dir} ({vm.name})")
                vm.copy_files_from(f, to_dir, timeout=30)
    elif params.get("vm_action", "run") == "upload":
        if params.get("os_type", "linux") in ["android"]:
            raise NotImplementedError("No data exchange is currently possible for Android")
        for vm in vmnet.get_ordered_vms():
            to_dir = vm.params["tmp_dir"]
            for f in vm.params.objects("files"):
                log.info(f"Uploading {f} to {to_dir} ({vm.name})")
                vm.copy_files_to(f, to_dir, timeout=30)
    elif params.get("vm_action", "run") == "shutdown":
        vmnet.start_all_sessions()
        for vm in vmnet.get_ordered_vms():
            vm.destroy(gracefully=True)

    # state manipulation
    elif params.get("vm_action", "run") == "check":
        log.info(f"Checking {params['main_vm']}'s (and its images') states")
        ss.check_states(params, env)
    elif params.get("vm_action", "run") == "push":
        log.info(f"Pushing {params['main_vm']}'s (and its images') states")
        ss.push_states(params, env)
    elif params.get("vm_action", "run") == "pop":
        log.info(f"Popping {params['main_vm']}'s (and its images') states")
        ss.pop_states(params, env)
    elif params.get("vm_action", "run") in ["get", "set"]:
        # these operations are performed automatically by the environment process
        log.info(f"{params['vm_action'].title()}ting {params['main_vm']}'s (and its images') states")
    elif params.get("vm_action", "run") == "unset":
        log.info(f"Unsetting {params['main_vm']}'s (and its images') states")
        ss.unset_states(params, env)
