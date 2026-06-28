"""

SUMMARY
------------------------------------------------------
Sample test suite GET tutorial -- *Complex test dependencies*

Copyright: Intra2net AG


INTERFACE
------------------------------------------------------

"""

import time
import os
import logging

# avocado imports
from avocado.core import exceptions

# custom imports
from sample_utility import sleep


log = logging.getLogger('avocado.test.log')


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
    vmnet.start_all_sessions()
    vms = vmnet.get_vms()
    temporary = vms.temporary
    permanent = vms.permanent

    log.info(temporary.session.cmd_output("uptime"))
    log.info(temporary.session.cmd_output("cat /etc/os-release"))

    log.info(permanent.session.cmd_output("uptime"))
    log.info(permanent.session.cmd_output("cat /etc/os-release"))

    # call to a function shared among tests
    sleep(3)

    log.info("Test passed.")
