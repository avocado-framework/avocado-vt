"""

SUMMARY
------------------------------------------------------
Sample test suite tutorial pt. 1 -- *Easy test example*

Copyright: Intra2net AG


INTERFACE
------------------------------------------------------

"""

import random
import logging

# avocado imports
from avocado.core import exceptions


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
    log.info("Running minimal tutorial test.")

    # Get the VM Network object for this test
    vmnet = env.get_vmnet()

    # Get a session to the only VM in the network.
    # This VM is the one available for tests within the quicktest variant
    _, session = vmnet.get_single_vm_with_session()

    log.info("Writing to a sample file.")

    # Get the content to write to the file from the cartesian configuration
    contents_to_write = params.get("file_contents", "some content")

    # Create the file on the remote VM and writing to it
    # by invoking a shell command remotely
    session.cmd("echo %s > /root/sample.txt" % contents_to_write)

    log.info("Fetching file contents.")

    # Read the file we've previously written
    contents_written = session.cmd_output("cat /root/sample.txt").strip()

    if contents_written != contents_to_write:
        raise exceptions.TestFail(
            "File contents (%s) differs from the expected (%s)."
            % (contents_to_write, contents_written)
        )
