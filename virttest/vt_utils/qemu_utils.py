#
# Library for qemu option related helper functions
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
import re

from avocado.utils import process


def has_option(option, qemu_path="/usr/bin/qemu-kvm"):
    """
    Helper function for command line option wrappers.

    :param option: Option need check.
    :type option: String
    :param qemu_path: Path for qemu-kvm.
    :type option: String

    :return: Return true if the qemu has the given option. Otherwise, return
             false.
    :rtype: Boolean
    """
    hlp = process.run(
        "%s -help" % qemu_path, shell=True, ignore_status=True, verbose=False
    ).stdout_text
    return bool(re.search(r"^-%s(\s|$)" % option, hlp, re.MULTILINE))


def get_support_machine_type(qemu_binary="/usr/libexec/qemu-kvm", remove_alias=False):
    """
    Get each machine types supported by host.

    :param qemu_binary: qemu-kvm binary file path.
    :type qemu_binary: String
    :param remove_alias: If it's True, remove alias or not. Otherwise, do NOT
                         remove alias.
    :type remove_alias: Boolean

    :return: A tuple(machine_name, machine_type, machine_alias).
    :rtype: Tuple[List, List, List]
    """
    o = process.run("%s -M ?" % qemu_binary).stdout_text.splitlines()
    machine_name = []
    machine_type = []
    machine_alias = []
    split_pattern = re.compile(
        r"^(\S+)\s+(.*?)(?: (\((?:alias|default|deprecated).*))?$"
    )
    for item in o[1:]:
        if "none" in item:
            continue
        machine_list = split_pattern.search(item).groups()
        machine_name.append(machine_list[0])
        machine_type.append(machine_list[1])
        val = None if remove_alias else machine_list[2]
        machine_alias.append(val)
    return machine_name, machine_type, machine_alias
