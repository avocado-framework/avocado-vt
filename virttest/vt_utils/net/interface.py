# Library for the interface related functions.
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
import fcntl
import json
import os
import re
import socket
import struct

from avocado.utils import process

from virttest import arch


def set_iface_flag(ifname, flag, active=True):
    """
    Set flag of the given interface.

    :param ifname: The interface name.
    :type ifname: String.
    :param flag: The flag. ( Such as IFF_BROADCAST or  1<<1 or 2)
    :type flag: Integer.
    :param active: Activate the flag given. Otherwise, deactivate the flag given.
    :type active: Boolean.

    :raise: IOError raised if fcntl.ioctl() command fails.
    """
    # Get existing device flags
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sockfd = sock.fileno()
        ifreq = struct.pack("16sh", ifname.encode(), 0)
        flags = struct.unpack("16sh", fcntl.ioctl(sockfd, arch.SIOCGIFFLAGS, ifreq))[1]

        # Set new flags
        if active:
            flags = flags | flag
        else:
            flags = flags & ~flag

        ifreq = struct.pack("16sh", ifname.encode(), flags)
        fcntl.ioctl(sockfd, arch.SIOCSIFFLAGS, ifreq)


def is_iface_flag_same(ifname, flag):
    """
    Check whether the flag given is as same as the current flags of interface.

    :param ifname: The interface name.
    :type ifname: String.
    :param flag: The flag.
    :type flag: Integer.

    :return: Return true if it's same. Otherwise, return false.
    :rtype: Boolean.

    :raise: IOError raised if fcntl.ioctl() command fails.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sockfd = sock.fileno()
        ifreq = struct.pack("16sh", ifname.encode(), 0)
        flags = struct.unpack("16sh", fcntl.ioctl(sockfd, arch.SIOCGIFFLAGS, ifreq))[1]

    return True if flags & flag else False


def create_ifname_index_mapping(ifname):
    """
    Map an interface name into its corresponding index.
    Returns 0 on error, as 0 is not a valid index.

    :param ifname: The interface name.
    :type ifname: String.

    :return: The index of the given interface.
    :rtype: Integer.

    :raise: IOError raised if fcntl.ioctl() command fails.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        ifr = struct.pack("16si", ifname.encode(), 0)
        r = fcntl.ioctl(sock, arch.SIOCGIFINDEX, ifr)
        index = struct.unpack("16si", r)[1]
    return index


def vnet_support_probe(tapfd, flag):
    """
    Check if a flag is support by tun.

    :param tapfd: The file descriptor of /dev/net/tun.
    :type tapfd: Integer.
    :param flag: The flag checked. ( Such as IFF_MULTI_QUEUE, IFF_VNET_HDR )
    :type flag: String.

    :return: Return true if support. Otherwise, return false.
    :rtype: Boolean.
    """
    u = struct.pack("I", 0)
    try:
        r = fcntl.ioctl(tapfd, arch.TUNGETFEATURES, u)
    except OverflowError:
        return False
    flags = struct.unpack("I", r)[0]
    flag = eval("arch.%s" % flag)
    return True if flags & flag else False


def get_net_if_operstate(ifname):
    """
    Get linux network device operstate.

    :param ifname: Name of the interface.
    :type ifname: String

    :return: the operstate of device. ( Such as up, down )
    :rtype: String

    :raise: A RuntimeError may be raised if running command fails.
            Example: The ifname is an un-existed interface.
    """
    cmd = "cat /sys/class/net/%s/operstate" % ifname
    cmd_obj = process.run(cmd, shell=True)
    output = cmd_obj.stdout_text.strip()
    return output


def get_net_if_ip_addrs(ifname):
    """
    Get network device ip addresses.

    :param ifname: Name of interface.
    :type ifname: String.

    :return: List ip addresses of network interface.
             {
                "ipv4": xxx,
                "ipv6": xxx,
                "mac": xxx,
             }
    :rtype: Dictionary.

    :raise: A RuntimeError may be raised if running command fails.
    """
    cmd = "ip addr show %s" % ifname
    cmd_obj = process.run(cmd, shell=True)
    status, output = cmd_obj.exit_status, cmd_obj.stdout_text.strip()
    return {
        "ipv4": re.findall("inet (.+?)/..?", output, re.MULTILINE),
        "ipv6": re.findall("inet6 (.+?)/...?", output, re.MULTILINE),
        "mac": re.findall("link/ether (.+?) ", output, re.MULTILINE),
    }


def set_net_if_ip_addrs(if_name, ip_addr):
    """
    Set network device ip addresses.

    :param if_name: Name of interface.
    :type if_name: String.
    :param ip_addr: Interface ip addr in format "ip_address/mask".
    :type ip_addr: String.

    :raise: process.CmdError.
    """
    cmd = "ip addr add %s dev %s" % (ip_addr, if_name)
    process.run(cmd, shell=True)


def del_net_if_ip_addrs(if_name, ip_addr):
    """
    Delete network device ip addresses.

    :param if_name: Name of interface.
    :type if_name: String.
    :param ip_addr: Interface ip addr in format "ip_address/mask".
    :type ip_addr: String.

    :raise: process.CmdError.
    """
    cmd = "ip addr del %s dev %s" % (ip_addr, if_name)
    process.run(cmd, shell=True)


def get_net_if(state=".*", qdisc=".*", optional=".*"):
    """
    Filter the all interfaces based on the parameters.

    :param state: interface state get from ip link.
    :type state: String.
    :param qdisc: interface qdisc get from ip link.
    :type qdisc: String.
    :param optional: optional match for interface find.
    :type optional: String.

    :return: List of network interfaces.
             ['lo', 'eno12409', 'eno8403', 'switch']
    :rtype: List.

    :raise: A RuntimeError may be raised if running command fails.
    """
    cmd = "ip link"
    cmd_obj = process.run(cmd, shell=True)
    output = cmd_obj.stdout_text.strip()
    return re.findall(
        r"^\d+: (\S+?)[@:].*%s.*%s.*state %s.*$" % (optional, qdisc, state),
        output,
        re.MULTILINE,
    )


def bring_up_ifname(ifname):
    """
    Bring up an interface.

    :param ifname: Name of the interface.
    :type ifname: String.

    :raise: IOError raised if fcntl.ioctl() command fails.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0) as sock:
        ifr = struct.pack("16sh", ifname.encode(), arch.IFF_UP)
        fcntl.ioctl(sock, arch.SIOCSIFFLAGS, ifr)


def bring_down_ifname(ifname):
    """
    Bring down an interface.

    :param ifname: Name of the interface.
    :type ifname: String.

    :raise: IOError raised if fcntl.ioctl() command fails.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0) as sock:
        ifr = struct.pack("16sh", ifname.encode(), 0)
        fcntl.ioctl(sock, arch.SIOCSIFFLAGS, ifr)


def net_if_set_macaddress(ifname, mac):
    """
    Set the mac address for an interface.

    :param ifname: Name of the interface.
    :type ifname: String.
    :param mac: Mac address.
    :type mac: String.

    :raise: IOError raised if fcntl.ioctl() command fails.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0) as sock:
        ifr = struct.pack("256s", ifname.encode())
        mac_dev = fcntl.ioctl(sock, arch.SIOCGIFHWADDR, ifr)[18:24]
        mac_dev = ":".join(["%02x" % ord(m) for m in mac_dev])

        if mac_dev.lower() == mac.lower():
            return

        ifr = struct.pack(
            "16sH14s",
            ifname.encode(),
            1,
            b"".join([chr(int(m, 16)) for m in mac.split(":")]),
        )
        fcntl.ioctl(sock, arch.SIOCSIFHWADDR, ifr)


def net_get_ifname(mac_address=""):
    """
    Get the interface name through the mac address.

    :param mac_address: The mac address of nic.
    :type mac_address: String.

    :return: The names of interface.
    :rtype: List.

    :raise: IOError or RuntimeError.
    """
    ifname_list = []
    cmd = "ip -json link"
    cmd_obj = process.run(cmd, shell=True)
    output = cmd_obj.stdout_text.strip()
    ip_info = json.loads(output)
    for ip in ip_info:
        if mac_address == ip["address"]:
            ifname_list.append(ip["ifname"])
    return ifname_list


def net_get_iface_info(iface="", mac=None):
    """
    Get info of certain interface with given mac address or
    interface name.

    :param iface: The name of given interface, defaults to "".
    :type iface: String.
    :param mac: Mac address of given interface, defaults to None.
    :type mac: String.

    :return: Info of interface, None if not get any.
    :rtype: Dictionary.

    :raise: IOError or RuntimeError.
    """
    cmd = "ip -json addr show %s" % iface
    cmd_obj = process.run(cmd, shell=True)
    output = cmd_obj.stdout_text.strip()
    ip_info = json.loads(output)
    if mac:
        for iface in ip_info:
            if iface.get("address") == mac:
                return iface
        return None
    if iface:
        return ip_info[0]
    else:
        return ip_info


def get_gateway(default_iface=False, ip_ver="ipv4", force_dhcp=False, ifname=""):
    """
    Get the default gateway or interface.

    :param default_iface: Whether default interface (True), or default gateway
                    (False) is returned, defaults to False.
    :type default_iface: Boolean.
    :param ip_ver: The ip version, defaults to "ipv4".
    :type ip_ver: String.
    :param force_dhcp: Check whether the protocol is DHCP.
    :type force_dhcp: Boolean.
    :param ifname: If given, get default gateway only for this device.
    :type ifname: String.

    :return: The gateway.
    :rtype: String.

    :raise: RuntimeError raised if command fails.
    """
    cmd = "ip -json -6 route" if ip_ver == "ipv6" else "ip -json route"
    cmd_obj = process.run(cmd, shell=True)
    output = cmd_obj.stdout_text.strip()
    ip_info = json.loads(output)
    gateways = []
    for ip in ip_info:
        if not ifname or ifname == ip.get("dev"):
            if not force_dhcp or (force_dhcp and ip.get("protocol") == "dhcp"):
                if default_iface:
                    gateways.append(ip.get("dev"))
                else:
                    gateways.append(ip.get("gateway"))
    return "\n".join(gateways)


def get_sorted_net_if():
    """
    Get all network interfaces, but sort them among physical and virtual if.

    :return: (physical interfaces, virtual interfaces).
    :rtype: Tuple.
    """
    SYSFS_NET_PATH = "/sys/class/net"
    all_interfaces = get_net_if()
    phy_interfaces = []
    vir_interfaces = []
    for d in all_interfaces:
        path = os.path.join(SYSFS_NET_PATH, d)
        if not os.path.isdir(path):
            continue
        if not os.path.exists(os.path.join(path, "device")):
            vir_interfaces.append(d)
        else:
            phy_interfaces.append(d)
    return (phy_interfaces, vir_interfaces)


def net_if_is_brport(ifname):
    """
    Check Whether this Interface is a bridge port_to_br.

    :param ifname: The interface name.
    :type ifname: String.

    :return: True if it's a bridge port_to_br, otherwise return False.
    :rtype: Boolean.
    """
    SYSFS_NET_PATH = "/sys/class/net"
    path = os.path.join(SYSFS_NET_PATH, ifname)
    return os.path.exists(os.path.join(path, "brport"))
