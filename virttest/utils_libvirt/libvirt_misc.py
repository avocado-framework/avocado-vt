"""
Virtualization test - utility functions for libvirt

:copyright: 2021 Red Hat Inc.
"""

import re
import logging

LOG = logging.getLogger('avocado.' + __name__)


def convert_to_dict(content, pattern=r'(\d+) +(\S+)'):
    """
    Put the content into a dict according to the pattern.

    :param content: str, the string to be parsed
    :param pattern: str, regex for parsing the command output
    :return: dict, the dict contains matched result
    """

    info_dict = {}
    info_list = re.findall(pattern, content, re.M)
    for info in info_list:
        info_dict[info[0]] = info[1]
    LOG.debug("The dict converted is:\n%s", info_dict)
    return info_dict
