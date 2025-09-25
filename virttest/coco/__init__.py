# Confidential Computing (CoCo) module for avocado-vt
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; specifically version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat (c) 2025
# Author: Yihuang Yu <yihyu@redhat.com>


import logging

from avocado.utils import cpu as utils

from virttest.cpu import UnsupportedCPU, cpuid

LOG = logging.getLogger("avocado." + __name__)


def get_amd_cbit_position():
    """
    Get AMD C-bit position for memory encryption

    This function checks if the CPU supports SEV (Secure Encrypted Virtualization)
    and returns the C-bit position used for memory encryption.

    :return: C-bit position (0-63)
    :raises: UnsupportedCPU if not an AMD CPU, CPU doesn't support required
             extended CPUID leaf, or SEV is not supported
    """
    if utils.get_vendor() != "amd":
        raise UnsupportedCPU("C-bit detection only supported on AMD CPU")

    # Check maximum extended leaf
    eax, _, _, _ = cpuid(0x80000000)
    if eax < 0x8000001F:
        raise UnsupportedCPU("CPU does not support extended leaf 0x8000001f")

    # Query SEV/SME features
    eax, ebx, _, _ = cpuid(0x8000001F)

    # Check SEV support bit (EAX bit 1)
    if (eax & 2) == 0:
        raise UnsupportedCPU("CPU does not support SEV")

    # Extract C-bit position (lower 6 bits of EBX) with additional validation
    cbit_position = ebx & 0x3F
    LOG.debug("AMD C-bit position: %d", cbit_position)
    return cbit_position
