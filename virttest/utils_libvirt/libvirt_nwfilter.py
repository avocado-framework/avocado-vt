"""
Accommodate libvirt nwfilter utility functions.

:copyright: 2020 Red Hat Inc.
"""

import logging
import re

from virttest import virsh

LOG = logging.getLogger('avocado.' + __name__)


def clean_up_nwfilter_binding(ignore_status=False):
    """
    Clean up existed nwfilter binding.

    :param ignore_status: default value True to allow silent failure.
    """
    cmd_result = virsh.nwfilter_binding_list(debug=True)
    binding_list = cmd_result.stdout_text.strip().splitlines()
    binding_list = binding_list[2:]
    result = []
    # If binding list is not empty.
    if binding_list:
        for line in binding_list:
            # Split on whitespace, assume 1 column
            linesplit = line.split(None, 1)
            result.append(linesplit[0])
    LOG.info("existed nwfilter binding list is: %s", result)
    for binding_uuid in result:
        virsh.nwfilter_binding_delete(binding_uuid, ignore_status=ignore_status)


def get_nwfilter_list():
    """
    Get nwfilter list in tuple(UUID, Name)

    Usage:
         Native virsh nwfilter-list output as below:
         # virsh nwfilter-list
         UUID                                  Name
         --------------------------------------------------
         5c79e80b-cfb5-46d0-9490-77db3318a4b5  allow-arp
         d8150f0b-2859-4049-a58d-963f33c59aa4  allow-dhcp
         ...
        get_nwfilter_list() will parse the output as one list something like:
        [('5c79e80b-cfb5-46d0-9490-77db3318a4b5, allow-arp'), ('d8150f0b-2859-4049-a58d-963f33c59aa4', 'allow-dhcp')]
    """
    cmd_result = virsh.nwfilter_list(debug=True)
    nwfilter_list = re.findall(r"(\S+)\ +(\S+)", cmd_result.stdout_text.strip())
    index = nwfilter_list.index(('UUID', 'Name'))
    nwfilter_list = nwfilter_list[index+1:]
    return nwfilter_list
