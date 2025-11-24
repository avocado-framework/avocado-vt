# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>

import logging

from virttest.vt_utils import cpu

LOG = logging.getLogger("avocado.service." + __name__)


def get_cpu_vendor_id():
    return cpu.get_cpu_vendor_id()


def get_cpu_model_name():
    return cpu.get_cpu_model_name()
