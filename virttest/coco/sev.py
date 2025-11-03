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

from virttest.cpu import cpuid

LOG = logging.getLogger("avocado." + __name__)


def is_sev_snp_supported():
    """
    Check if AMD SEV-SNP (Secure Nested Paging) is supported.

    :return: True if SEV-SNP is supported, False otherwise
    """
    try:
        if utils.get_vendor() != "amd":
            return False

        # Check maximum extended leaf
        eax, _, _, _ = cpuid(0x80000000)
        if eax < 0x8000001F:
            return False

        # Query SEV/SME features
        eax, _, _, _ = cpuid(0x8000001F)

        # Check SEV-SNP support bit (EAX bit 4)
        return bool(eax & (1 << 4))
    except Exception:
        return False
