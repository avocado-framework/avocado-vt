"""
Simple service handling test

Please put the configuration file service.cfg into $tests/cfg/ directory.

:difficulty: advanced
:copyright: 2014 Red Hat Inc.
"""
import logging
import time

from autotest.client import utils
from autotest.client.shared import error
from autotest.client.shared.service import SpecificServiceManager
from virttest import remote


# error.context_aware decorator initializes context, which provides additional
# information on exceptions.
@error.context_aware
def run(test, params, env):
    """
    Logs guest's hostname.
    1) Decide whether use host/guest
    2) Check current service status
    3) Start (Stop) $service
    4) Check status of $service
    5) Stop (Start) $service
    6) Check service status

    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    if params.get('test_on_guest') == "yes":
        # error.context() is common method to log test steps used to verify
        # what exactly was tested.
        error.context("Using guest.", logging.info)
        vm = env.get_vm(params["main_vm"])
        session = vm.wait_for_login()
        # RemoteRunner is object, which simulates the utils.run() behavior
        # on remote consoles
        runner = remote.RemoteRunner(session=session).run
    else:
        error.context("Using host", logging.info)
        runner = utils.run

    error.context("Initialize service manager", logging.info)
    service = SpecificServiceManager(params["test_service"], runner)

    error.context("Testing service %s" % params["test_service"], logging.info)
    original_status = service.status()
    logging.info("Original status=%s", original_status)

    if original_status is True:
        service.stop()
        time.sleep(5)
        if service.status() is not False:
            logging.error("Fail to stop service")
            service.start()
            raise error.TestFail("Fail to stop service")
        service.start()
    else:
        service.start()
        time.sleep(5)
        if service.status() is not True:
            logging.error("Fail to start service")
            service.stop()
            raise error.TestFail("Fail to start service")
        service.start()
    time.sleep(5)
    if not service.status() is original_status:
        raise error.TestFail("Fail to restore original status of the %s "
                             "service" % params["test_service"])
