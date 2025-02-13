"""
Simple bad test.

:difficulty: simple
:copyright: 2014 Red Hat Inc.
"""

from avocado.utils import process


def run(test, params, env):
    """
    Executes missing_command which, in case it's not present, should raise
    exception providing information about this failure.

    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    process.run("missing_command")
