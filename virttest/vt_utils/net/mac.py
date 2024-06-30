# Library for the mac address related functions.
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
# Copyright: Red Hat (c) 2024 and Avocado contributors
# Author: Houqi Zuo <hzuo@redhat.com>
from virttest.vt_utils import tool


def generate_mac_address_simple():
    """
    Generate a random mac address.

    :return: A random mac address.
    :rtype: String.
    """
    ieee_eui8_assignment = tool.ieee_eui_assignment(8)(0, repeat=False)
    mac = "9a:%02x:%02x:%02x:%02x:%02x" % (
        next(ieee_eui8_assignment),
        next(ieee_eui8_assignment),
        next(ieee_eui8_assignment),
        next(ieee_eui8_assignment),
        next(ieee_eui8_assignment),
    )
    return mac
