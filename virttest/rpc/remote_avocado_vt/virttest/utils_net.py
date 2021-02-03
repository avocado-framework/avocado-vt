import os
import errno
import socket
import struct
import fcntl
import logging

from remote_avocado_vt.virttest import arch

try:
    unicode
except NameError:
    unicode = str


CTYPES_SUPPORT = True
try:
    import ctypes
except ImportError:
    CTYPES_SUPPORT = False

SYSFS_NET_PATH = "/sys/class/net"
PROCFS_NET_PATH = "/proc/net/dev"
# globals
sock = None
sockfd = None


class NetError(Exception):

    def __init__(self, *args):
        Exception.__init__(self, *args)


class TAPModuleError(NetError):

    def __init__(self, devname, action="open", details=None):
        NetError.__init__(self, devname)
        self.devname = devname
        self.action = action
        self.details = details

    def __str__(self):
        e_msg = "Can't %s %s" % (self.action, self.devname)
        if self.details is not None:
            e_msg += " : %s" % self.details
        return e_msg


class TAPNotExistError(NetError):

    def __init__(self, ifname):
        NetError.__init__(self, ifname)
        self.ifname = ifname

    def __str__(self):
        return "Interface %s does not exist" % self.ifname


class TAPCreationError(NetError):

    def __init__(self, ifname, details=None):
        NetError.__init__(self, ifname, details)
        self.ifname = ifname
        self.details = details

    def __str__(self):
        e_msg = "Cannot create TAP device %s" % self.ifname
        if self.details is not None:
            e_msg += ": %s" % self.details
        return e_msg


class MacvtapCreationError(NetError):

    def __init__(self, ifname, base_interface, details=None):
        NetError.__init__(self, ifname, details)
        self.ifname = ifname
        self.interface = base_interface
        self.details = details

    def __str__(self):
        e_msg = "Cannot create macvtap device %s " % self.ifname
        e_msg += "base physical interface %s." % self.interface
        if self.details is not None:
            e_msg += ": %s" % self.details
        return e_msg


class MacvtapGetBaseInterfaceError(NetError):

    def __init__(self, ifname=None, details=None):
        NetError.__init__(self, ifname, details)
        self.ifname = ifname
        self.details = details

    def __str__(self):
        e_msg = "Cannot get a valid physical interface to create macvtap."
        if self.ifname:
            e_msg += "physical interface is : %s " % self.ifname
        if self.details is not None:
            e_msg += "error info: %s" % self.details
        return e_msg


class TAPBringUpError(NetError):

    def __init__(self, ifname):
        NetError.__init__(self, ifname)
        self.ifname = ifname

    def __str__(self):
        return "Cannot bring up TAP %s" % self.ifname


class TAPBringDownError(NetError):

    def __init__(self, ifname):
        NetError.__init__(self, ifname)
        self.ifname = ifname

    def __str__(self):
        return "Cannot bring down TAP %s" % self.ifname


class BRAddIfError(NetError):

    def __init__(self, ifname, brname, details):
        NetError.__init__(self, ifname, brname, details)
        self.ifname = ifname
        self.brname = brname
        self.details = details

    def __str__(self):
        return ("Can't add interface %s to bridge %s: %s" %
                (self.ifname, self.brname, self.details))


class BRDelIfError(NetError):

    def __init__(self, ifname, brname, details):
        NetError.__init__(self, ifname, brname, details)
        self.ifname = ifname
        self.brname = brname
        self.details = details

    def __str__(self):
        return ("Can't remove interface %s from bridge %s: %s" %
                (self.ifname, self.brname, self.details))


class IfNotInBridgeError(NetError):

    def __init__(self, ifname, details):
        NetError.__init__(self, ifname, details)
        self.ifname = ifname
        self.details = details

    def __str__(self):
        return ("Interface %s is not present on any bridge: %s" %
                (self.ifname, self.details))


class OpenflowSwitchError(NetError):

    def __init__(self, brname):
        NetError.__init__(self, brname)
        self.brname = brname

    def __str__(self):
        return ("Only support openvswitch, make sure your env support ovs, "
                "and your bridge %s is an openvswitch" % self.brname)


class BRNotExistError(NetError):

    def __init__(self, brname, details):
        NetError.__init__(self, brname, details)
        self.brname = brname
        self.details = details

    def __str__(self):
        return ("Bridge %s does not exist: %s" % (self.brname, self.details))


class IfChangeBrError(NetError):

    def __init__(self, ifname, old_brname, new_brname, details):
        NetError.__init__(self, ifname, old_brname, new_brname, details)
        self.ifname = ifname
        self.new_brname = new_brname
        self.old_brname = old_brname
        self.details = details

    def __str__(self):
        return ("Can't move interface %s from bridge %s to bridge %s: %s" %
                (self.ifname, self.new_brname, self.oldbrname, self.details))


class IfChangeAddrError(NetError):

    def __init__(self, ifname, ipaddr, details):
        NetError.__init__(self, ifname, ipaddr, details)
        self.ifname = ifname
        self.ipaddr = ipaddr
        self.details = details

    def __str__(self):
        return ("Can't change interface IP address %s from interface %s: %s" %
                (self.ifname, self.ipaddr, self.details))


class BRIpError(NetError):

    def __init__(self, brname):
        NetError.__init__(self, brname)
        self.brname = brname

    def __str__(self):
        return ("Bridge %s doesn't have an IP address assigned. It's"
                " impossible to start dnsmasq for this bridge." %
                (self.brname))


class VMIPV6NeighNotFoundError(NetError):

    def __init__(self, ipv6_address):
        NetError.__init__(self, ipv6_address)
        self.ipv6_address = ipv6_address

    def __str__(self):
        return "No IPV6 neighbours with address %s" % self.ipv6_address


class VMIPV6AdressError(NetError):

    def __init__(self, error_info):
        NetError.__init__(self, error_info)
        self.error_info = error_info

    def __str__(self):
        return "%s, check your test env supports IPV6" % self.error_info


class HwAddrSetError(NetError):

    def __init__(self, ifname, mac):
        NetError.__init__(self, ifname, mac)
        self.ifname = ifname
        self.mac = mac

    def __str__(self):
        return "Can not set mac %s to interface %s" % (self.mac, self.ifname)


class HwAddrGetError(NetError):

    def __init__(self, ifname):
        NetError.__init__(self, ifname)
        self.ifname = ifname

    def __str__(self):
        return "Can not get mac of interface %s" % self.ifname


class IPAddrGetError(NetError):

    def __init__(self, mac_addr, details=None):
        NetError.__init__(self, mac_addr)
        self.mac_addr = mac_addr
        self.details = details

    def __str__(self):
        details_msg = "Get guest nic ['%s'] IP address error" % self.mac_addr
        details_msg += "error info: %s" % self.details
        return details_msg


class IPAddrSetError(NetError):

    def __init__(self, mac_addr, ip_addr, details=None):
        NetError.__init__(self, mac_addr, ip_addr)
        self.mac_addr = mac_addr
        self.ip_addr = ip_addr
        self.details = details

    def __str__(self):
        details_msg = "Cannot set IP %s to guest mac ['%s']." % (self.ip_addr,
                                                                 self.mac_addr)
        details_msg += " Error info: %s" % self.details
        return details_msg


class HwOperstarteGetError(NetError):

    def __init__(self, ifname, details=None):
        NetError.__init__(self, ifname)
        self.ifname = ifname
        self.details = details

    def __str__(self):
        return "Get nic %s operstate error, %s" % (self.ifname, self.details)


class VlanError(NetError):

    def __init__(self, ifname, details):
        NetError.__init__(self, ifname, details)
        self.ifname = ifname
        self.details = details

    def __str__(self):
        return ("Vlan error on interface %s: %s" %
                (self.ifname, self.details))


class VMNetError(NetError):

    def __str__(self):
        return ("VMNet instance items must be dict-like and contain "
                "a 'nic_name' mapping")


class DbNoLockError(NetError):

    def __str__(self):
        return "Attempt made to access database with improper locking"


class DelLinkError(NetError):

    def __init__(self, ifname, details=None):
        NetError.__init__(self, ifname, details)
        self.ifname = ifname
        self.details = details

    def __str__(self):
        e_msg = "Cannot delete interface %s" % self.ifname
        if self.details is not None:
            e_msg += ": %s" % self.details
        return e_msg


def if_nametoindex(ifname):
    """
    Map an interface name into its corresponding index.
    Returns 0 on error, as 0 is not a valid index

    :param ifname: interface name
    """
    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
    ifr = struct.pack("16si", ifname.encode(), 0)
    r = fcntl.ioctl(ctrl_sock, arch.SIOCGIFINDEX, ifr)
    index = struct.unpack("16si", r)[1]
    ctrl_sock.close()
    return index


def bring_up_ifname(ifname):
    """
    Bring up an interface

    :param ifname: Name of the interface
    """
    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
    ifr = struct.pack("16sh", ifname.encode(), arch.IFF_UP)
    try:
        fcntl.ioctl(ctrl_sock, arch.SIOCSIFFLAGS, ifr)
    except IOError:
        raise TAPBringUpError(ifname)
    ctrl_sock.close()
    return True


def bring_down_ifname(ifname):
    """
    Bring down an interface

    :param ifname: Name of the interface
    """
    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
    ifr = struct.pack("16sh", ifname.encode(), 0)
    try:
        fcntl.ioctl(ctrl_sock, arch.SIOCSIFFLAGS, ifr)
    except IOError:
        raise TAPBringDownError(ifname)
    ctrl_sock.close()


def vnet_mq_probe(tapfd):
    """
    Check if the IFF_MULTI_QUEUE is support by tun.

    :param tapfd: the file descriptor of /dev/net/tun
    """
    u = struct.pack("I", 0)
    try:
        r = fcntl.ioctl(tapfd, arch.TUNGETFEATURES, u)
    except OverflowError:
        logging.debug("Fail to get tun features!")
        return False
    flags = struct.unpack("I", r)[0]
    if flags & arch.IFF_MULTI_QUEUE:
        return True
    else:
        return False


def vnet_hdr_probe(tapfd):
    """
    Check if the IFF_VNET_HDR is support by tun.

    :param tapfd: the file descriptor of /dev/net/tun
    """
    u = struct.pack("I", 0)
    try:
        r = fcntl.ioctl(tapfd, arch.TUNGETFEATURES, u)
    except OverflowError:
        logging.debug("Fail to get tun features!")
        return False
    flags = struct.unpack("I", r)[0]
    if flags & arch.IFF_VNET_HDR:
        return True
    else:
        return False


def open_tap(devname, ifname, queues=1, vnet_hdr=True):
    """
    Open a tap device and returns its file descriptors which are used by
    fds=<fd1:fd2:..> parameter of qemu

    For single queue, only returns one file descriptor, it's used by
    fd=<fd> legacy parameter of qemu

    :param devname: TUN device path
    :param ifname: TAP interface name
    :param queues: Queue number
    :param vnet_hdr: Whether enable the vnet header
    """
    tapfds = []

    for i in range(int(queues)):
        try:
            tapfds.append(str(os.open(devname, os.O_RDWR)))
        except OSError as e:
            raise TAPModuleError(devname, "open", e)

        flags = arch.IFF_TAP | arch.IFF_NO_PI

        if vnet_mq_probe(int(tapfds[i])):
            flags |= arch.IFF_MULTI_QUEUE
        elif (int(queues) > 1):
            raise TAPCreationError(ifname, "Host doesn't support MULTI_QUEUE")

        if vnet_hdr and vnet_hdr_probe(int(tapfds[i])):
            flags |= arch.IFF_VNET_HDR

        ifr = struct.pack("16sh", ifname.encode(), flags)
        try:
            r = fcntl.ioctl(int(tapfds[i]), arch.TUNSETIFF, ifr)
        except IOError as details:
            raise TAPCreationError(ifname, details)

    return ':'.join(tapfds)


class Bridge(object):

    def get_structure(self):
        """
        Get bridge list.
        """
        sysfs_path = "/sys/class/net"
        result = dict()
        for br_iface in os.listdir(sysfs_path):
            br_iface_path = os.path.join(sysfs_path, br_iface)
            try:
                if (not os.path.isdir(br_iface_path) or
                        "bridge" not in os.listdir(br_iface_path)):
                    continue
            except OSError as e:
                if e.errno == errno.ENOENT:
                    continue
                else:
                    raise e

            result[br_iface] = dict()
            # Get stp_state
            stp_state_path = os.path.join(br_iface_path, "bridge", "stp_state")
            with open(stp_state_path, "r") as stp_state_file:
                stp_state = int(stp_state_file.read().strip())
            # Assign with 'yes' or 'no' to keep ABI compatibility
            result[br_iface]["stp"] = "yes" if stp_state else "no"
            # Get ports
            brif_path = os.path.join(br_iface_path, "brif")
            result[br_iface]["iface"] = os.listdir(brif_path)
        return result

    def list_br(self):
        return list(self.get_structure().keys())

    def list_iface(self, br=None):
        """
        Return all interfaces used by bridge.

        :param br: Name of bridge
        """
        if br:
            return self.get_structure()[br]['iface']
        interface_list = []
        for br in self.list_br():
            for (value) in self.get_structure()[br]['iface']:
                interface_list.append(value)
        return interface_list

    def port_to_br(self, port_name):
        """
        Return bridge which contain port.

        :param port_name: Name of port.
        :return: Bridge name or None if there is no bridge which contain port.
        """
        bridge = None
        for br in self.list_br():
            if port_name in self.get_structure()[br]['iface']:
                bridge = br
        return bridge

    def br_ioctl(self, io_cmd, brname, ifname):
        ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        index = if_nametoindex(ifname)
        if index == 0:
            raise TAPNotExistError(ifname)
        ifr = struct.pack("16si", brname.encode(), index)
        _ = fcntl.ioctl(ctrl_sock, io_cmd, ifr)
        ctrl_sock.close()

    def add_port(self, brname, ifname):
        """
        Add a device to bridge

        :param ifname: Name of TAP device
        :param brname: Name of the bridge
        """
        try:
            self.br_ioctl(arch.SIOCBRADDIF, brname, ifname)
        except IOError as details:
            raise BRAddIfError(ifname, brname, details)

    def del_port(self, brname, ifname):
        """
        Remove a TAP device from bridge

        :param ifname: Name of TAP device
        :param brname: Name of the bridge
        """
        try:
            self.br_ioctl(arch.SIOCBRDELIF, brname, ifname)
        except IOError as details:
            # Avoid failing the test when port not present in br
            if ifname in self.list_iface(brname):
                raise BRDelIfError(ifname, brname, details)

    def add_bridge(self, brname):
        """
        Add a bridge in host
        """
        ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        fcntl.ioctl(ctrl_sock, arch.SIOCBRADDBR, brname)
        ctrl_sock.close()

    def del_bridge(self, brname):
        """
        Delete a bridge in host
        """
        ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        fcntl.ioctl(ctrl_sock, arch.SIOCBRDELBR, brname)
        ctrl_sock.close()

    def get_stp_status(self, brname):
        """
        get STP status
        """
        bridge_stp = None
        try:
            bridge_stp = self.get_structure()[brname]['stp']
        except KeyError:
            logging.error("Not find bridge %s", brname)
        return bridge_stp
