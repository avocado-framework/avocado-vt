"""
Simple bad test.

:difficulty: simple
:copyright: 2014 Red Hat Inc.
"""
from autotest.client import utils


def run(test, params, env):
    """
    Executes missing_command which, in case it's not present, should raise
    exception providing information about this failure.

    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    utils.run("missing_command")
