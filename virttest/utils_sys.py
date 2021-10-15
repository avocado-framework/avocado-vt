"""
Virtualization test utility functions.

:copyright: 2021 Red Hat Inc.
"""

import logging
import re

from avocado.utils import process

LOG = logging.getLogger('avocado.' + __name__)


# TODO: check function in avocado.utils after the next LTS
def check_dmesg_output(pattern, expect=True, session=None):
    """
    Check whether certain pattern exists in dmesg.

    :param pattern: pattern to search in dmesg
    :param expect: True if expect to exist, False if not
    :param session: session of vm to be checked
    :return: True if result met expectation, False if not met
    """
    dmesg_cmd = 'dmesg'
    func_get_dmesg = session.cmd if session else process.run
    dmesg = func_get_dmesg(dmesg_cmd)

    prefix = '' if expect else 'Not '
    LOG.info('%sExpecting pattern: "%s".', prefix, pattern)

    # Search for pattern
    found = bool(re.search(pattern, dmesg))
    log_content = ('' if found else 'Not') + 'Found "%s"' % pattern
    LOG.debug(log_content)

    if found ^ expect:
        LOG.error('Dmesg output does not meet expectation.')
        return False
    else:
        LOG.info('Dmesg output met expectation')
        return True
