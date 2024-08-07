# Library for the ip address related functions.
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
import ipaddress as pyipaddr
import re

from avocado.utils import process


def gen_ipv4_addr(network_num="10.0.0.0", network_prefix="24", exclude_ips=[]):
    """
    Generate ipv4 address.

    :param network_num: Network number to be used.
    :type network_num: String.
    :param network_prefix: Prefix used to get subnet mask to calculate ip range.
    :type network_prefix: String.
    :param exclude_ips: The list of ipaddress should be excluded.
    :type exclude_ips: List.

    :return: The ip address.
    :rtype: String
    """
    ip_regex = "^\d+.\d+.\d+.\d+$"
    exclude_ips = set(exclude_ips)
    if not re.match(ip_regex, network_num):
        network_num = "10.0.0.0"
    if not exclude_ips and network_prefix == "24":
        exclude_ips.add(network_num)
        exclude_ips.add(".".join(network_num.split(".")[0:3]) + ".%s" % str(1))
        exclude_ips.add((".".join(network_num.split(".")[0:3]) + ".%s" % str(255)))
    network = pyipaddr.ip_network("%s/%s" % (network_num, network_prefix))
    for ip_address in network:
        if str(ip_address) not in exclude_ips:
            yield str(ip_address)


def get_correspond_ip(remote_ip):
    """
    Get local ip address which is used to contact remote ip.

    :param remote_ip: Remote ip.
    :type remote_ip: String.

    :return: Local corespond IP.
    :rtype: String.
    """
    result = process.run("ip route get %s" % remote_ip).stdout_text
    local_ip = re.search("src (.+)", result)
    if local_ip is not None:
        local_ip = local_ip.groups()[0]
    return local_ip


def append_hosts(hostname_ip_dict):
    """
    Method to map ipaddress and hostname for resolving appropriately
    in /etc/hosts file.

    :param hostname_ip_dict: The mapping of hostname and ipaddress.
    :type hostname_ip_dict: Dictionary.

    :raise: RuntimeError.
    """
    hosts_file = "/etc/hosts"
    for hostname, ip in hostname_ip_dict:
        cmd = "echo '%s %s' >> %s" % (ip, hostname, hosts_file)
        process.run(cmd, shell=True)
