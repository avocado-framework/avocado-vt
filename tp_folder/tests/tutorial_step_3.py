"""

SUMMARY
------------------------------------------------------
Sample test suite tutorial pt. 3 -- *Multi-VM example*

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
This part of the tutorial validates deployed packages in multiple virtual
machines. It could then be extended to any client-server protocol once
the connectivity between the vm is established with a vm network ping.


INTERFACE
------------------------------------------------------

"""

import time
import os
import logging

# avocado imports
from avocado.core import exceptions
from virttest import error_context
try:
    from aexpect import remote_door as door
    DOOR_AVAILABLE = True
except ImportError:
    log.warning("The remote door of an upgraded aexpect package is not available")
    import types
    door = types.ModuleType('door')
    door.run_remotely = lambda x: x
    DOOR_AVAILABLE = False

# custom imports
from sample_utility import sleep


log = logging = logging.getLogger('avocado.test.log')


###############################################################################
# HELPERS
###############################################################################


@door.run_remotely
def check_walk(params):
    """
    Asserts that a given file is in the test prefix using python `walk`.

    :param params: extended dictionary of parameters
    :type params: {str, str}
    """
    # This function is run remotely where we use a generic logging module
    logging.info("Enter tutorial test variant two: check else.")
    walk_prefix = params["walk_prefix"]
    walk_goal = params["must_exist_in_walk"]

    # This code is ran remotely so no imports on the host are valid
    import os
    for base_path, dir_names, file_names in os.walk(walk_prefix):
        if walk_goal in file_names:
            break
    else:
        # we cannot raise exception classes from imports that are not available remotely
        raise AssertionError("Couldn't find %s inside %s" % (walk_goal, walk_prefix))


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
    error_context.context("network configuration")
    vmnet = env.get_vmnet()
    vmnet.start_all_sessions()
    vms = vmnet.get_vms()
    server_vm = vms.server
    client_vm = vms.client
    vmnet.ping_all()

    # call to a function shared among tests
    sleep(3)

    error_context.context("misc commands on each vm")
    tmp_server = server_vm.session.cmd("ls " + server_vm.params["tmp_dir"])
    tmp_client = client_vm.session.cmd("dir " + client_vm.params["tmp_dir"])
    log.info(f"Content of temporary server folder:\n{tmp_server}")
    log.info(f"Content of temporary client folder:\n{tmp_client}")
    deployed_folders = ("utils", "packages")
    for folder in deployed_folders:
        if folder not in tmp_server:
            raise exceptions.TestFail("No deployed %s was found on the server" % folder)
        if folder not in tmp_client:
            raise exceptions.TestFail("No deployed %s was found on the client" % folder)

    error_context.context("enhanced remote checks")
    if params.get_boolean("enhanced_remote_checks"):
        # Another way to run remote commands is through the host -> guest door,
        # which provides us with different functions to share code between
        # the host machine and a guest virtual machine (vm).
        if not DOOR_AVAILABLE:
            raise exceptions.TestSkipError("The remote door of an upgraded aexpect package is not available")
        door.DUMP_CONTROL_DIR = test.logdir
        door.REMOTE_PYTHON_BINARY = "python3.6"

        # The most advanced remote methods require serialization backend.
        serialization_cmd = door.REMOTE_PYTHON_BINARY + " -c 'import Pyro5'"
        guest_serialization = server_vm.session.cmd_status(serialization_cmd) == 0
        if not guest_serialization:
            logging.warning("The remote door object backend not found on guest")
        try:
            import Pyro5
        except ImportError:
            logging.warning("The remote door object backend not found on host")
            host_serialization = False
        else:
            host_serialization = True

        # The simplest remote execution we can perform is through a single call to
        # a utility or module. Under the hood, this is similar to running a
        # python script on the vm with just a few lines importing the module or
        # utility and calling its desired function.
        if params.get_boolean("remote_util_check"):
            door.run_remote_util(
                server_vm.session,
                "os",
                "listdir",
                server_vm.params["tmp_dir"].replace("\\", r"\\"),
            )
            # Note that the usage of `shell=True` is here because `run_remote_util`
            # doesn't support array serialization. However, `shell=True` should be
            # avoided in real test scripts.
            door.run_remote_util(
                server_vm.session,
                "subprocess",
                "call",
                "dir " + client_vm.params["tmp_dir"].replace("\\", r"\\"),
                shell=True
            )

        # A bit more flexible way to run code on the vm is using a decorated
        # function with multiple locally written but remotely executed lines.
        if params.get_boolean("remote_decorator_check"):
            check_walk(server_vm.session, params)

        # One advanced but last resort method is to use a control file which is
        # a file where the remote code is written and deployed to the vm. This
        # is also used internally for both previous methods.
        if params.get_boolean("remote_control_check"):
            # With a bit of metaprogramming, we can set single parameters, lists, or
            # dicts for one time use by th control file.
            control_path = server_vm.params["control_file"]
            control_path = door.set_subcontrol_parameter(control_path, "EXTRA_SLEEP", 2)
            control_path = door.set_subcontrol_parameter(control_path, "ROOT_DIR", params["root_dir"])
            control_path = door.set_subcontrol_parameter_list(control_path, "DETECT_DIRS", ["utils", "packages"])
            control_path = door.set_subcontrol_parameter_dict(control_path, "SIMPLE_PARAMS",
                                                              {"client": server_vm.params["client"],
                                                               "server": server_vm.params["server"]})
            door.run_subcontrol(server_vm.session, control_path)
            # It becomes more intricate but possible to share the Cartesian
            # configuration between the host test and the control file and thus
            # allowing for return arguments from the control but we need a remote
            # object backend as additional satisfied dependency.
            if host_serialization and guest_serialization:
                log.info("Performing extra hostname check using shared parameters control")
                control_path = server_vm.params["control_file"].replace("step_3", "step_3.2")
                control_path = door.set_subcontrol_parameter_object(control_path,
                                                                    "virttest.utils_params.Params",
                                                                    server_vm.params)
                door.run_subcontrol(server_vm.session, control_path)
                failed_checks = server_vm.params["failed_checks"]
                if failed_checks > 0:
                    raise exceptions.TestFail("%s hostname checks failed" % failed_checks)

        # The highest complexity but most permanent approach (supports multiple
        # calls switching back and forth from guest to host) is using a remote
        # object and serializing the calls in the background. This is the most
        # flexible approach and a bit less complex than using controls but might
        # require an additional dependency as a backend implementation for the
        # remote objects (we usually use pyro and pickle or serpent serializers).
        if params.get_boolean("remote_object_check"):
            if not guest_serialization or not host_serialization:
                raise exceptions.TestSkipError("The remote door object backend (pyro) is not available")
            sysmisc = door.get_remote_object("sample_utility",
                                             session=server_vm.wait_for_login(),
                                             host=server_vm.params["ip_" + server_vm.params["ro_nic"]],
                                             port=server_vm.params["ro_port"])
            sysmisc.sleep(5)

    log.info("It would appear that the test terminated in a civilized manner.")
