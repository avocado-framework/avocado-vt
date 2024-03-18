#
# library for time related helper functions
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
# Copyright: Red Hat (c) 2023 and Avocado contributors
# Author: Houqi Zuo <hzuo@redhat.com>
import re

from avocado.utils import process


def get_timezone():
    """
    Get system timezone.

    :return: timezone name, timezone code
    :rtype: tuple
    :raises: AttributeError or IndexError will be raised if the result is NOT
             matched on the platform.
             The process.CmdError will be raised if the command is failed
             on the platform.
    """
    timezone_cmd = 'timedatectl | grep "Time zone"'
    timezone_re = "^(?:\s+Time zone:\s)(\w+\/\S+|UTC)(?:\s\(\S+,\s)([+|-]\d{4})\)$"

    timezone = process.run(timezone_cmd, shell=True).stdout_text
    timezone_set = re.match(timezone_re, timezone).groups()
    return timezone_set[0], timezone_set[1]


def set_timezone(timezone):
    """
    Set system timezone.

    :params timezone: timezone
    :type timezone: string
    :raises: The process.CmdError will be raised if the command is failed
             on the platform.
    """
    cmd = "timedatectl set-timezone %s" % timezone
    process.system(cmd, shell=True)
