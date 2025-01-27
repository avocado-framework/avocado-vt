"""
Simple service handling test

Please put the configuration file service.cfg into $tests/cfg/ directory.

:difficulty: advanced
:copyright: 2014 Red Hat Inc.
"""

import logging
import time

from avocado.core import exceptions
from avocado.utils import process
from avocado.utils.service import SpecificServiceManager

from virttest import error_context, remote

LOG = logging.getLogger("avocado.vt.examples.service")


# error_context.context_aware decorator initializes context, which provides additional
# information on exceptions.
@error_context.context_aware
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
    if params.get("test_on_guest") == "yes":
        # error_context.context() is common method to log test steps used to verify
        # what exactly was tested.
        error_context.context("Using guest.", LOG.info)
        vm = env.get_vm(params["main_vm"])
        session = vm.wait_for_login()
        # RemoteRunner is object, which simulates the utils.run() behavior
        # on remote consoles
        runner = remote.RemoteRunner(session=session).run
    else:
        error_context.context("Using host", LOG.info)
        runner = process.run

    error_context.context("Initialize service manager", LOG.info)
    service = SpecificServiceManager(params["test_service"], runner)

    error_context.context("Testing service %s" % params["test_service"], LOG.info)
    original_status = service.status()
    LOG.info("Original status=%s", original_status)

    if original_status is True:
        service.stop()
        time.sleep(5)
        if service.status() is not False:
            LOG.error("Fail to stop service")
            service.start()
            raise exceptions.TestFail("Fail to stop service")
        service.start()
    else:
        service.start()
        time.sleep(5)
        if service.status() is not True:
            LOG.error("Fail to start service")
            service.stop()
            raise exceptions.TestFail("Fail to start service")
        service.start()
    time.sleep(5)
    if not service.status() is original_status:
        raise exceptions.TestFail(
            "Fail to restore original status of the %s "
            "service" % params["test_service"]
        )
