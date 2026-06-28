"""

SUMMARY
------------------------------------------------------
Run the steps necessary to make sure a vm has internet access.

Copyright: Intra2net AG


INTERFACE
------------------------------------------------------

"""

import time
import os

# avocado imports
from avocado.core import exceptions

# custom imports
pass


###############################################################################
# TEST MAIN
###############################################################################


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
    vm, session = vmnet.get_single_vm_with_session()

    vmnet.ping_all()
    if vm.params["os_variant"] == "centos":
        session.cmd("pip3 install Pyro5")
    else:
        test.log.info(f"No remote support for OS variant {vm.params['os_variant']}")
