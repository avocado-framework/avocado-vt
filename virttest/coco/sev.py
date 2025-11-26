# AMD SEV specific confidential computing helper functions
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


def _get_mem_encryption_features():
    """
    Get AMD memory encryption CPUID features (internal helper)

    Query CPUID leaf 0x8000001F for SME/SEV memory encryption features.

    :return: Tuple of (eax, ebx, ecx, edx) register values from CPUID 0x8000001F
    :raises: UnsupportedCPU if not an AMD CPU, CPU doesn't support required
             extended CPUID leaf, or SME/SEV is not supported
    """
    if utils.get_vendor() != "amd":
        raise UnsupportedCPU("AMD memory encryption only supported on AMD CPU")

    # Check maximum extended leaf
    eax, _, _, _ = cpuid(0x80000000)
    if eax < 0x8000001F:
        raise UnsupportedCPU("CPU does not support extended leaf 0x8000001f")

    # Query SEV/SME features
    eax, ebx, ecx, edx = cpuid(0x8000001F)

    # Check SME or SEV support (EAX bit 0 or bit 1)
    if (eax & 0x3) == 0:
        raise UnsupportedCPU("CPU does not support SME or SEV")

    return eax, ebx, ecx, edx


def get_cbit_position():
    """
    Get C-bit position for memory encryption

    This function checks if the CPU supports SME/SEV and returns the C-bit
    position used for memory encryption.

    :return: C-bit position (0-63)
    :raises: UnsupportedCPU if not an AMD CPU, CPU doesn't support required
             extended CPUID leaf, or SME/SEV is not supported
    """
    _, ebx, _, _ = _get_mem_encryption_features()

    # Extract C-bit position (lower 6 bits of EBX)
    cbit_position = ebx & 0x3F
    return cbit_position


def get_reduced_phys_bits():
    """
    Get physical address bits reduced by memory encryption

    This function checks if the CPU supports SME/SEV and returns the number
    of physical address bits reduced due to encryption metadata overhead.

    :return: Number of physical address bits reduced (0-63)
    :raises: UnsupportedCPU if not an AMD CPU, CPU doesn't support required
             extended CPUID leaf, or SME/SEV is not supported
    """
    _, ebx, _, _ = _get_mem_encryption_features()

    # Extract reduced physical address bits (bits [11:6] of EBX)
    reduced_bits = (ebx >> 6) & 0x3F
    return reduced_bits


def is_sev_snp_supported():
    """
    Check if AMD SEV-SNP (Secure Nested Paging) is supported.

    :return: True if SEV-SNP is supported, False otherwise
    """
    try:
        eax, _, _, _ = _get_mem_encryption_features()
        # Check SEV-SNP support bit (EAX bit 4)
        return bool(eax & (1 << 4))
    except UnsupportedCPU:
        return False
