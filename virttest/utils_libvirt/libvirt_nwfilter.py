"""
Accommodate libvirt nwfilter utility functions.

:copyright: 2020 Red Hat Inc.
"""

import logging

from virttest import virsh


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
    logging.info("existed nwfilter binding list is: %s", result)
    for binding_uuid in result:
        virsh.nwfilter_binding_delete(binding_uuid, ignore_status=ignore_status)
