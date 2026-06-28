"""

SUMMARY
------------------------------------------------------
Run the steps necessary to make virtual user software run on Windows.

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
pass


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
    vm, session = vmnet.get_single_vm_with_session()

    log.info("Making virtual user software available on the vm")
    try:
        from guibot import GuiBot
        from guibot.config import GlobalConfig
        from guibot.controller import QemuController, VNCDoToolController
    except ImportError:
        # we would typically raise test error here to cancel all dependent tests
        # but we want the test suite to skip tests in the best case
        log.warning("No virtual user backend found")
    log.info("...some setup steps on windows")

    log.info("Virtual user is ready to manipulate the vm from a screen")
    log.info("\nFor more details check https://guibot.org")
