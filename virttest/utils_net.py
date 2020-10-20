import re
import os
import socket
import fcntl
import errno
import struct
import logging
import random
import math
import time
import shelve
import signal
import netifaces
import netaddr
import platform
import uuid
import hashlib
import shutil

import aexpect
from aexpect import remote

from avocado.core import exceptions
from avocado.utils import path as utils_path
from avocado.utils import process

import six
from six.moves import xrange

from virttest import openvswitch
from virttest import data_dir
from virttest import propcan
from virttest import utils_misc
from virttest import arch
from virttest import utils_selinux
from virttest import utils_package

from virttest.staging import utils_memory
from virttest.versionable_class import factory
from virttest.utils_windows import virtio_win
from virttest.utils_windows import system


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


def warp_init_del(func):
    def new_func(*args, **argkw):
        globals()["sock"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        globals()["sockfd"] = globals()["sock"].fileno()
        try:
            return func(*args, **argkw)
        finally:
            globals()["sock"].close()
            globals()["sock"] = None
            globals()["sockfd"] = None
    return new_func


class Interface(object):

    ''' Class representing a Linux network device. '''

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "<%s %s at 0x%x>" % (self.__class__.__name__,
                                    self.name, id(self))

    @warp_init_del
    def set_iface_flag(self, flag, active=True):
        # Get existing device flags
        ifreq = struct.pack('16sh', self.name.encode(), 0)
        flags = struct.unpack('16sh',
                              fcntl.ioctl(sockfd, arch.SIOCGIFFLAGS, ifreq))[1]

        # Set new flags
        if active:
            flags = flags | flag
        else:
            flags = flags & ~flag

        ifreq = struct.pack('16sh', self.name.encode(), flags)
        fcntl.ioctl(sockfd, arch.SIOCSIFFLAGS, ifreq)

    @warp_init_del
    def is_iface_flag_on(self, flag):
        ifreq = struct.pack('16sh', self.name.encode(), 0)
        flags = struct.unpack('16sh',
                              fcntl.ioctl(sockfd, arch.SIOCGIFFLAGS, ifreq))[1]

        if flags & flag:
            return True
        else:
            return False

    def up(self):
        '''
        Bring up the bridge interface. Equivalent to ifconfig [iface] up.
        '''
        self.set_iface_flag(arch.IFF_UP)

    def down(self):
        '''
        Bring down the bridge interface. Equivalent to ifconfig [iface] down.
        '''
        self.set_iface_flag(arch.IFF_UP, active=False)

    def is_up(self):
        '''
        Return True if the interface is up, False otherwise.
        '''
        return self.is_iface_flag_on(arch.IFF_UP)

    def promisc_on(self):
        '''
        Enable promiscuous mode on the interface.
        Equivalent to ip link set [iface] promisc on.
        '''
        self.set_iface_flag(arch.IFF_PROMISC)

    def promisc_off(self):
        '''
        Disable promiscuous mode on the interface.
        Equivalent to ip link set [iface] promisc off.
        '''
        self.set_iface_flag(arch.IFF_PROMISC, active=False)

    def is_promisc(self):
        '''
        Return True if the interface promiscuous mode is on, False otherwise.
        '''
        return self.is_iface_flag_on(arch.IFF_PROMISC)

    @warp_init_del
    def get_mac(self):
        '''
        Obtain the device's mac address.
        '''
        ifreq = struct.pack('16sH14s', self.name.encode(),
                            socket.AF_UNIX, b'\x00' * 14)
        res = fcntl.ioctl(sockfd, arch.SIOCGIFHWADDR, ifreq)
        address = struct.unpack('16sH14s', res)[2]
        mac = struct.unpack('6B8x', address)

        return ":".join(['%02X' % i for i in mac])

    @warp_init_del
    def set_mac(self, newmac):
        '''
        Set the device's mac address. Device must be down for this to
        succeed.
        '''
        macbytes = [int(i, 16) for i in newmac.split(':')]
        ifreq = struct.pack('16sH6B8x', self.name.encode(),
                            socket.AF_UNIX, *macbytes)
        fcntl.ioctl(sockfd, arch.SIOCSIFHWADDR, ifreq)

    @warp_init_del
    def get_ip(self):
        """
        Get ip address of this interface
        """
        ifreq = struct.pack('16sH14s', self.name.encode(),
                            socket.AF_INET, b'\x00' * 14)
        try:
            res = fcntl.ioctl(sockfd, arch.SIOCGIFADDR, ifreq)
        except IOError:
            return None
        ip = struct.unpack('16sH2x4s8x', res)[2]

        return socket.inet_ntoa(ip)

    @warp_init_del
    def set_ip(self, newip):
        """
        Set the ip address of the interface
        """
        ipbytes = socket.inet_aton(newip)
        ifreq = struct.pack('16sH2s4s8s', self.name.encode(),
                            socket.AF_INET, b'\x00' * 2, ipbytes, b'\x00' * 8)
        fcntl.ioctl(sockfd, arch.SIOCSIFADDR, ifreq)

    @warp_init_del
    def get_netmask(self):
        """
        Get ip network netmask
        """
        if not CTYPES_SUPPORT:
            raise exceptions.TestSkipError("Getting the netmask requires "
                                           "python > 2.4")
        ifreq = struct.pack('16sH14s', self.name.encode(),
                            socket.AF_INET, b'\x00' * 14)
        try:
            res = fcntl.ioctl(sockfd, arch.SIOCGIFNETMASK, ifreq)
        except IOError:
            return 0
        netmask = socket.ntohl(struct.unpack('16sH2xI8x', res)[2])

        return 32 - int(math.log(ctypes.c_uint32(~netmask).value + 1, 2))

    @warp_init_del
    def set_netmask(self, netmask):
        """
        Set netmask
        """
        if not CTYPES_SUPPORT:
            raise exceptions.TestSkipError("Setting the netmask requires "
                                           "python > 2.4")
        netmask = ctypes.c_uint32(~((2 ** (32 - netmask)) - 1)).value
        nmbytes = socket.htonl(netmask)
        ifreq = struct.pack('16sH2si8s', self.name.encode(),
                            socket.AF_INET, b'\x00' * 2, nmbytes, b'\x00' * 8)
        fcntl.ioctl(sockfd, arch.SIOCSIFNETMASK, ifreq)

    @warp_init_del
    def get_mtu(self):
        '''
        Get MTU size of the interface
        '''
        ifreq = struct.pack('16sH14s', self.name.encode(),
                            socket.AF_INET, b'\x00' * 14)
        res = fcntl.ioctl(sockfd, arch.SIOCGIFMTU, ifreq)

        return struct.unpack('16sH14s', res)[1]

    @warp_init_del
    def set_mtu(self, newmtu):
        '''
        Set MTU size of the interface
        '''
        ifreq = struct.pack('16sH14s', self.name.encode(),
                            newmtu, b'\x00' * 14)
        fcntl.ioctl(sockfd, arch.SIOCSIFMTU, ifreq)

    @warp_init_del
    def get_index(self):
        '''
        Convert an interface name to an index value.
        '''
        ifreq = struct.pack('16si', self.name.encode(), 0)
        res = fcntl.ioctl(sockfd, arch.SIOCGIFINDEX, ifreq)
        return struct.unpack("16si", res)[1]

    @warp_init_del
    def get_stats(self):
        """
        Get the status information of the Interface
        """
        spl_re = re.compile(r"\s+")

        fp = open(PROCFS_NET_PATH)
        # Skip headers
        fp.readline()
        fp.readline()
        while True:
            data = fp.readline()
            if not data:
                return None

            name, stats_str = data.split(":")
            if name.strip() != self.name:
                continue

            stats = [int(a) for a in spl_re.split(stats_str.strip())]
            break

        titles = ["rx_bytes", "rx_packets", "rx_errs", "rx_drop", "rx_fifo",
                  "rx_frame", "rx_compressed", "rx_multicast", "tx_bytes",
                  "tx_packets", "tx_errs", "tx_drop", "tx_fifo", "tx_colls",
                  "tx_carrier", "tx_compressed"]
        return dict(zip(titles, stats))

    def is_brport(self):
        """
        Check Whether this Interface is a bridge port_to_br
        """
        path = os.path.join(SYSFS_NET_PATH, self.name)
        return os.path.exists(os.path.join(path, "brport"))

    def __netlink_pack(self, msgtype, flags, seq, pid, data):
        '''
        Pack with Netlink message header and data
        into Netlink package
        :msgtype:  Message types: e.g. RTM_DELLINK
        :flags: Flag bits
        :seq: The sequence number of the message
        :pid: Process ID
        :data:  data
        :return: return the package
        '''
        return struct.pack('IHHII', 16 + len(data),
                           msgtype, flags, seq, pid) + data

    def __netlink_unpack(self, data):
        '''
        Unpack the data from kernel
        '''
        out = []
        while data:
            length, msgtype, flags, seq, pid = struct.unpack('IHHII',
                                                             data[:16])
            if len(data) < length:
                raise RuntimeError("Buffer overrun!")
            out.append((msgtype, flags, seq, pid, data[16:length]))
            data = data[length:]

        return out

    def dellink(self):
        '''
        Delete the interface. Equivalent to 'ip link delete NAME'.
        '''
        # create socket
        sock = socket.socket(socket.AF_NETLINK,
                             socket.SOCK_RAW,
                             arch.NETLINK_ROUTE)

        # Get the interface index
        interface_index = self.get_index()

        # send data to socket
        sock.send(self.__netlink_pack(msgtype=arch.RTM_DELLINK,
                                      flags=arch.NLM_F_REQUEST | arch.NLM_F_ACK,
                                      seq=1, pid=0,
                                      data=struct.pack('BxHiII',
                                                       arch.AF_PACKET,
                                                       0, interface_index, 0, 0)))

        # receive data from socket
        try:
            while True:
                data_recv = sock.recv(1024)
                for msgtype, flags, mseq, pid, data in \
                        self.__netlink_unpack(data_recv):
                    if msgtype == arch.NLMSG_ERROR:
                        (err_no,) = struct.unpack("i", data[:4])
                        if err_no == 0:
                            return 0
                        else:
                            raise DelLinkError(self.name, os.strerror(-err_no))
                    else:
                        raise DelLinkError(self.name, "unexpected error")
        finally:
            sock.close()


class Macvtap(Interface):

    """
    class of macvtap, base Interface
    """

    def __init__(self, tapname=None):
        if tapname is None:
            self.tapname = "macvtap" + utils_misc.generate_random_id()
        else:
            self.tapname = tapname
        Interface.__init__(self, self.tapname)

    def get_tapname(self):
        return self.tapname

    def get_device(self):
        return "/dev/tap%s" % self.get_index()

    def ip_link_ctl(self, params, ignore_status=False):
        return process.run('%s %s' %
                           (utils_path.find_command("ip"), " ".join(params)),
                           ignore_status=ignore_status, verbose=False)

    def create(self, device, mode="vepa"):
        """
        Create a macvtap device, only when the device does not exist.

        :param device: Macvtap device to be created.
        :param mode: Creation mode.
        """
        path = os.path.join(SYSFS_NET_PATH, self.tapname)
        if not os.path.exists(path):
            self.ip_link_ctl(["link", "add", "link", device, "name",
                              self.tapname, "type", "macvtap", "mode", mode])

    def delete(self):
        path = os.path.join(SYSFS_NET_PATH, self.tapname)
        if os.path.exists(path):
            self.ip_link_ctl(["link", "delete", self.tapname])

    def open(self):
        device = self.get_device()
        try:
            return os.open(device, os.O_RDWR)
        except OSError as e:
            raise TAPModuleError(device, "open", e)


class IPAddress(object):

    """
    Class to manipulate IPv4 or IPv6 address.
    """

    def __init__(self, ip_str='', info=''):
        self.addr = ''
        self.iface = ''
        self.scope = 0
        self.packed_addr = None

        if info:
            try:
                self.iface = info['iface']
                self.addr = info['addr']
                self.version = info['version']
                self.scope = info['scope']
            except KeyError:
                pass

        if ip_str:
            self.canonicalize(ip_str)

    def __str__(self):
        if self.version == 'ipv6':
            return "%s%%%s" % (self.addr, self.scope)
        else:
            return self.addr

    def canonicalize(self, ip_str):
        """
        Parse an IP string for listen to IPAddress content.
        """
        try:
            if ':' in ip_str:
                self.version = 'ipv6'
                if '%' in ip_str:
                    ip_str, scope = ip_str.split('%')
                    self.scope = int(scope)
                self.packed_addr = socket.inet_pton(socket.AF_INET6, ip_str)
                self.addr = socket.inet_ntop(socket.AF_INET6, self.packed_addr)
            else:
                self.version = 'ipv4'
                self.packed_addr = socket.inet_pton(socket.AF_INET, ip_str)
                self.addr = socket.inet_ntop(socket.AF_INET, self.packed_addr)
        except socket.error as detail:
            if 'illegal IP address' in str(detail):
                self.addr = ip_str
                self.version = 'hostname'

    def listening_on(self, port, max_retry=30):
        """
        Check whether a port is used for listening.
        """

        def test_connection(self, port):
            """
            Try connect to a port and return the connect result as error no.
            """

            port = int(port)
            if self.version == 'ipv6':
                sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                result = sock.connect_ex((self.addr, port, 0, self.scope))
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                result = sock.connect_ex((self.addr, port))
            return result

        retry = 0
        while True:
            if retry == max_retry:
                return False

            result = test_connection(self, port)

            if result == 0:
                return True
            elif result == 11:  # Resource temporarily unavailable.
                time.sleep(0.1)
                retry += 1
            else:
                return False

    def __eq__(self, other_ip):
        if self.version != other_ip.version:
            return False
        if self.addr != other_ip.addr:
            return False
        if self.iface and other_ip.iface and self.iface != other_ip.iface:
            return False
        return True


def raw_ping(command, timeout, session, output_func):
    """
    Low-level ping command execution.

    :param command: Ping command.
    :param timeout: Timeout of the ping command.
    :param session: Local executon hint or session to execute the ping command.
    """
    if session is None:
        logging.info("The command of Ping is: %s", command)
        process = aexpect.run_bg(command, output_func=output_func,
                                 timeout=timeout)

        # Send SIGINT signal to notify the timeout of running ping process,
        # Because ping have the ability to catch the SIGINT signal so we can
        # always get the packet loss ratio even if timeout.
        if process.is_alive():
            utils_misc.kill_process_tree(process.get_pid(), signal.SIGINT)

        status = process.get_status()
        output = process.get_output()

        process.close()
        return status, output
    else:
        output = ""
        try:
            output = session.cmd_output(command, timeout=timeout,
                                        print_func=output_func)
        except aexpect.ShellTimeoutError:
            # Send ctrl+c (SIGINT) through ssh session
            session.send("\003")
            try:
                output2 = session.read_up_to_prompt(print_func=output_func)
                output += output2
            except aexpect.ExpectTimeoutError as e:
                output += e.output
                # We also need to use this session to query the return value
                session.send("\003")

        session.sendline(session.status_test_command)
        try:
            o2 = session.read_up_to_prompt()
        except aexpect.ExpectError:
            status = -1
        else:
            try:
                status = int(re.findall("\d+", o2)[0])
            except Exception:
                status = -1

        return status, output


def ping(dest=None, count=None, interval=None, interface=None,
         packetsize=None, ttl=None, hint=None, adaptive=False,
         broadcast=False, flood=False, timeout=0,
         output_func=logging.debug, session=None, force_ipv4=False):
    """
    Wrapper of ping.

    :param dest: Destination address.
    :param count: Count of icmp packet.
    :param interval: Interval of two icmp echo request.
    :param interface: Specified interface of the source address.
    :param packetsize: Packet size of icmp.
    :param ttl: IP time to live.
    :param hint: Path mtu discovery hint.
    :param adaptive: Adaptive ping flag.
    :param broadcast: Broadcast ping flag.
    :param flood: Flood ping flag.
    :param timeout: Timeout for the ping command.
    :param output_func: Function used to log the result of ping.
    :param session: Local executon hint or session to execute the ping command.
    :param force_ipv4: Whether or not force using IPV4 to ping.
    """
    command = "ping"
    if session and "Windows" in session.cmd_output_safe("echo %OS%"):
        if dest:
            command += " %s " % dest
        else:
            command += " localhost "
        if count:
            command += " -n %s" % count
        if packetsize:
            command += " -l %s" % packetsize
        if ttl:
            command += " -i %s" % ttl
        if interface:
            command += " -S %s" % interface
        if flood:
            command += " -t"
    else:
        if ":" in dest:
            command = "ping6"
        if dest:
            command += " %s " % dest
        else:
            command += " localhost "
        if count:
            command += " -c %s" % count
        if interval:
            command += " -i %s" % interval
        if interface:
            command += " -I %s" % interface
        else:
            if dest.upper().startswith("FE80"):
                err_msg = "Using ipv6 linklocal must assigne interface"
                raise exceptions.TestSkipError(err_msg)
        if packetsize:
            command += " -s %s" % packetsize
        if ttl:
            command += " -t %s" % ttl
        if hint:
            command += " -M %s" % hint
        if adaptive:
            command += " -A"
        if broadcast:
            command += " -b"
        if flood:
            command += " -f -q"
            command = "sleep %s && kill -2 `pidof ping` & %s" % (timeout,
                                                                 command)
            output_func = None
            timeout += 1
        if force_ipv4:
            command += ' -4'

    return raw_ping(command, timeout, session, output_func)


def get_macvtap_base_iface(base_interface=None):
    """
    Get physical interface to create macvtap, if you assigned base interface
    is valid(not belong to any bridge and is up), will use it; else use the
    first physical interface,  which is not a brport and up.
    """
    tap_base_device = None

    (dev_int, _) = get_sorted_net_if()
    if not dev_int:
        err_msg = "Cannot get any physical interface from the host"
        raise MacvtapGetBaseInterfaceError(details=err_msg)

    if base_interface and base_interface in dev_int:
        base_inter = Interface(base_interface)
        if (not base_inter.is_brport()) and base_inter.is_up():
            tap_base_device = base_interface

    if not tap_base_device:
        if base_interface:
            warn_msg = "Can not use '%s' as macvtap base interface, "
            warn_msg += "will choice automatically"
            logging.warn(warn_msg % base_interface)
        for interface in dev_int:
            base_inter = Interface(interface)
            if base_inter.is_brport():
                continue
            if base_inter.is_up():
                tap_base_device = interface
                break

    if not tap_base_device:
        err_msg = ("Could not find a valid physical interface to create "
                   "macvtap, make sure the interface is up and it does not "
                   "belong to any bridge.")
        raise MacvtapGetBaseInterfaceError(details=err_msg)
    return tap_base_device


def create_macvtap(ifname, mode="vepa", base_if=None, mac_addr=None):
    """
    Create Macvtap device, return a object of Macvtap

    :param ifname: macvtap interface name
    :param mode:  macvtap type mode ("vepa, bridge,..)
    :param base_if: physical interface to create macvtap
    :param mac_addr: macvtap mac address
    """
    try:
        base_if = get_macvtap_base_iface(base_if)
        o_macvtap = Macvtap(ifname)
        o_macvtap.create(base_if, mode)
        if mac_addr:
            o_macvtap.set_mac(mac_addr)
        return o_macvtap
    except Exception as e:
        raise MacvtapCreationError(ifname, base_if, e)


def open_macvtap(macvtap_object, queues=1):
    """
    Open a macvtap device and returns its file descriptors which are used by
    fds=<fd1:fd2:..> parameter of qemu

    For single queue, only returns one file descriptor, it's used by
    fd=<fd> legacy parameter of qemu

    If you not have a switch support vepa in you env, run this type case you
    need at least two nic on you host [just workaround]

    :param macvtap_object:  macvtap object
    :param queues: Queue number
    """
    tapfds = []
    for queue in range(int(queues)):
        tapfds.append(str(macvtap_object.open()))
    return ":".join(tapfds)


def create_and_open_macvtap(ifname, mode="vepa", queues=1, base_if=None,
                            mac_addr=None):
    """
    Create a new macvtap device, open it, and return the fds

    :param ifname: macvtap interface name
    :param mode:  macvtap type mode ("vepa, bridge,..)
    :param queues: Queue number
    :param base_if: physical interface to create macvtap
    :param mac_addr: macvtap mac address
    """
    o_macvtap = create_macvtap(ifname, mode, base_if, mac_addr)
    return open_macvtap(o_macvtap, queues)


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

    def _br_ioctl(self, io_cmd, brname, ifname):
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
            self._br_ioctl(arch.SIOCBRADDIF, brname, ifname)
        except IOError as details:
            raise BRAddIfError(ifname, brname, details)

    def del_port(self, brname, ifname):
        """
        Remove a TAP device from bridge

        :param ifname: Name of TAP device
        :param brname: Name of the bridge
        """
        try:
            self._br_ioctl(arch.SIOCBRDELIF, brname, ifname)
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


# Global variable for OpenVSwitch
__ovs = None
__bridge = Bridge()


def __init_openvswitch(func):
    """
    Decorator used for late init of __ovs variable.
    """
    def wrap_init(*args, **kargs):
        global __ovs
        if __ovs is None:
            try:
                __ovs = factory(openvswitch.OpenVSwitchSystem)()
                __ovs.init_system()
                if (not __ovs.check()):
                    raise Exception("Check of OpenVSwitch failed.")
            except Exception as e:
                logging.debug("Host does not support OpenVSwitch: %s", e)

        return func(*args, **kargs)
    return wrap_init


def setup_ovs_vhostuser(hp_num, tmpdir, br_name, port_names,
                        queue_size=None):
    """
    Setup vhostuser interface with openvswitch and dpdk

    :param hp_num: hugepage count number
    :param tmpdir: tmp directory for save openvswitch test files
    :param br_name: name of bridge
    :param port_names: list name of port need to add to bridge
    :param queue_size: size of the multiqueue
    """
    clean_ovs_env(selinux_mode="permissive", page_size=hp_num,
                  clean_ovs=True)

    # Install openvswitch
    if process.system("yum info openvswitch", ignore_status=True) == 0:
        utils_package.package_install("openvswitch")
    if process.system("yum info openvswitch2.11", ignore_status=True) == 0:
        utils_package.package_install("openvswitch2.11")

    # Init ovs
    ovs = factory(openvswitch.OpenVSwitch)(tmpdir)
    ovs.init_new()
    if not ovs.check():
        raise Exception("Check of OpenVSwitch failed.")

    # Create bridge and ports
    ovs.create_bridge(br_name)
    ovs.add_ports(br_name, port_names)

    # Enable multiqueue size
    if queue_size:
        ovs.enable_multiqueue(port_names, int(queue_size))

    return ovs


def clean_ovs_env(run_dir="/var/run/openvswitch", selinux_mode=None,
                  page_size=None, clean_ovs=False):
    """
    Cleanup ovs environment

    :param run_dir: openvswitch run dir
    :param selinux_mode: permissive or enforcing
    :param page_size: size for setting hugepage
    :param clean_ovs: clean ovs service or not
    """
    # Clean dir
    if os.path.exists(run_dir):
        shutil.rmtree(run_dir)
    os.mkdir(run_dir)

    # Recovery selinux
    if selinux_mode:
        utils_selinux.set_status(selinux_mode)

    # Kernel hugepage setting
    if page_size:
        utils_memory.drop_caches()
        utils_memory.set_num_huge_pages(int(page_size))

    # Clean ovs services
    if clean_ovs:
        utils_misc.kill_process_by_pattern("ovsdb-server")
        utils_misc.kill_process_by_pattern("ovs-vswitchd")


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


def is_virtual_network_dev(dev_name):
    """
    :param dev_name: Device name.

    :return: True if dev_name is in virtual/net dir, else false.
    """
    if dev_name in os.listdir("/sys/devices/virtual/net/"):
        return True
    else:
        return False


def find_dnsmasq_listen_address():
    """
    Search all dnsmasq listen addresses.

    :param bridge_name: Name of bridge.
    :param bridge_ip: Bridge ip.
    :return: List of ip where dnsmasq is listening.
    """
    cmd = "ps -Af | grep dnsmasq"
    result = process.run(cmd).stdout_text
    return re.findall("--listen-address (.+?) ", result, re.MULTILINE)


def local_runner(cmd, timeout=None, shell=False):
    return process.run(cmd, verbose=False, timeout=timeout, shell=shell).stdout_text


def local_runner_status(cmd, timeout=None, shell=False):
    return process.run(cmd, verbose=False, timeout=timeout, shell=shell).exit_status


def get_net_if(runner=local_runner, state=".*", qdisc=".*", optional=".*"):
    """
    :param runner: command runner.
    :param state: interface state get from ip link
    :param qdisc: interface qdisc get from ip link
    :param optional: optional match for interface find
    :return: List of network interfaces.
    """
    cmd = "ip link"
    # As the runner converts stdout to unicode on Python2,
    # it has to be converted to string for struct.pack().
    result = str(runner(cmd))
    return re.findall(r"^\d+: (\S+?)[@:].*%s.*%s.*state %s.*$" % (optional, qdisc, state),
                      result,
                      re.MULTILINE)


def get_sorted_net_if():
    """
    Get all network interfaces, but sort them among physical and virtual if.

    :return: Tuple (physical interfaces, virtual interfaces)
    """
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


def get_remote_host_net_ifs(session, state=None):
    """
    Get all network interfaces of remote host and sort them as physical
    and virtual interfaces.

    :param session: remote session object
    :param state: regex used for state
    :return: Tuple of physical and virtual interfaces lists
    """
    phy_interfaces = []
    vir_interfaces = []
    cmd = "ip link"
    if not state:
        state = ".*"
    cmd_output = session.cmd_status_output(cmd)
    if cmd_output[0]:
        exceptions.TestError("Failed to fetch %s from remote"
                             "machine" % cmd)
    else:
        result = cmd_output[1].strip()
    host_interfaces = re.findall(r"^\d+: (\S+?)[@:].*state %s.*$" % (state),
                                 result,
                                 re.MULTILINE)
    for each_path in host_interfaces:
        path = os.path.join(SYSFS_NET_PATH, each_path)
        cmd = "ls %s" % path
        if session.cmd_status_output(cmd)[0]:
            continue
        cmd = "ls %s" % os.path.join(path, "device")
        if session.cmd_status_output(cmd)[0]:
            vir_interfaces.append(str(each_path))
        else:
            phy_interfaces.append(str(each_path))

    return (phy_interfaces, vir_interfaces)


def get_net_if_addrs(if_name, runner=None):
    """
    Get network device ip addresses. ioctl not used because it's not
    compatible with ipv6 address.

    :param if_name: Name of interface.
    :return: List ip addresses of network interface.
    """
    if runner is None:
        runner = local_runner
    cmd = "ip addr show %s" % (if_name)
    result = runner(cmd)
    return {"ipv4": re.findall("inet (.+?)/..?", result, re.MULTILINE),
            "ipv6": re.findall("inet6 (.+?)/...?", result, re.MULTILINE),
            "mac": re.findall("link/ether (.+?) ", result, re.MULTILINE)}


def get_net_if_addrs_win(session, mac_addr):
    """
    Try to get windows guest nic address by serial session

    :param session: serial sesssion
    :param mac_addr:  guest nic mac address
    :return: List ip addresses of network interface.
    """
    ip_address = get_windows_nic_attribute(session, "macaddress",
                                           mac_addr, "IPAddress",
                                           global_switch="nicconfig")
    return {"ipv4": re.findall('(\d+\.\d+\.\d+\.\d+)"', ip_address),
            "ipv6": re.findall('(fe80.*?)"', ip_address)}


def get_net_if_and_addrs(runner=None):
    """
    :return: Dict of interfaces and their addresses {"ifname": addrs}.
    """
    ret = {}
    ifs = get_net_if(runner)
    for iface in ifs:
        ret[iface] = get_net_if_addrs(iface, runner)
    return ret


def get_guest_ip_addr(session, mac_addr, os_type="linux", ip_version="ipv4",
                      linklocal=False, timeout=1):
    """
    Get guest ip addresses by serial session

    :param session: serial session
    :param mac_addr: nic mac address of the nic that you want get
    :param os_type: guest os type, windows or linux
    :param ip_version: guest ip version, ipv4 or ipv6
    :param linklocal: Wether ip address is local or remote
    :param timeout: Timeout for get ip addr
    :return: ip addresses of network interface.
    """
    info_cmd = ""

    timeout = time.time() + timeout
    while time.time() < timeout:
        try:
            if os_type == "linux":
                nic_ifname = get_linux_ifname(session, mac_addr)
                info_cmd = "ifconfig -a; ethtool -S %s" % nic_ifname
                nic_address = get_net_if_addrs(nic_ifname,
                                               session.cmd_output)
            elif os_type == "windows":
                info_cmd = "ipconfig /all"
                nic_address = get_net_if_addrs_win(session, mac_addr)
            else:
                raise ValueError("Unknown os type")

            if ip_version == "ipv4":
                linklocal_prefix = "169.254"
            elif ip_version == "ipv6":
                linklocal_prefix = "fe80"
            else:
                raise ValueError("Unknown ip version type")

            try:
                if linklocal:
                    return [x for x in nic_address[ip_version]
                            if x.lower().startswith(linklocal_prefix)][0]
                else:
                    return [x for x in nic_address[ip_version]
                            if not x.lower().startswith(linklocal_prefix)][0]
            except IndexError:
                time.sleep(1)
        except Exception as err:
            logging.debug(session.cmd_output(info_cmd))
            raise IPAddrGetError(mac_addr, err)

    return None


def convert_netmask(mask):
    """
    Convert string type netmask to int type netmask.

    param mask: string type netmask, eg. 255.255.255.0

    return: int type netmask eg. input '255.255.255.0' return 24
    """
    bin_str = ""
    for bits in mask.split("."):
        bin_str += bin(int(bits))[2:]
    if not bin_str:
        return 0
    return sum(map(int, list(bin_str)))


def set_guest_ip_addr(session, mac, ip_addr,
                      netmask="255.255.255.0", os_type="linux"):
    """
    Get guest ip addresses by serial session, for linux guest, please
    ensure target interface not controlled by NetworkManager service,
    before call this function.

    :param session: serial session
    :param mac: nic mac address of the nic that you want set ip
    :param ip_addr: IP address set to guest
    :param os_type: guest os type, windows or linux

    :return: True if set up guest ip successfully.
    """
    info_cmd = ""
    try:
        if os_type == "linux":
            nic_ifname = get_linux_ifname(session, mac)
            if session.cmd_status("which ip") != 0:
                info_cmd = "ifconfig -a; ethtool -S %s" % nic_ifname
                cmd = ("ifconfig %s %s netmask %s" %
                       (nic_ifname, ip_addr, netmask))
            else:
                if "." in netmask:
                    netmask = convert_netmask(netmask)
                info_cmd = "ip addr show; ethtool -s %s" % nic_ifname
                cmd = ("ip addr add %s/%s dev %s" %
                       (ip_addr, netmask, nic_ifname))
            session.cmd(cmd, timeout=360)
        elif os_type == "windows":
            info_cmd = "ipconfig /all"
            cmd = ("wmic nicconfig where MACAddress='%s' call "
                   "enablestatic '%s','%s'" % (mac, ip_addr, netmask))
            session.cmd(cmd, timeout=360)
        else:
            info_cmd = ""
            raise IPAddrSetError(mac, ip_addr, "Unknown os type")
    except Exception as err:
        logging.debug(session.cmd_output(info_cmd))
        raise IPAddrSetError(mac, ip_addr, err)


def get_guest_nameserver(session):
    """
    Get guest nameserver from serial session for linux guest

    :param session: serial session
    :return: return nameserver
    """
    cmd = "cat /etc/resolv.conf  | grep nameserver"
    output = None
    try:
        output = session.cmd_output(cmd).strip()
        logging.debug("Guest name server is %s" % output)
    except (aexpect.ShellError, aexpect.ShellTimeoutError):
        logging.error("Failed to get the guest's nameserver")
    return output


def restart_guest_network(session, mac_addr=None, os_type="linux",
                          ip_version="ipv4", timeout=240):
    """
    Restart guest network by serial session

    :param session: serial session
    :param mac_addr: nic mac address of the nic that you want restart
    :param os_type: guest os type, windows or linux
    :param ip_version: guest ip version, ipv4 or ipv6
    :param timeout: timeout value for command.
    """
    if os_type == "linux":
        if mac_addr:
            nic_ifname = get_linux_ifname(session, mac_addr)
            restart_cmd = "ifconfig %s up; " % nic_ifname
            restart_cmd += "dhclient -r; "
            if ip_version == "ipv6":
                restart_cmd += "dhclient -6 %s" % nic_ifname
            else:
                restart_cmd += "dhclient %s" % nic_ifname
        else:
            restart_cmd = "dhclient -r; "
            if ip_version == "ipv6":
                restart_cmd += "dhclient -6"
            else:
                restart_cmd += "dhclient"
    elif os_type == "windows":
        if ip_version == "ipv6":
            restart_cmd = 'ipconfig /renew6'
        else:
            restart_cmd = 'ipconfig /renew'
        if mac_addr:
            nic_connectionid = get_windows_nic_attribute(session,
                                                         "macaddress",
                                                         mac_addr,
                                                         "netconnectionid",
                                                         timeout=120)
            restart_cmd += ' "%s"' % nic_connectionid
    session.cmd_output_safe(restart_cmd, timeout=timeout)


def set_net_if_ip(if_name, ip_addr, runner=None):
    """
    Set network device ip addresses. ioctl not used because there is
    incompatibility with ipv6.

    :param if_name: Name of interface.
    :param ip_addr: Interface ip addr in format "ip_address/mask".
    :raise: IfChangeAddrError.
    """
    if runner is None:
        runner = local_runner
    cmd = "ip addr add %s dev %s" % (ip_addr, if_name)
    try:
        runner(cmd)
    except process.CmdError as e:
        raise IfChangeAddrError(if_name, ip_addr, e)


def del_net_if_ip(if_name, ip_addr, runner=None):
    """
    Delete network device ip addresses.

    :param if_name: Name of interface.
    :param ip_addr: Interface ip addr in format "ip_address/mask".
    :raise: IfChangeAddrError.
    """
    if runner is None:
        runner = local_runner
    cmd = "ip addr del %s dev %s" % (ip_addr, if_name)
    try:
        runner(cmd)
    except process.CmdError as e:
        raise IfChangeAddrError(if_name, ip_addr, e)


def get_net_if_operstate(ifname, runner=None):
    """
    Get linux host/guest network device operstate.

    :param if_name: Name of the interface.
    :raise: HwOperstarteGetError.
    """
    if runner is None:
        runner = local_runner
    cmd = "cat /sys/class/net/%s/operstate" % ifname
    try:
        operstate = runner(cmd)
        if "up" in operstate:
            return "up"
        elif "down" in operstate:
            return "down"
        elif "unknown" in operstate:
            return "unknown"
        else:
            raise HwOperstarteGetError(ifname, "operstate is not known.")
    except process.CmdError:
        raise HwOperstarteGetError(ifname, "run operstate cmd error.")


def get_network_cfg_file(iface_name, vm=None):
    """
    Get absolute network cfg file path of the VM or Host.

    :param iface_name: Name of the network interface
    :param vm: VM object, if None uses Host

    :return: absolute path of network script file
    """
    if vm:
        distro = vm.get_distro().lower()
    else:
        distro = platform.platform().lower()
    iface_cfg_file = ""
    if "ubuntu" in distro:
        iface_cfg_file = "/etc/network/interfaces"
    elif "suse" in distro:
        iface_cfg_file = "/etc/sysconfig/network/ifcfg-%s" % (iface_name)
    else:
        iface_cfg_file = "/etc/sysconfig/network-scripts/"
        iface_cfg_file += "ifcfg-%s" % (iface_name)
    return iface_cfg_file


def create_network_script(iface_name, mac_addr, boot_proto, net_mask,
                          vm=None, ip_addr=None, **dargs):
    """
    Form network script with its respective network param for vm or Host.

    :param iface_name: Name of the network interface
    :param mac_addr: Mac address of the network interface
    :param boot_proto: static ip or dhcp of the interface
    :param net_mask: network mask for the interface
    :param vm: VM object, if None uses Host
    :param ip_addr: ip address for the interface
    :param dargs: dict of additional attributes, onboot="yes", start_mode="auto"

    :raise: test.error() if creation of network script fails
    """
    network_param_list = []
    script_file = get_network_cfg_file(iface_name, vm=vm)
    cmd = "cat %s" % script_file
    if vm:
        session = vm.wait_for_login()
        distro = vm.get_distro().lower()
        status, output = session.cmd_status_output(cmd)
        if "ubuntu" in distro:
            if iface_name in output.strip():
                logging.error("network script file for %s already exists in "
                              "guest %s", iface_name, script_file)
                return
        else:
            if not status:
                logging.error("network script file for %s already exists in "
                              "guest %s", iface_name, script_file)
                return
    else:
        distro = platform.platform().lower()
        if "ubuntu" in distro:
            if iface_name in process.run(cmd).stdout_text.strip():
                logging.error("network script file for %s already exists in "
                              "host %s", iface_name, script_file)
                return
        else:
            if os.path.isfile(script_file):
                logging.error("network script file for %s already exists in "
                              "host %s", iface_name, script_file)
                return
    if "ubuntu" in distro:
        network_param_list = ['auto %s' % iface_name, 'iface %s inet %s' %
                              (iface_name, boot_proto), 'netmask %s' %
                              net_mask]
        if ip_addr and (boot_proto.strip().lower() != 'dhcp'):
            network_param_list.append('address %s' % ip_addr)
    else:
        network_param_list = ['NAME=%s' % iface_name, 'BOOTPROTO=%s' %
                              boot_proto, 'NETMASK=%s' % net_mask,
                              'HWADDR=%s' % mac_addr]
        if ip_addr and (boot_proto.strip().lower() != 'dhcp'):
            network_param_list.append('IPADDR=%s' % ip_addr)
        if "suse" in distro.lower():
            network_param_list.append("STARTMODE=%s" %
                                      dargs.get("start_mode", "auto"))
        else:
            network_param_list.append("ONBOOT=%s" % dargs.get("on_boot",
                                                              "yes"))

    cmd = "echo '%s' >> %s"
    for each in network_param_list:
        command = cmd % (each, script_file)
        if vm:
            if session.cmd_status(command):
                raise exceptions.TestError("Failed to create network script file")
        else:
            if process.system(command, shell=True):
                raise exceptions.TestError("Failed to create network script file")
    logging.debug("Network script file created in %s:", script_file)


def ipv6_from_mac_addr(mac_addr):
    """
    Note:
    Only support systems which choose EUI-64
     - Linux support
     - Windows not. Windows generate ipv6 by using a random value.
    :return: Ipv6 address for communication in link range.
    """
    mp = mac_addr.split(":")
    mp[0] = ("%x") % (int(mp[0], 16) ^ 0x2)
    mac_address = "fe80::%s%s:%sff:fe%s:%s%s" % tuple(mp)
    return ":".join(map(lambda x: x.lstrip("0"), mac_address.split(":")))


def refresh_neigh_table(interface_name=None, neigh_address="ff02::1",
                        session=None, timeout=60.0, **dargs):
    """
    Refresh host neighbours table, if interface_name is assigned only refresh
    neighbours of this interface, else refresh the all the neighbours.
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    if isinstance(interface_name, list):
        interfaces = interface_name
    elif isinstance(interface_name, six.string_types):
        interfaces = interface_name.split()
    else:
        interfaces = list(filter(lambda x: "-" not in x, get_net_if()))
        interfaces.remove("lo")

    for interface in interfaces:
        refresh_cmd = "ping6 -c 2 -I %s %s > /dev/null" % (interface,
                                                           neigh_address)
        func(refresh_cmd, timeout=timeout, **dargs)


def get_neighbours_info(neigh_address="", interface_name=None, session=None,
                        timeout=60.0, **dargs):
    """
    Get the neighbours infomation
    """
    refresh_neigh_table(interface_name, neigh_address, session=session,
                        timeout=timeout, **dargs)
    func = process.getoutput
    if session:
        func = session.cmd_output
    cmd = "ip -6 neigh show nud reachable"
    if neigh_address:
        cmd += " %s" % neigh_address
    output = func(cmd, timeout=timeout, **dargs)
    if not output:
        raise VMIPV6NeighNotFoundError(neigh_address)
    all_neigh = {}
    neigh_info = {}
    for line in output.splitlines():
        neigh_address = line.split()[0]
        neigh_info["address"] = neigh_address
        neigh_info["attach_if"] = line.split()[2]
        neigh_mac = line.split()[4]
        neigh_info["mac"] = neigh_mac
        all_neigh[neigh_mac] = neigh_info
        all_neigh[neigh_address] = neigh_info
    return all_neigh


def neigh_reachable(neigh_address, attach_if=None, session=None, timeout=60.0,
                    **dargs):
    """
    Check the neighbour is reachable
    """
    try:
        get_neighbours_info(neigh_address, attach_if, session=session,
                            timeout=timeout, **dargs)
    except VMIPV6NeighNotFoundError:
        return False
    return True


def get_neigh_attch_interface(neigh_address, session=None, timeout=60.0, **dargs):
    """
    Get the interface which can reach the neigh_address
    """
    return get_neighbours_info(neigh_address, session=session, timeout=timeout,
                               **dargs)[neigh_address]["attach_if"]


def get_neigh_mac(neigh_address, session=None, timeout=60.0, **dargs):
    """
    Get neighbour mac by his address
    """
    return get_neighbours_info(neigh_address, session=session, timeout=timeout,
                               **dargs)[neigh_address]["mac"]


def check_add_dnsmasq_to_br(br_name, tmpdir):
    """
    Add dnsmasq for bridge. dnsmasq could be added only if bridge
    has assigned ip address.

    :param bridge_name: Name of bridge.
    :param bridge_ip: Bridge ip.
    :param tmpdir: Tmp dir for save pid file and ip range file.
    :return: When new dnsmasq is started name of pidfile  otherwise return
             None because system dnsmasq is already started on bridge.
    """
    br_ips = get_net_if_addrs(br_name)["ipv4"]
    if not br_ips:
        raise BRIpError(br_name)
    dnsmasq_listen = find_dnsmasq_listen_address()
    dhcp_ip_start = br_ips[0].split(".")
    dhcp_ip_start[3] = "128"
    dhcp_ip_start = ".".join(dhcp_ip_start)

    dhcp_ip_end = br_ips[0].split(".")
    dhcp_ip_end[3] = "254"
    dhcp_ip_end = ".".join(dhcp_ip_end)

    pidfile = ("%s-dnsmasq.pid") % (br_ips[0])
    leases = ("%s.leases") % (br_ips[0])

    if not (set(br_ips) & set(dnsmasq_listen)):
        logging.debug("There is no dnsmasq on br %s."
                      "Starting new one." % (br_name))
        process.run("/usr/sbin/dnsmasq --strict-order --bind-interfaces"
                    " --pid-file=%s --conf-file= --except-interface lo"
                    " --listen-address %s --dhcp-range %s,%s --dhcp-leasefile=%s"
                    " --dhcp-lease-max=127 --dhcp-no-override" %
                    (os.path.join(tmpdir, pidfile), br_ips[0], dhcp_ip_start,
                     dhcp_ip_end, (os.path.join(tmpdir, leases))))
        return pidfile
    return None


@__init_openvswitch
def find_bridge_manager(br_name, ovs=None):
    """
    Finds bridge which contain interface iface_name.

    :param br_name: Name of interface.
    :return: (br_manager) which contain bridge or None.
    """
    if ovs is None:
        ovs = __ovs
    # find ifname in standard linux bridge.
    if br_name in __bridge.list_br():
        return __bridge
    elif ovs is not None and br_name in ovs.list_br():
        return ovs
    else:
        return None


@__init_openvswitch
def find_current_bridge(iface_name, ovs=None):
    """
    Finds bridge which contains interface iface_name.

    :param iface_name: Name of interface.
    :return: (br_manager, Bridge) which contain iface_name or None.
    """
    if ovs is None:
        ovs = __ovs
    # find ifname in standard linux bridge.
    master = __bridge
    bridge = master.port_to_br(iface_name)
    if bridge is None and ovs:
        master = ovs
        bridge = master.port_to_br(iface_name)

    if bridge is None:
        master = None

    return (master, bridge)


@__init_openvswitch
def change_iface_bridge(ifname, new_bridge, ovs=None):
    """
    Change bridge on which interface was added.

    :param ifname: Iface name or Iface struct.
    :param new_bridge: Name of new bridge.
    """
    if ovs is None:
        ovs = __ovs
    br_manager_new = find_bridge_manager(new_bridge, ovs)
    if br_manager_new is None:
        raise BRNotExistError(new_bridge, "")

    if isinstance(ifname, six.string_types):
        (br_manager_old, br_old) = find_current_bridge(ifname, ovs)
        if br_manager_old is not None:
            br_manager_old.del_port(br_old, ifname)
        br_manager_new.add_port(new_bridge, ifname)
    elif issubclass(type(ifname), VirtIface):
        br_manager_old = find_bridge_manager(ifname.netdst, ovs)
        if br_manager_old is not None:
            br_manager_old.del_port(ifname.netdst, ifname.ifname)
        br_manager_new.add_port(new_bridge, ifname.ifname)
        ifname.netdst = new_bridge
    else:
        raise ValueError("Network interface %s is wrong type %s." %
                         (ifname, new_bridge))


@__init_openvswitch
def ovs_br_exists(brname, ovs=None):
    """
    Check if bridge exists or not on OVS system

    :param brname: Name of the bridge
    :param ovs: OpenVSwitch object.
    """
    if ovs is None:
        ovs = __ovs

    if ovs is not None:
        return brname in ovs.list_br()
    else:
        raise exceptions.TestError("Host does not support OpenVSwitch")


@__init_openvswitch
def add_ovs_bridge(brname, ovs=None):
    """
    Add a bridge to ovs

    :param brname: Name of the bridge
    :param ovs: OpenVSwitch object.
    """
    if ovs is None:
        ovs = __ovs

    if not ovs_br_exists(brname, ovs):
        ovs.add_br(brname)


@__init_openvswitch
def del_ovs_bridge(brname, ovs=None):
    """
    Delete a bridge from ovs

    :param brname: Name of the bridge
    :param ovs: OpenVSwitch object.
    """
    if ovs is None:
        ovs = __ovs

    if ovs_br_exists(brname, ovs):
        ovs.del_br(brname)
    else:
        raise BRNotExistError(brname, "")


@__init_openvswitch
def add_to_bridge(ifname, brname, ovs=None):
    """
    Add a TAP device to bridge

    :param ifname: Name of TAP device
    :param brname: Name of the bridge
    :param ovs: OpenVSwitch object.
    """
    if ovs is None:
        ovs = __ovs

    _ifname = None
    if isinstance(ifname, six.string_types):
        _ifname = ifname
    elif issubclass(type(ifname), VirtIface):
        _ifname = ifname.ifname

    if brname in __bridge.list_br():
        # Try add port to standard bridge or openvswitch in compatible mode.
        __bridge.add_port(brname, _ifname)
        return

    if ovs is None:
        raise BRAddIfError(ifname, brname, "There is no bridge in system.")
    # Try add port to OpenVSwitch bridge.
    if brname in ovs.list_br():
        ovs.add_port(brname, ifname)


@__init_openvswitch
def del_from_bridge(ifname, brname, ovs=None):
    """
    Del a TAP device to bridge

    :param ifname: Name of TAP device
    :param brname: Name of the bridge
    :param ovs: OpenVSwitch object.
    """
    if ovs is None:
        ovs = __ovs

    _ifname = None
    if isinstance(ifname, six.string_types):
        _ifname = ifname
    elif issubclass(type(ifname), VirtIface):
        _ifname = ifname.ifname

    if ovs is None:
        raise BRDelIfError(ifname, brname, "There is no bridge in system.")

    if brname in __bridge.list_br():
        # Try add port to standard bridge or openvswitch in compatible mode.
        __bridge.del_port(brname, _ifname)
        return

    # Try add port to OpenVSwitch bridge.
    if brname in ovs.list_br():
        ovs.del_port(brname, _ifname)


@__init_openvswitch
def openflow_manager(br_name, command, flow_options=None, ovs=None):
    """
    Manager openvswitch flow rules

    :param br_name: name of the bridge
    :param command: manager cmd(add-flow, del-flows, dump-flows..)
    :param flow_options: open flow options
    :param ovs: OpenVSwitch object.
    """
    if ovs is None:
        ovs = __ovs

    if ovs is None or br_name not in ovs.list_br():
        raise OpenflowSwitchError(br_name)

    manager_cmd = "ovs-ofctl %s %s" % (command, br_name)
    if flow_options:
        manager_cmd += " %s" % flow_options
    return process.run(manager_cmd)


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


def if_set_macaddress(ifname, mac):
    """
    Set the mac address for an interface

    :param ifname: Name of the interface
    :param mac: Mac address
    """
    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)

    ifr = struct.pack("256s", ifname.encode())
    try:
        mac_dev = fcntl.ioctl(ctrl_sock, arch.SIOCGIFHWADDR, ifr)[18:24]
        mac_dev = ":".join(["%02x" % ord(m) for m in mac_dev])
    except IOError as e:
        raise HwAddrGetError(ifname)

    if mac_dev.lower() == mac.lower():
        return

    ifr = struct.pack("16sH14s", ifname.encode(), 1,
                      b"".join([chr(int(m, 16)) for m in mac.split(":")]))
    try:
        fcntl.ioctl(ctrl_sock, arch.SIOCSIFHWADDR, ifr)
    except IOError as e:
        logging.info(e)
        raise HwAddrSetError(ifname, mac)
    ctrl_sock.close()


class IPv6Manager(propcan.PropCanBase):

    """
    Setup and cleanup IPv6 environment.
    """

    __slots__ = ('server_ip', 'server_user', 'server_pwd', 'server_ifname',
                 'client_ifname', 'client_ipv6_addr', 'server_ipv6_addr',
                 'client', 'port', 'runner', 'prompt', 'session',
                 'auto_recover', 'check_ipv6_connectivity', 'client_ipv6_added',
                 'server_ipv6_added')

    def __init__(self, *args, **dargs):
        init_dict = dict(*args, **dargs)
        init_dict['server_ip'] = init_dict.get('server_ip', 'SERVER.IP')
        init_dict['server_user'] = init_dict.get('server_user', 'root')
        init_dict['server_pwd'] = init_dict.get('server_pwd', None)
        init_dict['server_ifname'] = init_dict.get('server_ifname', 'eth0')
        init_dict['server_ipv6_addr'] = init_dict.get('server_ipv6_addr')
        init_dict['client_ifname'] = init_dict.get('client_ifname', 'eth0')
        init_dict['client_ipv6_addr'] = init_dict.get('client_ipv6_addr')
        init_dict['client'] = init_dict.get('client', 'ssh')
        init_dict['port'] = init_dict.get('port', 22)
        init_dict['prompt'] = init_dict.get('prompt', r"[\#\$]\s*$")
        init_dict['auto_recover'] = init_dict.get('auto_recover', False)
        init_dict['check_ipv6_connectivity'] = \
            init_dict.get('check_ipv6_connectivity', 'yes')
        init_dict['client_ipv6_added'] = False
        init_dict['server_ipv6_added'] = False

        self.__dict_set__('session', None)
        super(IPv6Manager, self).__init__(init_dict)

    def __del__(self):
        """
        Close opened session and recover network configuration.
        """
        self.close_session()
        if self.auto_recover:
            try:
                self.cleanup()
            except Exception:
                raise exceptions.TestError(
                    "Failed to cleanup test environment")

    def _new_session(self):
        """
        Build a new server session.
        """
        port = self.port
        prompt = self.prompt
        host = self.server_ip
        client = self.client
        username = self.server_user
        password = self.server_pwd

        try:
            session = remote.wait_for_login(client, host, port,
                                            username, password, prompt)
        except remote.LoginTimeoutError:
            raise exceptions.TestError(
                "Got a timeout error when login to server.")
        except remote.LoginAuthenticationError:
            raise exceptions.TestError(
                "Authentication failed to login to server.")
        except remote.LoginProcessTerminatedError:
            raise exceptions.TestError(
                "Host terminates during login to server.")
        except remote.LoginError:
            raise exceptions.TestError(
                "Some error occurs login to client server.")
        return session

    def get_session(self):
        """
        Make sure the session is alive and available
        """
        session = self.__dict_get__('session')

        if (session is not None) and (session.is_alive()):
            return session
        else:
            session = self._new_session()

        self.__dict_set__('session', session)
        return session

    def close_session(self):
        """
        If the session exists then close it.
        """
        if self.session:
            self.session.close()

    def get_addr_list(self, runner=None):
        """
        Get IPv6 address list from local and remote host.
        """
        ipv6_addr_list = []

        if not runner:
            ipv6_addr_list = get_net_if_addrs(self.client_ifname).get("ipv6")
            logging.debug("Local IPv6 address list: %s", ipv6_addr_list)
        else:
            ipv6_addr_list = get_net_if_addrs(self.server_ifname,
                                              runner).get("ipv6")
            logging.debug("remote IPv6 address list: %s", ipv6_addr_list)

        return ipv6_addr_list

    @staticmethod
    def check_connectivity(client_ifname, server_ipv6, count=5):
        """
        Check IPv6 network connectivity
        :param client_ifname: client network interface name
        :param server_ipv6: server IPv6 address
        :param count: sending packets counts, default is 5
        """
        try:
            utils_path.find_command("ping6")
        except utils_path.CmdNotFoundError:
            raise exceptions.TestSkipError("Can't find ping6 command")
        command = "ping6 -I %s %s -c %s" % (client_ifname, server_ipv6, count)
        result = process.run(command, ignore_status=True)
        if result.exit_status:
            raise exceptions.TestSkipError("The '%s' destination is "
                                           "unreachable: %s", server_ipv6,
                                           result.stderr_text)
        else:
            logging.info("The '%s' destination is connectivity!", server_ipv6)

    def flush_ip6tables(self):
        """
        Refresh IPv6 firewall rules
        """
        flush_cmd = "ip6tables -F"
        find_ip6tables_cmd = "which ip6tables"
        test_skip_err = "Can't find ip6tables command"
        test_fail_err = "Failed to flush 'icmp6-adm-prohibited' rule"
        flush_cmd_pass = "Succeed to run command '%s'" % flush_cmd
        # check if ip6tables command exists on the local
        try:
            utils_path.find_command("ip6tables")
        except utils_path.CmdNotFoundError:
            raise exceptions.TestSkipError(test_skip_err)
        # flush local ip6tables rules
        result = process.run(flush_cmd, ignore_status=True)
        if result.exit_status:
            raise exceptions.TestFail("%s on local host:%s" %
                                      (test_fail_err,
                                       result.stderr_text))
        else:
            logging.info("%s on the local host", flush_cmd_pass)

        # check if ip6tables command exists on the remote
        if self.session.cmd_status(find_ip6tables_cmd):
            raise exceptions.TestSkipError(test_skip_err)
        # flush remote ip6tables rules
        if self.session.cmd_status(flush_cmd):
            raise exceptions.TestFail("%s on the remote host" % test_fail_err)
        else:
            logging.info("%s on the remote host", flush_cmd_pass)

    def setup(self):
        """
        Setup IPv6 network environment.
        """
        self.session = self.get_session()
        runner = self.session.cmd_output

        try:
            logging.info("Prepare to configure IPv6 test environment...")
            local_ipv6_addr_list = self.get_addr_list()

            # the ipv6 address looks like this '3efe::101/64'
            ipv6_addr_src = self.client_ipv6_addr.split('/')[0]
            ipv6_addr_des = self.server_ipv6_addr.split('/')[0]

            # configure global IPv6 address for local host
            if ipv6_addr_src not in local_ipv6_addr_list:
                set_net_if_ip(self.client_ifname, self.client_ipv6_addr)
                self.client_ipv6_added = True
            else:
                logging.debug(
                    "Skip to add the existing ipv6 address %s",
                    ipv6_addr_src)

            self.session = self.get_session()
            runner = self.session.cmd_output
            remote_ipv6_addr_list = self.get_addr_list(runner)

            # configure global IPv6 address for remote host
            if ipv6_addr_des not in remote_ipv6_addr_list:
                set_net_if_ip(
                    self.server_ifname,
                    self.server_ipv6_addr,
                    runner)
                self.server_ipv6_added = True
            else:
                logging.debug(
                    "Skip to add the existing ipv6 address %s",
                    ipv6_addr_des)

            # check IPv6 network connectivity
            if self.check_ipv6_connectivity == "yes":
                # the ipv6 address looks like this '3efe::101/64'
                ipv6_addr_des = self.server_ipv6_addr.split('/')[0]
                self.check_connectivity(self.client_ifname, ipv6_addr_des)
            # flush ip6tables both local and remote host
            self.flush_ip6tables()
        except Exception as e:
            self.close_session()
            raise exceptions.TestError(
                "Failed to setup IPv6 environment!!:%s", e)

    def cleanup(self):
        """
        Cleanup IPv6 network environment.
        """
        logging.info("Prepare to clean up IPv6 test environment...")
        local_ipv6_addr_list = self.get_addr_list()

        # the ipv6 address looks like this '3efe::101/64'
        ipv6_addr_src = self.client_ipv6_addr.split('/')[0]
        ipv6_addr_des = self.server_ipv6_addr.split('/')[0]

        # delete global IPv6 address from local host
        if (ipv6_addr_src in local_ipv6_addr_list) and self.client_ipv6_added:
            del_net_if_ip(self.client_ifname, self.client_ipv6_addr)

        self.session = self.get_session()
        runner = self.session.cmd_output
        remote_ipv6_addr_list = self.get_addr_list(runner)
        # delete global IPv6 address from remote host
        if (ipv6_addr_des in remote_ipv6_addr_list) and self.server_ipv6_added:
            del_net_if_ip(self.server_ifname, self.server_ipv6_addr, runner)

        # make sure opening session is closed
        self.close_session()


def ieee_eui_generator(base, mask, start=0, repeat=False):
    """
    IEEE extended unique identifier(EUI) generator.

    :param base: The base identifier number.
    :param mask: The mask to calculate identifiers.
    :param start: The ordinal number of the first identifier.
    :param repeat: Whether use repeated identifiers when exhausted.

    :return generator: The target EUI generator.
    """
    offset = 0
    while True:
        out = base + ((start + offset) & mask)
        yield out
        offset += 1
        if offset > mask:
            if not repeat:
                break
            offset = 0


def ieee_eui_assignment(eui_bits):
    """
    IEEE EUI assignment.

    :param eui_bits: The number of EUI bits.
    """
    def assignment(oui_bits, prefix=0, repeat=False):
        """
        The template of assignment.

        :param oui_bits: The number of OUI bits.
        :param prefix: The prefix of OUI, for example 0x9a.
        :param repeat: Whether use repeated identifiers when exhausted.
        """
        # Using UUID1 combine with `__file__` to avoid getting the same hash
        data = uuid.uuid1().hex + __file__
        data = hashlib.sha256(data.encode()).digest()[:(eui_bits // 8)]
        sample = 0
        for num in bytearray(data):
            sample <<= 8
            sample |= num
        bits = eui_bits - oui_bits
        mask = (1 << bits) - 1
        start = sample & mask
        base = sample ^ start
        if prefix > 0:
            pbits = eui_bits + (-(prefix.bit_length()) // 4) * 4
            pmask = (1 << pbits) - 1
            prefix <<= pbits
            base = prefix | (base & pmask)
        return ieee_eui_generator(base, mask, start, repeat=repeat)
    return assignment


ieee_eui48_assignment = ieee_eui_assignment(48)
ieee_eui64_assignment = ieee_eui_assignment(64)


class VirtIface(propcan.PropCan, object):

    """
    Networking information for single guest interface and host connection.
    """

    __slots__ = ['nic_name', 'g_nic_name', 'mac', 'nic_model', 'ip',
                 'nettype', 'netdst', 'queues', 'net_driver']
    # Using MA-S assignment here, that means we can have at most 4096 unique
    # identifiers (MAC addresses) on the same job instance. We may consider
    # using bigger blocks for large-scale deployment, such as microVM
    # applications
    EUI48_ASSIGNMENT = ieee_eui48_assignment(36, repeat=True)

    def __getstate__(self):
        state = {}
        for key in self.__class__.__all_slots__:
            if key in self:
                state[key] = self[key]
        return state

    def __setstate__(self, state):
        self.__init__(state)

    @classmethod
    def name_is_valid(cls, nic_name):
        """
        Corner-case prevention where nic_name is not a sane string value
        """
        try:
            return isinstance(nic_name, six.string_types) and len(nic_name) > 1
        except (TypeError, KeyError, AttributeError):
            return False

    @classmethod
    def mac_is_valid(cls, mac):
        try:
            mac = cls.mac_str_to_int_list(mac)
        except TypeError:
            return False
        return True  # Though may be less than 6 bytes

    @classmethod
    def mac_str_to_int_list(cls, mac):
        """
        Convert list of string bytes to int list
        """
        if isinstance(mac, (str, unicode)):
            mac = mac.split(':')
        # strip off any trailing empties
        for rindex in xrange(len(mac), 0, -1):
            if not mac[rindex - 1].strip():
                del mac[rindex - 1]
            else:
                break
        try:
            assert len(mac) < 7
            for byte_str_index in xrange(0, len(mac)):
                byte_str = mac[byte_str_index]
                assert isinstance(byte_str, (str, unicode))
                assert len(byte_str) > 0
                try:
                    value = eval("0x%s" % byte_str, {}, {})
                except SyntaxError:
                    raise AssertionError
                assert value >= 0x00
                assert value <= 0xFF
                mac[byte_str_index] = value
        except AssertionError:
            raise TypeError("%s %s is not a valid MAC format "
                            "string or list" % (str(mac.__class__),
                                                str(mac)))
        return mac

    @classmethod
    def int_list_to_mac_str(cls, mac_bytes):
        """
        Return string formatting of int mac_bytes
        """
        for byte_index in xrange(0, len(mac_bytes)):
            mac = mac_bytes[byte_index]
            # Project standardized on lower-case hex
            if mac < 16:
                mac_bytes[byte_index] = "0%x" % mac
            else:
                mac_bytes[byte_index] = "%x" % mac
        return mac_bytes

    @staticmethod
    def _int_to_int_list(number, align=0):
        """
        Convert integer to integer list split by byte.
        """
        out = []
        while number > 0:
            out.insert(0, number & 0xff)
            number >>= 8
        if not out:
            out.append(0)
        blen = len(out)
        if align > blen:
            out = ([0] * (align - blen)) + out
        return out

    @classmethod
    def _generate_eui48(cls, prefix=None):
        """
        Generate EUI-48.
        """
        out = next(cls.EUI48_ASSIGNMENT)
        out = cls._int_to_int_list(out, 6)
        if prefix:
            for idx, num in enumerate(prefix):
                out[idx] = num
        return out

    @classmethod
    def complete_mac_address(cls, mac):
        """
        Append randomly generated byte strings to make mac complete

        :param mac: String or list of mac bytes (possibly incomplete)
        :raise: TypeError if mac is not a string or a list
        """
        mac = cls.mac_str_to_int_list(mac)
        nr_bytes = len(mac)
        assert not (nr_bytes > 6)
        if nr_bytes < 6:
            mac = cls._generate_eui48(mac)
        return ":".join(cls.int_list_to_mac_str(mac))


class LibvirtIface(VirtIface):

    """
    Networking information specific to libvirt
    """
    __slots__ = []


class QemuIface(VirtIface):

    """
    Networking information specific to Qemu
    """
    __slots__ = ['vlan', 'device_id', 'ifname', 'tapfds',
                 'tapfd_ids', 'netdev_id', 'tftp',
                 'romfile', 'nic_extra_params',
                 'netdev_extra_params', 'queues', 'vhostfds',
                 'vectors']


class VMNet(list):

    """
    Collection of networking information.
    """

    # don't flood discard warnings
    DISCARD_WARNINGS = 10

    # __init__ must not presume clean state, it should behave
    # assuming there is existing properties/data on the instance
    # and take steps to preserve or update it as appropriate.
    def __init__(self, container_class=VirtIface, virtiface_list=[]):
        """
        Initialize from list-like virtiface_list using container_class
        """
        if container_class != VirtIface and (
                not issubclass(container_class, VirtIface)):
            raise TypeError("Container class must be Base_VirtIface "
                            "or subclass not a %s" % str(container_class))
        self.container_class = container_class
        super(VMNet, self).__init__([])
        if isinstance(virtiface_list, list):
            for virtiface in virtiface_list:
                self.append(virtiface)
        else:
            raise VMNetError

    def __getstate__(self):
        return [nic for nic in self]

    def __setstate__(self, state):
        VMNet.__init__(self, self.container_class, state)

    def __getitem__(self, index_or_name):
        if isinstance(index_or_name, six.string_types):
            index_or_name = self.nic_name_index(index_or_name)
        return super(VMNet, self).__getitem__(index_or_name)

    def __setitem__(self, index_or_name, value):
        if not isinstance(value, dict):
            raise VMNetError
        if self.container_class.name_is_valid(value['nic_name']):
            if isinstance(index_or_name, six.string_types):
                index_or_name = self.nic_name_index(index_or_name)
            self.process_mac(value)
            super(VMNet, self).__setitem__(index_or_name,
                                           self.container_class(value))
        else:
            raise VMNetError

    def __delitem__(self, index_or_name):
        if isinstance(index_or_name, six.string_types):
            index_or_name = self.nic_name_index(index_or_name)
        super(VMNet, self).__delitem__(index_or_name)

    def subclass_pre_init(self, params, vm_name):
        """
        Subclasses must establish style before calling VMNet. __init__()
        """
        # TODO: Get rid of this function.  it's main purpose is to provide
        # a shared way to setup style (container_class) from params+vm_name
        # so that unittests can run independently for each subclass.
        self.vm_name = vm_name
        self.params = params.object_params(self.vm_name)
        self.vm_type = self.params.get('vm_type', 'default')
        self.driver_type = self.params.get('driver_type', 'default')
        for key, value in list(VMNetStyle(self.vm_type,
                                          self.driver_type).items()):
            setattr(self, key, value)

    def process_mac(self, value):
        """
        Strips 'mac' key from value if it's not valid
        """
        original_mac = mac = value.get('mac')
        if mac:
            mac = value['mac'] = value['mac'].lower()
            if len(mac.split(':')
                   ) == 6 and self.container_class.mac_is_valid(mac):
                return
            else:
                del value['mac']  # don't store invalid macs
                # Notify user about these, but don't go crazy
                if self.__class__.DISCARD_WARNINGS >= 0:
                    logging.warning('Discarded invalid mac "%s" for nic "%s" '
                                    'from input, %d warnings remaining.'
                                    % (original_mac,
                                       value.get('nic_name'),
                                       self.__class__.DISCARD_WARNINGS))
                    self.__class__.DISCARD_WARNINGS -= 1

    def mac_list(self):
        """
        Return a list of all mac addresses used by defined interfaces
        """
        return [nic.mac for nic in self if hasattr(nic, 'mac')]

    def append(self, value):
        newone = self.container_class(value)
        newone_name = newone['nic_name']
        if newone.name_is_valid(newone_name) and (
                newone_name not in self.nic_name_list()):
            self.process_mac(newone)
            super(VMNet, self).append(newone)
        else:
            raise VMNetError

    def nic_name_index(self, name):
        """
        Return the index number for name, or raise KeyError
        """
        if not isinstance(name, six.string_types):
            raise TypeError("nic_name_index()'s nic_name must be a string")
        nic_name_list = self.nic_name_list()
        try:
            return nic_name_list.index(name)
        except ValueError:
            raise IndexError("Can't find nic named '%s' among '%s'" %
                             (name, nic_name_list))

    def nic_name_list(self):
        """
        Obtain list of nic names from lookup of contents 'nic_name' key.
        """
        namelist = []
        for item in self:
            # Rely on others to throw exceptions on 'None' names
            namelist.append(item['nic_name'])
        return namelist

    def nic_lookup(self, prop_name, prop_value):
        """
        Return the first index with prop_name key matching prop_value or None
        """
        for nic_index in xrange(0, len(self)):
            if prop_name in self[nic_index]:
                if self[nic_index][prop_name] == prop_value:
                    return nic_index
        return None


# TODO: Subclass VMNet into Qemu/Libvirt variants and
# pull them, along with ParmasNet and maybe DbNet based on
# Style definitions.  i.e. libvirt doesn't need DbNet at all,
# but could use some custom handling at the VMNet layer
# for xen networking.  This will also enable further extensions
# to network information handing in the future.
class VMNetStyle(dict):

    """
    Make decisions about needed info from vm_type and driver_type params.
    """

    # Keyd first by vm_type, then by driver_type.
    VMNet_Style_Map = {
        'default': {
            'default': {
                'mac_prefix': '9a',
                'container_class': QemuIface,
            }
        },
        'libvirt': {
            'default': {
                'mac_prefix': '9a',
                'container_class': LibvirtIface,
            },
            'qemu': {
                'mac_prefix': '52:54:00',
                'container_class': LibvirtIface,
            },
            'xen': {
                'mac_prefix': '00:16:3e',
                'container_class': LibvirtIface,
            }
        }
    }

    def __new__(cls, vm_type, driver_type):
        return cls.get_style(vm_type, driver_type)

    @classmethod
    def get_vm_type_map(cls, vm_type):
        return cls.VMNet_Style_Map.get(vm_type,
                                       cls.VMNet_Style_Map['default'])

    @classmethod
    def get_driver_type_map(cls, vm_type_map, driver_type):
        return vm_type_map.get(driver_type,
                               vm_type_map['default'])

    @classmethod
    def get_style(cls, vm_type, driver_type):
        style = cls.get_driver_type_map(cls.get_vm_type_map(vm_type),
                                        driver_type)
        return style


class ParamsNet(VMNet):

    """
    Networking information from Params

        Params contents specification-
            vms = <vm names...>
            nics = <nic names...>
            nics_<vm name> = <nic names...>
            # attr: mac, ip, model, nettype, netdst, etc.
            <attr> = value
            <attr>_<nic name> = value
    """

    # __init__ must not presume clean state, it should behave
    # assuming there is existing properties/data on the instance
    # and take steps to preserve or update it as appropriate.

    def __init__(self, params, vm_name):
        self.subclass_pre_init(params, vm_name)
        # use temporary list to initialize
        result_list = []
        nic_name_list = self.params.objects('nics')
        for nic_name in nic_name_list:
            nic_name = str(nic_name)
            # nic name is only in params scope
            nic_dict = {'nic_name': nic_name}
            nic_params = self.params.object_params(nic_name)
            # set default values for the nic
            nic_params = self.__set_default_params__(nic_name, nic_params)
            # avoid processing unsupported properties
            proplist = list(self.container_class().__all_slots__)
            # nic_name was already set, remove from __slots__ list copy
            del proplist[proplist.index('nic_name')]
            for propertea in proplist:
                # Merge existing propertea values if they exist
                try:
                    existing_value = getattr(self[nic_name], propertea, None)
                except ValueError:
                    existing_value = None
                except IndexError:
                    existing_value = None
                nic_dict[propertea] = nic_params.get(propertea, existing_value)
                if propertea == "netdst" and "shell:" in nic_dict[propertea]:
                    nic_dict[propertea] = process.getoutput(
                        nic_dict[propertea].split(':', 1)[1])
                    if not nic_dict[propertea]:
                        raise exceptions.TestError(
                            "netdst is null, please check the shell command")
            result_list.append(nic_dict)
        VMNet.__init__(self, self.container_class, result_list)

    def __set_default_params__(self, nic_name, nic_params):
        """
        Use params to overwrite defaults from  DbParams

        param: nic_name: nic name (string)
        param: nic_params: params contain nic properties(like dict)
        """
        default_params = {}
        default_params['queues'] = 1
        default_params['tftp'] = None
        default_params['romfile'] = None
        default_params['nic_extra_params'] = ''
        default_params['netdev_extra_params'] = ''
        nic_name_list = self.params.objects('nics')
        default_params['vlan'] = str(nic_name_list.index(nic_name))
        for key, val in list(default_params.items()):
            nic_params.setdefault(key, val)

        return nic_params

    def mac_index(self):
        """
        Generator over mac addresses found in params
        """
        for nic_name in self.params.get('nics'):
            nic_obj_params = self.params.object_params(nic_name)
            mac = nic_obj_params.get('mac')
            if mac:
                yield mac
            else:
                continue

    def reset_mac(self, index_or_name):
        """
        Reset to mac from params if defined and valid, or undefine.
        """
        nic = self[index_or_name]
        nic_name = nic.nic_name
        nic_params = self.params.object_params(nic_name)
        params_mac = nic_params.get('mac')
        if params_mac and self.container_class.mac_is_valid(params_mac):
            new_mac = params_mac.lower()
        else:
            new_mac = None
        nic.mac = new_mac

    def reset_ip(self, index_or_name):
        """
        Reset to ip from params if defined and valid, or undefine.
        """
        nic = self[index_or_name]
        nic_name = nic.nic_name
        nic_params = self.params.object_params(nic_name)
        params_ip = nic_params.get('ip')
        if params_ip:
            new_ip = params_ip
        else:
            new_ip = None
        nic.ip = new_ip


class DbNet(VMNet):

    """
    Networking information from database

        Database specification-
            database values are python string-formatted lists of dictionaries
    """

    # __init__ must not presume clean state, it should behave
    # assuming there is existing properties/data on the instance
    # and take steps to preserve or update it as appropriate.

    def __init__(self, params, vm_name, db_filename, db_key):
        self.subclass_pre_init(params, vm_name)
        self.db_key = db_key
        self.db_filename = db_filename
        self.db_lockfile = db_filename + ".lock"
        # Merge (don't overwrite) existing propertea values if they
        # exist in db
        try:
            self.lock_db()
            entry = self.db_entry()
        except KeyError:
            entry = []
        self.unlock_db()
        proplist = list(self.container_class().__all_slots__)
        # nic_name was already set, remove from __slots__ list copy
        del proplist[proplist.index('nic_name')]
        nic_name_list = self.nic_name_list()
        for db_nic in entry:
            nic_name = db_nic['nic_name']
            if nic_name in nic_name_list:
                for propertea in proplist:
                    # only set properties in db but not in self
                    if propertea in db_nic:
                        self[nic_name].set_if_none(
                            propertea, db_nic[propertea])
        if entry:
            VMNet.__init__(self, self.container_class, entry)
        # Assume self.update_db() called elsewhere

    def lock_db(self):
        if not hasattr(self, 'lock'):
            self.lock = utils_misc.lock_file(self.db_lockfile)
            if not hasattr(self, 'db'):
                self.db = shelve.open(self.db_filename)
            else:
                raise DbNoLockError
        else:
            raise DbNoLockError

    def unlock_db(self):
        if hasattr(self, 'db'):
            self.db.close()
            del self.db
            if hasattr(self, 'lock'):
                utils_misc.unlock_file(self.lock)
                del self.lock
            else:
                raise DbNoLockError
        else:
            raise DbNoLockError

    def db_entry(self, db_key=None):
        """
        Returns a python list of dictionaries from locked DB string-format entry
        """
        if not db_key:
            db_key = self.db_key
        try:
            db_entry = self.db[db_key]
        except AttributeError:  # self.db doesn't exist:
            raise DbNoLockError
        # Always wear protection
        try:
            eval_result = eval(db_entry, {}, {})
        except SyntaxError:
            raise ValueError("Error parsing entry for %s from "
                             "database '%s'" % (self.db_key,
                                                self.db_filename))
        if not isinstance(eval_result, list):
            raise ValueError("Unexpected database data: %s" % (
                str(eval_result)))
        result = []
        for result_dict in eval_result:
            if not isinstance(result_dict, dict):
                raise ValueError("Unexpected database sub-entry data %s" % (
                    str(result_dict)))
            result.append(result_dict)
        return result

    def save_to_db(self, db_key=None):
        """
        Writes string representation out to database
        """
        if db_key is None:
            db_key = self.db_key
        data = str(self)
        # Avoid saving empty entries
        if len(data) > 3:
            try:
                self.db[self.db_key] = data
            except AttributeError:
                raise DbNoLockError
        else:
            try:
                # make sure old db entry is removed
                del self.db[db_key]
            except KeyError:
                pass

    def update_db(self):
        self.lock_db()
        self.save_to_db()
        self.unlock_db()

    def mac_index(self):
        """Generator of mac addresses found in database"""
        try:
            for db_key in list(self.db.keys()):
                for nic in self.db_entry(db_key):
                    mac = nic.get('mac')
                    if mac:
                        yield mac
                    else:
                        continue
        except AttributeError:
            raise DbNoLockError


ADDRESS_POOL_FILENAME = os.path.join(data_dir.get_tmp_dir(), "address_pool")
ADDRESS_POOL_LOCK_FILENAME = ADDRESS_POOL_FILENAME + ".lock"


def clean_tmp_files():
    """
    Remove the base address pool filename.
    """
    if os.path.isfile(ADDRESS_POOL_LOCK_FILENAME):
        os.unlink(ADDRESS_POOL_LOCK_FILENAME)
    if os.path.isfile(ADDRESS_POOL_FILENAME):
        os.unlink(ADDRESS_POOL_FILENAME)


class VirtNet(DbNet, ParamsNet):

    """
    Persistent collection of VM's networking information.
    """
    # __init__ must not presume clean state, it should behave
    # assuming there is existing properties/data on the instance
    # and take steps to preserve or update it as appropriate.

    def __init__(self, params, vm_name, db_key,
                 db_filename=ADDRESS_POOL_FILENAME):
        """
        Load networking info. from db, then from params, then update db.

        :param params: Params instance using specification above
        :param vm_name: Name of the VM as might appear in Params
        :param db_key: database key uniquely identifying VM instance
        :param db_filename: database file to cache previously parsed params
        """
        # Params always overrides database content
        DbNet.__init__(self, params, vm_name, db_filename, db_key)
        ParamsNet.__init__(self, params, vm_name)
        self.update_db()

    # Delegating get/setstate() details more to ancestor classes
    # doesn't play well with multi-inheritence.  While possibly
    # more difficult to maintain, hard-coding important property
    # names for pickling works. The possibility also remains open
    # for extensions via style-class updates.
    def __getstate__(self):
        state = {'container_items': VMNet.__getstate__(self)}
        for attrname in ['params', 'vm_name', 'db_key', 'db_filename',
                         'vm_type', 'driver_type', 'db_lockfile']:
            state[attrname] = getattr(self, attrname)
        for style_attr in list(VMNetStyle(self.vm_type, self.driver_type).keys()):
            state[style_attr] = getattr(self, style_attr)
        return state

    def __setstate__(self, state):
        for key in list(state.keys()):
            if key == 'container_items':
                continue  # handle outside loop
            setattr(self, key, state.pop(key))
        VMNet.__setstate__(self, state.pop('container_items'))

    def __eq__(self, other):
        if len(self) != len(other):
            return False
        # Order doesn't matter for most OS's as long as MAC & netdst match
        for nic_name in self.nic_name_list():
            if self[nic_name] != other[nic_name]:
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def mac_index(self):
        """
        Generator for all allocated mac addresses (requires db lock)
        """
        for mac in DbNet.mac_index(self):
            yield mac
        for mac in ParamsNet.mac_index(self):
            yield mac

    def generate_mac_address(self, nic_index_or_name, attempts=1024):
        """
        Set & return valid mac address for nic_index_or_name or raise NetError

        :param nic_index_or_name: index number or name of NIC
        :return: MAC address string
        :raise: NetError if mac generation failed
        """
        nic = self[nic_index_or_name]
        if 'mac' in nic:
            logging.warning("Overwriting mac %s for nic %s with random"
                            % (nic.mac, str(nic_index_or_name)))
        self.free_mac_address(nic_index_or_name)
        attempts_remaining = attempts
        while attempts_remaining > 0:
            mac_attempt = nic.complete_mac_address(self.mac_prefix)
            self.lock_db()
            if mac_attempt not in self.mac_index():
                nic.mac = mac_attempt.lower()
                self.unlock_db()
                self.update_db()
                return self[nic_index_or_name].mac
            else:
                attempts_remaining -= 1
                self.unlock_db()
        raise NetError("%s/%s MAC generation failed with prefix %s after %d "
                       "attempts for NIC %s on VM %s (%s)" % (
                           self.vm_type,
                           self.driver_type,
                           self.mac_prefix,
                           attempts,
                           str(nic_index_or_name),
                           self.vm_name,
                           self.db_key))

    def free_mac_address(self, nic_index_or_name):
        """
        Remove the mac value from nic_index_or_name and cache unless static

        :param nic_index_or_name: index number or name of NIC
        """
        nic = self[nic_index_or_name]
        if 'mac' in nic:
            # Reset to params definition if any, or None
            self.reset_mac(nic_index_or_name)
        self.update_db()

    def set_mac_address(self, nic_index_or_name, mac):
        """
        Set a MAC address to value specified

        :param nic_index_or_name: index number or name of NIC
        :raise: NetError if mac already assigned
        """
        nic = self[nic_index_or_name]
        if 'mac' in nic:
            logging.warning("Overwriting mac %s for nic %s with %s"
                            % (nic.mac, str(nic_index_or_name), mac))
        nic.mac = mac.lower()
        self.update_db()

    def get_mac_address(self, nic_index_or_name):
        """
        Return a MAC address for nic_index_or_name

        :param nic_index_or_name: index number or name of NIC
        :return: MAC address string.
        """
        return self[nic_index_or_name].mac.lower()

    def generate_ifname(self, nic_index_or_name):
        """
        Return and set network interface name
        """
        nic_index = self.nic_name_index(self[nic_index_or_name].nic_name)
        prefix = "t%d-" % nic_index
        postfix = utils_misc.generate_random_string(6)
        # Ensure interface name doesn't excede 11 characters
        self[nic_index_or_name].ifname = (prefix + postfix)[-11:]
        self.update_db()
        return self[nic_index_or_name].ifname


def parse_arp(session=None, timeout=60.0, **dargs):
    """
    Read /proc/net/arp, return a mapping of MAC to IP

    :param session: ShellSession object of remote host
    :param timeout: Timeout for commands executed
    :param dargs: extra options for session/process commands
    :return: dict mapping MAC to IP
    """
    ret = {}
    func = process.getoutput
    if session:
        func = session.cmd_output
    arp_cache = func('cat /proc/net/arp', timeout=timeout,
                     **dargs).strip().split('\n')

    for line in arp_cache:
        mac = line.split()[3]
        ip = line.split()[0]
        flag = line.split()[2]

        # Skip the header
        if mac.count(":") != 5:
            continue

        # Skip the incomplete ARP entries
        if flag == "0x0":
            continue

        ret[mac] = ip

    return ret


def verify_ip_address_ownership(ip, macs, timeout=60.0, devs=None,
                                session=None):
    """
    Make sure a given IP address belongs to one of the given
    MAC addresses.

    :param ip: The IP address to be verified.
    :param macs: A list or tuple of MAC addresses.
    :param timeout: Timeout for retry verifying IP and for commands
    :param devs: A set of network interfaces to check on. If is absent
                 then use route table to get a name for possible
                 network interfaces.
    :param session: ShellSession object of remote host
    :return: True if ip is assigned to a MAC address in macs.
    """
    def __arping(ip, macs, dev, timeout, session=None, **dargs):
        func = process.getoutput
        if session:
            func = session.cmd_output
        # Compile a regex that matches the given IP address and any of the
        # given MAC addresses from arping output
        ip_map = parse_arp(session=session, timeout=timeout, **dargs)
        for mac in macs:
            if ip_map.get(mac) == ip:
                return True

        mac_regex = "|".join("(%s)" % mac for mac in macs)
        regex = re.compile(r"\b%s\b.*\b(%s)\b" % (ip, mac_regex), re.I)
        arping_bin = utils_path.find_command("arping")
        if session:
            arping_bin = func("which arping", timeout=timeout, **dargs).strip()
        cmd = "%s --help" % arping_bin
        if "-C count" in func(cmd, timeout=timeout, **dargs):
            regex = re.compile(r"\b%s\b.*\b(%s)" % (mac_regex, ip), re.I)
            arping_cmd = "%s -C1 -c3 -w%d -I %s %s" % (arping_bin, int(timeout),
                                                       dev, ip)
        else:
            arping_cmd = "%s -f -c3 -w%d -I %s %s" % (arping_bin, int(timeout),
                                                      dev, ip)
        try:
            o = func(arping_cmd, **dargs)
        except (process.CmdError, aexpect.ShellError):
            return False
        return bool(regex.search(o))

    def __verify_neigh(ip, macs, dev, timeout, session=None, **dargs):
        refresh_neigh_table(dev, ip, session=session, timeout=timeout, **dargs)
        try:
            neigh_mac = get_neigh_mac(ip, session=session, timeout=timeout, **dargs)
            for mac in macs:
                if neigh_mac.lower() == mac.lower():
                    return True
        except VMIPV6NeighNotFoundError:
            pass
        return False

    ip_ver = netaddr.IPAddress(ip).version

    func = process.getoutput
    dargs = dict()
    if session:
        func = session.cmd_output
        dargs["safe"] = True
    else:
        dargs["ignore_bg_processes"] = True
    if not devs:
        # Get the name of the bridge device for ip route cache
        ip_cmd = utils_path.find_command("ip")
        if session:
            ip_cmd = func("which ip", timeout=timeout, **dargs).strip()
        ip_cmd = "%s route get %s; %s -%d route | grep default" % (
            ip_cmd, ip, ip_cmd, ip_ver)
        output = func(ip_cmd, timeout=timeout, **dargs)
        devs = set(re.findall(r"dev\s+(\S+)", output, re.I))
    if not devs:
        logging.debug("No path to %s in route table: %s" % (ip, output))
        return False

    # TODO: use same verification function for both ipv4 and ipv6
    verify_func = __verify_neigh if ip_ver == 6 else __arping
    for dev in devs:
        # VM might take some time to respond after migration
        return bool(utils_misc.wait_for(lambda: verify_func(ip, macs, dev,
                                                            timeout,
                                                            session=session, **dargs),
                                        timeout))


def generate_mac_address_simple():
    r = random.SystemRandom()
    mac = "9a:%02x:%02x:%02x:%02x:%02x" % (r.randint(0x00, 0xff),
                                           r.randint(0x00, 0xff),
                                           r.randint(0x00, 0xff),
                                           r.randint(0x00, 0xff),
                                           r.randint(0x00, 0xff))
    return mac


def gen_ipv4_addr(network_num="10.0.0.0", network_prefix="24", exclude_ips=[]):
    """
    generate ipv4 address
    :param network_num: network number to be used
    :param network_prefix: prefix used to get subnet mask to calculate ip range
    :param exclude_ips: the list of ipaddress should be excluded

    :return: ipaddress of type str
    """
    ip_regex = "^\d+.\d+.\d+.\d+$"
    exclude_ips = set(exclude_ips)
    if not re.match(ip_regex, network_num):
        network_num = "10.0.0.0"
    if not exclude_ips and network_prefix == "24":
        exclude_ips.add(network_num)
        exclude_ips.add('.'.join(network_num.split('.')[0:3]) + ".%s" %
                        str(1))
        exclude_ips.add(('.'.join(network_num.split('.')[0:3]) + ".%s" %
                         str(255)))
    network = netaddr.IPNetwork("%s/%s" % (network_num, network_prefix))
    for ip_address in network:
        if str(ip_address) not in exclude_ips:
            yield str(ip_address)


def get_ip_address_by_interface(ifname, ip_ver="ipv4", linklocal=False):
    """
    returns ip address by interface
    :param ifname: interface name
    :param ip_ver: Host IP version, ipv4 or ipv6.
    :param linklocal: Whether ip address is local or remote
    :raise NetError: When failed to fetch IP address (ioctl raised IOError.).
    """
    if ip_ver == "ipv6":
        ver = netifaces.AF_INET6
        linklocal_prefix = "fe80"
    else:
        ver = netifaces.AF_INET
        linklocal_prefix = "169.254"
    addr = netifaces.ifaddresses(ifname).get(ver)

    if addr is not None:
        try:
            if linklocal:
                return [a['addr'] for a in addr
                        if a['addr'].lower().startswith(linklocal_prefix)][0]
            else:
                return [a['addr'] for a in addr
                        if not a['addr'].lower().startswith(linklocal_prefix)][0]
        except IndexError:
            logging.warning("No IP address configured for "
                            "the network interface %s !", ifname)
            return None
    else:
        logging.warning("No IP address configured for the network interface"
                        "%s !", ifname)
        return None


def get_host_ip_address(params=None, ip_ver="ipv4", linklocal=False):
    """
    Returns ip address of host specified in host_ip_addr parameter if provided.
    Otherwise ip address on interface specified in netdst parameter is returned.
    In case of "nettype == user" "netdst" parameter is left empty, then the
    default interface of the system is used.

    :param params
    :param ip_ver: Host IP version, ipv4 or ipv6.
    :param linklocal: Whether ip address is local or remote
    :raise: TestFail when failed to fetch IP address
    """
    net_dev = ""
    if params:
        host_ip = params.get('host_ip_addr', None)
        if host_ip:
            logging.debug("Use IP address at config %s=%s", 'host_ip_addr', host_ip)
            return host_ip
        net_dev = params.get("netdst")
    if not net_dev:
        net_dev = get_default_gateway(iface_name=True)
    logging.warning("No IP address of host was provided, using IP address"
                    " on %s interface", net_dev)
    return get_ip_address_by_interface(net_dev, ip_ver, linklocal)


def get_all_ips():
    """
    Get all IPv4 and IPv6 addresses from all interfaces.
    """
    ips = []

    # Get all ipv4 IPs.
    for iface in get_host_iface():
        try:
            ip_addr = get_ip_address_by_interface(iface)
        except NetError:
            pass
        else:
            if ip_addr is not None:
                ip_info = {
                    'iface': iface,
                    'addr': ip_addr,
                    'version': 'ipv4',
                }
                ips.append(IPAddress(info=ip_info))

    # Get all ipv6 IPs.
    if_inet6_fp = open('/proc/net/if_inet6', 'r')
    for line in if_inet6_fp.readlines():
        # ipv6_ip, dev_no, len_prefix, scope, iface_flag, iface
        ipv6_ip, dev_no, _, _, _, iface = line.split()
        ipv6_ip = ":".join([ipv6_ip[i:i + 4] for i in range(0, 32, 4)])
        ip_info = {
            'iface': iface,
            'addr': ipv6_ip,
            'version': 'ipv6',
            'scope': int(dev_no, 16)
        }
        ips.append(IPAddress(info=ip_info))
    if_inet6_fp.close()

    return ips


def get_correspond_ip(remote_ip):
    """
    Get local ip address which is used to contact remote ip.

    :param remote_ip: Remote ip
    :return: Local corespond IP.
    """
    result = process.run("ip route get %s" % (remote_ip)).stdout_text
    local_ip = re.search("src (.+)", result)
    if local_ip is not None:
        local_ip = local_ip.groups()[0]
    return local_ip


def get_linux_mac(session, nic):
    """
    Get MAC address by nic name
    """
    sys_path = "%s/%s" % (SYSFS_NET_PATH, nic)
    pattern = "(\w{2}:\w{2}:\w{2}:\w{2}\:\w{2}:\w{2})"
    if session.cmd_status("test -d %s" % sys_path) == 0:
        mac_index = 1
        show_mac_cmd = "cat %s/address" % sys_path
        out = session.cmd_output(show_mac_cmd)
    else:
        pattern = "(ether|HWaddr) %s" % pattern
        mac_index = 2
        show_mac_cmd = "ifconfig %s || ip link show %s" % (nic, nic)
        out = session.cmd_output(show_mac_cmd)
    try:
        return str(re.search(pattern, out, re.M | re.I).group(mac_index))
    except Exception:
        logging.error("No HWaddr/ether found for nic %s: %s" % (nic, out))


def get_linux_ipaddr(session, nic):
    """
    Get IP addresses by nic name
    """
    rex = r"inet6?\s+(addr:)?\s*(\S+)\s+"
    cmd = "ifconfig %s || ip address show %s" % (nic, nic)
    out = session.cmd_output_safe(cmd)
    addrs = re.findall(rex, out, re.M)
    addrs = map(lambda x: x[1].split('/')[0], addrs)
    addrs = map(lambda x: netaddr.IPAddress(x), addrs)
    ipv4_addr = list(filter(lambda x: x.version == 4, addrs))
    ipv6_addr = list(filter(lambda x: x.version == 6, addrs))
    ipv4_addr = str(ipv4_addr[0]) if ipv4_addr else None
    ipv6_addr = str(ipv6_addr[0]) if ipv6_addr else None
    return (ipv4_addr, ipv6_addr)


def windows_mac_ip_maps(session):
    """
    Windows get MAC IP addresses maps
    """
    def str2ipaddr(str_ip):
        try:
            return netaddr.IPAddress(str_ip)
        except Exception:
            pass
        return None

    maps = {}
    cmd = "wmic nicconfig where IPEnabled=True get ipaddress, macaddress"
    out = session.cmd_output(cmd)
    regex = r".*\w{2}[:-]\w{2}[:-]\w{2}[:-]\w{2}[:-]\w{2}[:-]\w{2}\s*"
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    lines = [l for l in lines if re.match(regex, l)]
    for line in lines:
        line = re.sub(r"[\{\},\"]", "", line)
        addr_info = list(map(str, re.split(r"\s+", line)))
        mac = addr_info.pop().lower().replace("-", ":")
        addrs = filter(None, map(str2ipaddr, addr_info))
        ipv4_addr = list(filter(lambda x: x.version == 4, addrs))
        ipv6_addr = list(filter(lambda x: x.version == 6, addrs))
        if ipv4_addr:
            maps[mac] = str(ipv4_addr[0])
        if ipv6_addr:
            maps["%s_6" % mac] = str(ipv6_addr[0])
    return maps


def linux_mac_ip_maps(session):
    """
    Linux get MAC IP addresses maps
    """
    maps = {}
    for nic in get_linux_ifname(session):
        mac = get_linux_mac(session, nic)
        mac = mac.lower().replace("-", ":")
        ipv4_addr, ipv6_addr = get_linux_ipaddr(session, nic)
        if ipv4_addr:
            maps[mac] = ipv4_addr
        if ipv6_addr:
            maps["%s_6" % mac] = ipv6_addr
    return maps


def get_guest_address_map(session):
    """
    Get guest MAC IP addresses maps
    """
    os = session.cmd_output("echo %OS%")
    if "Win" in os:
        maps = windows_mac_ip_maps(session)
    else:
        maps = linux_mac_ip_maps(session)
    return maps


def get_linux_ifname(session, mac_address=""):
    """
    Get the interface name through the mac address.

    :param session: session to the virtual machine
    :param mac_address: the macaddress of nic

    :raise exceptions.TestError in case it was not possible to determine the
            interface name.
    """
    def _process_output(cmd, reg_pattern):
        sys_ifname = ["lo", "sit0", "virbr0"]
        try:
            output = session.cmd_output_safe(cmd)
            ifname_list = re.findall(reg_pattern, output, re.I)
            if not ifname_list:
                return None
            if mac_address:
                return ifname_list[0]
            for ifname in sys_ifname:
                if ifname in ifname_list:
                    ifname_list.remove(ifname)
            return ifname_list
        except aexpect.ShellCmdError:
            return None

    # Try ifconfig first
    i = _process_output("ifconfig -a", r"(\w+)\s+Link.*%s" % mac_address)
    if i is not None:
        return i

    # No luck, try ip link
    i = _process_output("ip link | grep -B1 '%s' -i" % mac_address,
                        r"\d+:\s+(\w+):\s+.*")
    if i is not None:
        return i

    # No luck, look on /sys
    cmd = r"grep '%s' /sys/class/net/*/address " % mac_address
    i = _process_output(cmd, r"net/(\w+)/address:%s" % mac_address)
    if i is not None:
        return i

    # If we came empty handed, let's raise an error
    raise exceptions.TestError("Failed to determine interface name with "
                               "mac %s" % mac_address)


def update_mac_ip_address(vm, timeout=240):
    """
    Get mac and ip address from guest then update the mac pool and
    address cache

    :param vm: VM object.
    :param timeout: Time (seconds) to keep trying to log in.
    """
    try:
        session = vm.wait_for_serial_login(timeout=timeout)
        addr_map = get_guest_address_map(session)
        session.close()
        if not addr_map:
            logging.warn("No VM's NIC got IP address")
            return
        vm.address_cache.update(addr_map)
    except Exception as e:
        logging.warn("Error occur when update VM address cache: %s", str(e))


def get_windows_nic_attribute(session, key, value, target, timeout=240,
                              global_switch="nic"):
    """
    Get the windows nic attribute using wmic. All the support key you can
    using wmic to have a check.

    :param session: session to the virtual machine
    :param key: the key supported by wmic
    :param value: the value of the key
    :param target: which nic attribute you want to get.

    """
    cmd = 'wmic %s where %s="%s" get %s' % (global_switch, key, value, target)
    status, out = session.cmd_status_output(cmd, timeout=timeout)
    if status != 0:
        err_msg = ("Execute guest shell command('%s') "
                   "failed with error: '%s'" % (cmd, out))
        raise exceptions.TestError(err_msg)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    # First line is header, return second line
    return lines[1]


def set_win_guest_nic_status(session, connection_id, status, timeout=240):
    """
    Set windows guest nic ENABLED/DISABLED

    :param  session : session to virtual machine
    :param  connection_id : windows guest nic netconnectionid
    :param  status : set nic ENABLED/DISABLED
    """
    cmd = 'netsh interface set interface name="%s" admin=%s'
    session.cmd(cmd % (connection_id, status), timeout=timeout)


def disable_windows_guest_network(session, connection_id, timeout=240):
    return set_win_guest_nic_status(session, connection_id,
                                    "DISABLED", timeout)


def enable_windows_guest_network(session, connection_id, timeout=240):
    return set_win_guest_nic_status(session, connection_id,
                                    "ENABLED", timeout)


def restart_windows_guest_network(session, connection_id, timeout=240,
                                  mode="netsh"):
    """
    Restart guest's network via serial console. mode "netsh" can not
    works in winxp system

    :param session: session to virtual machine
    :param connection_id: windows nic connectionid,it means connection name,
                          you Can get connection id string via wmic
    """
    if mode == "netsh":
        disable_windows_guest_network(session, connection_id, timeout=timeout)
        enable_windows_guest_network(session, connection_id, timeout=timeout)
    elif mode == "devcon":
        restart_windows_guest_network_by_devcon(session, connection_id)


def restart_windows_guest_network_by_key(session, key, value, timeout=240,
                                         mode="netsh"):
    """
    Restart the guest network by nic Attribute like connectionid,
    interfaceindex, "netsh" can not work in winxp system.
    using devcon mode must download devcon.exe and put it under c:\

    :param session: session to virtual machine
    :param key: the key supported by wmic nic
    :param value: the value of the key
    :param timeout: timeout
    :param mode: command mode netsh or devcon
    """
    if mode == "netsh":
        oper_key = "netconnectionid"
    elif mode == "devcon":
        oper_key = "pnpdeviceid"

    id = get_windows_nic_attribute(session, key, value, oper_key, timeout)
    if not id:
        raise exceptions.TestError("Get nic %s failed" % oper_key)
    if mode == "devcon":
        id = id.split("&")[-1]

    restart_windows_guest_network(session, id, timeout, mode)


def set_guest_network_status_by_devcon(session, status, netdevid,
                                       timeout=240):
    """
    using devcon to enable/disable the network device.
    using it must download the devcon.exe, and put it under c:\
    """
    set_cmd = r"c:\devcon.exe %s  =Net @PCI\*\*%s" % (status, netdevid)
    session.cmd(set_cmd, timeout=timeout)


def restart_windows_guest_network_by_devcon(session, netdevid, timeout=240):

    set_guest_network_status_by_devcon(session, 'disable', netdevid)
    set_guest_network_status_by_devcon(session, 'enable', netdevid)


def get_host_iface():
    """
    List the nic interface in host.
    :return: a list of the interfaces in host
    :rtype: builtin.list
    """
    proc_net_file = open(PROCFS_NET_PATH, 'r')
    host_iface_info = proc_net_file.read()
    proc_net_file.close()
    return [_.strip() for _ in re.findall("(.*):", host_iface_info)]


def get_default_gateway(iface_name=False, session=None):
    """
    Get the Default Gateway or Interface of host or guest.

    :param iface_name: Whether default interface (True), or default gateway
                       (False) is returned.
    :return: A string of the host's or guest's default gateway or interface.
    :rtype: string
    """
    if iface_name:
        cmd = "ip route | awk '/default/ { print $5 }'"
    else:
        cmd = "ip route | awk '/default/ { print $3 }'"
    try:
        if session:
            output = session.cmd_output(cmd).strip()
            logging.debug("Guest default gateway is %s" % output)
        else:
            output = process.run(cmd, shell=True).stdout_text.rstrip()
    except (aexpect.ShellError, aexpect.ShellTimeoutError, process.CmdError):
        logging.error("Failed to get the default GateWay")
        return None
    return output


def check_listening_port_by_service(service, port, listen_addr='0.0.0.0',
                                    runner=None):
    """
    Check TCP/IP listening by service
    """
    cmd = "netstat -tunlpW | grep -E '^tcp.*LISTEN.*%s.*'" % service
    find_netstat_cmd = "which netstat"
    output = ""
    find_str = listen_addr + ":" + port

    try:
        if not runner:
            try:
                utils_path.find_command("netstat")
            except utils_path.CmdNotFoundError as details:
                raise exceptions.TestSkipError(details)
            output = process.run(cmd, shell=True).stdout_text
        else:
            if not runner(find_netstat_cmd):
                raise exceptions.TestSkipError("Missing netstat command on "
                                               "remote")
            output = runner(cmd)
    except process.CmdError:
        logging.error("Failed to run command '%s'", cmd)

    if not re.search(find_str, output, re.M):
        raise exceptions.TestFail(
            "Failed to listen %s: %s" %
            (find_str, output))
    logging.info("The listening is active: %s", output)


def check_listening_port_remote_by_service(server_ip, server_user, server_pwd,
                                           service, port, listen_addr):
    """
    Check remote TCP/IP listening by service
    """
    # setup remote session
    session = None
    try:
        session = remote.wait_for_login('ssh', server_ip, '22', server_user,
                                        server_pwd, r"[\#\$]\s*$")
        runner = session.cmd_output
        check_listening_port_by_service(service, port, listen_addr, runner)
    except Exception:
        if session:
            session.close()


def block_specific_ip_by_time(ip_addr, block_time="1 seconds", runner=None):
    """
    Using iptables tool to block specific IP address with certain time

    :param ip_addr: specific host IP address
    :param block_time: blocking time, the format looks like 'N ${time}', and
                       N >=1, the ${time} is [hours|minutes|seconds],etc, the
                       default is '1 seconds'
    :param runner: command runner, it's a remote session
    """
    cmd = "iptables -A INPUT -s %s -m time --kerneltz --timestart \
           $(date +%%H:%%M:%%S) --timestop $(date --date='+%s' +%%H:%%M:%%S) \
           -j DROP" % (ip_addr, block_time)
    list_rules = "iptables -L"
    find_iptables = "which iptables"
    try:
        if not runner:
            try:
                utils_path.find_command("iptables")
            except utils_path.CmdNotFoundError as details:
                raise exceptions.TestSkipError(details)
            output = local_runner(cmd, shell=True)
            logging.debug("List current iptables rules:\n%s",
                          local_runner(list_rules))
        else:
            if not runner(find_iptables):
                raise exceptions.TestSkipError("Missing 'iptables' command on "
                                               "remote")
            output = runner(cmd)
            logging.debug("List current iptables rules:\n%s",
                          runner(list_rules))
    except process.CmdError:
        logging.error("Failed to run command '%s'", cmd)


def map_hostname_ipaddress(hostname_ip_dict, session=None):
    """
    Method to map ipaddress and hostname for resolving appropriately
    in /etc/hosts file.

    :param hostname_ip_dict: dict of Hostname and ipaddress to be mapped
    :param session: configure the /etc/hosts for remote host

    :return: True on successful mapping, False on failure
    """
    hosts_file = "/etc/hosts"
    check_cmd = "cat %s" % hosts_file
    func = process.getstatusoutput
    if session:
        func = session.cmd_status_output
    for hostname, ipaddress in six.iteritems(hostname_ip_dict):
        status, output = func(check_cmd)
        if status != 0:
            logging.error(output)
            return False
        pattern = "%s(\s+)%s$" % (ipaddress, hostname)
        if not re.search(pattern, output):
            cmd = "echo '%s %s' >> %s" % (ipaddress, hostname, hosts_file)
            status, output = func(cmd)
            if status != 0:
                logging.error(output)
                return False
    logging.info("All the hostnames and IPs are mapped in %s", hosts_file)
    return True


def _get_traceview_path(session, params):
    """
    Get the proper traceview.exe path.

    :param session: a session to send cmd
    :param params: the test params
    :return: the proper traceview path
    """

    traceview_path_template = params.get("traceview_path_template",
                                         "WIN_UTILS:\\traceview\\%s\\%%PROCESSOR_ARCHITECTURE%%\\traceview.exe")
    traceview_ver = "win10"
    os_version = system.version(session)
    main_ver = int(os_version.split('.')[0])
    if main_ver < 10:
        traceview_ver = "win8"
    traceview_path_template = traceview_path_template % traceview_ver
    return utils_misc.set_winutils_letter(session, traceview_path_template)


def _get_pdb_path(session, driver_name):
    """
    Get the proper [driver_name].pdb path from iso.

    :param session: a session to send cmd
    :param driver_name: the driver name
    :return: the proper pdb path
    """

    viowin_ltr = virtio_win.drive_letter_iso(session)
    if not viowin_ltr:
        err = "Could not find virtio-win drive in guest"
        raise exceptions.TestError(err)
    guest_name = virtio_win.product_dirname_iso(session)
    if not guest_name:
        err = "Could not get product dirname of the vm"
        raise exceptions.TestError(err)
    guest_arch = virtio_win.arch_dirname_iso(session)
    if not guest_arch:
        err = "Could not get architecture dirname of the vm"
        raise exceptions.TestError(err)

    pdb_middle_path = "%s\\%s" % (guest_name, guest_arch)
    pdb_find_cmd = 'dir /b /s %s\\%s.pdb | findstr "\\%s\\\\"'
    pdb_find_cmd %= (viowin_ltr, driver_name, pdb_middle_path)
    pdb_path = session.cmd(pdb_find_cmd).strip()
    logging.info("Found %s.pdb file at %s" % (driver_name, pdb_path))
    return pdb_path


def _prepare_traceview_windows(params, session, timeout=360):
    """
    Copy traceview.exe and corresponding pdb file to drive c: for future use.

    :param params: the test params
    :param session: a session to send command
    :param timeout: the command execute timeout
    :return: a tuple which consists of local traceview.exe and pdb file paths
    """

    copy_cmd = "xcopy %s %s /y"
    dst_folder = "c:\\"
    # copy traceview.exe
    logging.info("Copy traceview.exe to drive %s" % dst_folder)
    traceview_path = _get_traceview_path(session, params)
    session.cmd(copy_cmd % (traceview_path, dst_folder))

    # copy Netkvm.pdb
    driver_name = params.get("driver_name", "netkvm")
    logging.info("Locate %s.pdb and copy to drive %s" %
                 (driver_name, dst_folder))
    pdb_path = _get_pdb_path(session, driver_name)
    session.cmd(copy_cmd % (pdb_path, dst_folder))

    # return local file names
    pdb_local_path = "%s%s.pdb" % (dst_folder, driver_name)
    traceview_local_path = dst_folder + "traceview.exe"
    return (pdb_local_path, traceview_local_path)


def _get_msis_queues_from_traceview_output(output):
    """
    Extract MSIs&queues infomation from traceview log file output

    :param output: the content of traceview processed log infomation
    :return: a tuple of (msis, queues)
    """
    info_str = "Start checking dump content for MSIs&queues info"
    logging.info(info_str)
    search_exp = r'No MSIX, using (\d+) queue'
    # special case for vectors = 0
    queue_when_no_msi = re.search(search_exp, output)
    if queue_when_no_msi:
        return (0, int(queue_when_no_msi.group(1)))
    search_exp = r'(\d+) MSIs, (\d+) queues'
    search_res = re.search(search_exp, output)
    if not search_res:
        return (None, None)

    msis_number = int(search_res.group(1))
    queues_number = int(search_res.group(2))
    return (msis_number, queues_number)


def _wait_for_traceview_dump_finished(session, dump_file_path, timeout=100):
    """
    Check the dump file size periodically, untill the file size doesn't change,
    considered the dump process has finished. Then kill the idled progress.

    :param session: a session to send command
    :param dump_file_path: the dump file to check
    """
    last_size = [0]
    check_file_size_cmd = "for %%I in (%s) do @echo %%~zI" % dump_file_path

    def _check_file_size_unchanged():
        """
        Check whether dump file size is changed, by comparing current
        file size and last checked size. If unchanged, the dump process
        is considered finished.
        """
        status, output = session.cmd_status_output(check_file_size_cmd)
        if status or not output.isdigit():
            return False
        file_size = int(output)
        if file_size != last_size[0]:
            last_size[0] = file_size
            return False
        return True

    utils_misc.wait_for(lambda: _check_file_size_unchanged(),
                        timeout=timeout,
                        step=10.0)
    kill_cmd = "taskkill /im traceview.exe"
    session.cmd(kill_cmd)


def dump_traceview_log_windows(params, vm, timeout=360):
    """
    Dump traceview log file with nic restart panic
    Steps:
        1.Prepare traceview.exe & driver pdb files
        2.Start traceview session
        2.Restart network card to create panic
        3.Stop traceview session and dump log file

    :param params: test params
    :param vm: target vm
    :param timeout: timeout value for login
    :return: the content of traceview log file
    """
    log_path = "c:\\logfile.etl"
    clean_cmd = "del "
    dump_file = "c:\\trace.txt"

    session = vm.wait_for_login(timeout=timeout)
    # prepare traceview environment
    pdb_local_path, traceview_local_path = _prepare_traceview_windows(
        params, session, timeout)
    session.close()
    start_traceview_cmd = "%s -start test_session -pdb %s -level 5 -flag 0x1fff -f %s" % (
        traceview_local_path, pdb_local_path, log_path)
    stop_traceview_cmd = "%s -stop test_session" % traceview_local_path
    dump_cmd = "%s -process %s -pdb %s -o %s" % (
        traceview_local_path, log_path, pdb_local_path, dump_file)
    # start traceview
    logging.info("Start trace view with pdb file")
    session_serial = vm.wait_for_serial_login(timeout=timeout)
    try:
        session_serial.cmd(clean_cmd + log_path)
        session_serial.cmd(start_traceview_cmd, timeout=timeout)
        # restart nic
        logging.info("Restart guest nic")
        mac = vm.get_mac_address(0)
        connection_id = get_windows_nic_attribute(
            session_serial, "macaddress", mac, "netconnectionid")
        restart_windows_guest_network(session_serial, connection_id)
        # stop traceview
        logging.info("Stop traceview")
        session_serial.cmd(stop_traceview_cmd, timeout=timeout)
        # checkout traceview output
        logging.info("Check etl file generated by traceview")
        session_serial.cmd(clean_cmd + dump_file)
        status, output = session_serial.cmd_status_output(dump_cmd)
        if status:
            logging.error("Cann't dump log file %s: %s" % (log_path, output))
        _wait_for_traceview_dump_finished(session_serial, dump_file)
        status, output = session_serial.cmd_status_output(
            "type %s" % dump_file)
        if status:
            raise exceptions.TestError(
                "Cann't read dumped file %s: %s" % (dump_file, output))
        return output
    finally:
        session_serial.close()


def get_msis_and_queues_windows(params, vm, timeout=360):
    """
    Get MSIs&queues' infomation of current windows guest.
    First start a traceview session, then restart the nic interface
    to trigger logging. By analyzing the dumped output, the MSIs&queues
    info is acquired.

    :param params: the test params
    :param vm: target vm
    :param timeout: the timeout of login
    :return: a tuple of (msis, queues)
    """
    output = dump_traceview_log_windows(params, vm, timeout)
    return _get_msis_queues_from_traceview_output(output)


def set_netkvm_param_value(vm, param, value):
    """
    Set the value of certain 'param' in netkvm driver to 'value'
    This funcion will restart the first nic, so all the sessions
    opened before this function need close before this function is called.

    param vm: the target vm
    param param: the param
    param value: the value
    """

    session = vm.wait_for_serial_login(timeout=360)
    try:
        logging.info("Set %s to %s" % (param, value))
        cmd = 'netsh netkvm setparam 0 param=%s value=%s'
        cmd = cmd % (param, value)
        status, output = session.cmd_status_output(cmd)
        if status:
            err = "Error occured when set %s to value %s. " % (param, value)
            err += "With status=%s, output=%s" % (status, output)
            raise exceptions.TestError(err)

        logging.info("Restart nic to apply changes")
        dev_mac = vm.virtnet[0].mac
        connection_id = get_windows_nic_attribute(
            session, "macaddress", dev_mac, "netconnectionid")
        restart_windows_guest_network(session, connection_id)
        time.sleep(10)
    finally:
        session.close()


def get_netkvm_param_value(vm, param):
    """
    Get the value of certain 'param' in netkvm driver.

    param vm: the target vm
    param param: the param
    return: the value of the param
    """

    session = vm.wait_for_serial_login(timeout=360)
    try:
        logging.info("Get the value of %s" % param)
        cmd = 'netsh netkvm getparam 0 param=%s' % param
        status, output = session.cmd_status_output(cmd)
        if status:
            err = "Error occured when get value of %s. " % param
            err += "With status=%s, output=%s" % (status, output)
            raise exceptions.TestError(err)
        lines = output.strip().splitlines()
        value = lines[0].strip().split('=')[1].strip()
        return value
    finally:
        session.close()


def create_ovs_bridge(ovs_bridge_name, session=None, ignore_status=False):
    """
    Create ovs bridge via tmux command on local or remote

    :param ovs_bridge_name: The ovs bridge
    :param session: The remote session
    :param ignore_status: Whether to raise an exception when command fails
    :return: The command status and output
    """
    runner = local_runner
    if session:
        runner = session.cmd
    iface_name = get_net_if(runner=runner, state="UP")[0]
    if not utils_package.package_install("tmux", session):
        raise exceptions.TestError("Failed to install the tmux packages.")

    res = utils_misc.cmd_status_output("which ovs-vsctl", shell=True,
                                       ignore_status=False, session=session)[0]
    if res == 1:
        raise exceptions.TestError("ovs-vsctl: command not found, please make "
                                   "sure the openvswitch or openvswitch2 pkg "
                                   "is installed.")
    cmd = "ovs-vsctl add-br {0};ovs-vsctl add-port {0} {1};dhclient -r;"\
          "sleep 5 ;dhclient {0}".format(ovs_bridge_name, iface_name)
    tmux_cmd = 'tmux -c "{}"'.format(cmd)
    return utils_misc.cmd_status_output(tmux_cmd, shell=True, verbose=True,
                                        ignore_status=ignore_status,
                                        session=session)


def delete_ovs_bridge(ovs_bridge_name, session=None, ignore_status=False):
    """
    Delete ovs bridge via tmux command on local or remote

    :param ovs_bridge_name: The ovs bridge
    :param session: The remote session
    :param ignore_status: Whether to raise an exception when command fails
    :return: The command status and output
    """
    runner = local_runner
    if session:
        runner = session.cmd
    iface_name = get_net_if(runner=runner, state="UP")[0]
    if not utils_package.package_install("tmux", session):
        raise exceptions.TestError("Failed to install the tmux packages.")

    res = utils_misc.cmd_status_output("which ovs-vsctl", shell=True,
                                       ignore_status=False, session=session)[0]
    if res == 1:
        raise exceptions.TestError("ovs-vsctl: command not found, please make "
                                   "sure the openvswitch or openvswitch2 pkg "
                                   "is installed.")
    cmd = "ovs-vsctl del-port {0} {1};ovs-vsctl del-br {0};dhclient -r;"\
          "sleep 5 ;dhclient {1}".format(ovs_bridge_name, iface_name)
    tmux_cmd = 'tmux -c "{}"'.format(cmd)
    return utils_misc.cmd_status_output(tmux_cmd, shell=True, verbose=True,
                                        ignore_status=ignore_status,
                                        session=session)
