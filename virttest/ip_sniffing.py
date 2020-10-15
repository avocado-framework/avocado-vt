"""
IP sniffing facilities
"""

import threading
import logging
import re
from collections import Iterable

import aexpect
from aexpect.remote import handle_prompts
from avocado.utils import path as utils_path

import six

from virttest.utils_misc import log_line


class AddrCache(object):

    """
    Address cache implementation.
    """

    def __init__(self):
        """Initializes the address cache."""
        self._data = {}
        self._lock = threading.RLock()

    def __repr__(self):
        return repr(self._data)

    def __getstate__(self):
        state = self.__dict__.copy()
        del state["_lock"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._lock = threading.RLock()

    @staticmethod
    def _format_hwaddr(hwaddr):
        return hwaddr.lower()

    def __setitem__(self, hwaddr, ipaddr):
        hwaddr = self._format_hwaddr(hwaddr)
        with self._lock:
            if self._data.get(hwaddr) == ipaddr:
                return
            self._data[hwaddr] = ipaddr
        logging.debug("Updated HWADDR (%s)<->(%s) IP pair "
                      "into address cache", hwaddr, ipaddr)

    def __getitem__(self, hwaddr):
        hwaddr = self._format_hwaddr(hwaddr)
        ipaddr = None
        with self._lock:
            ipaddr = self._data.get(hwaddr)
        return ipaddr

    def __delitem__(self, hwaddr):
        hwaddr = self._format_hwaddr(hwaddr)
        with self._lock:
            if hwaddr not in self._data:
                return
            del self._data[hwaddr]
        logging.debug("Dropped the address cache of HWADDR (%s)", hwaddr)

    def get(self, hwaddr):
        """
        Get the ip address of the given hardware address.

        :param hwaddr: Hardware address.
        """
        return self.__getitem__(hwaddr)

    def drop(self, hwaddr):
        """
        Drop the cache of the given hardware address.

        :param hwaddr: Hardware address.
        """
        return self.__delitem__(hwaddr)

    def update(self, cache):
        """
        Update the address cache with the address pairs from other,
        overwriting existing hardware address.

        :param cache: AddrCache object, dict object or iterable
                      key/value pairs.
        """
        if self == cache:
            return
        if isinstance(cache, AddrCache):
            _cache = cache
            with _cache._lock:
                cache = _cache._data.copy()
        if isinstance(cache, Iterable):
            cache = six.iteritems(cache)
        for hwaddr, ipaddr in cache:
            self[hwaddr] = ipaddr

    def clear(self):
        """Clear all the address caches."""
        with self._lock:
            self._data.clear()
        logging.debug("Clean out all the address caches")


class Sniffer(object):

    """
    Virtual base class of the ip sniffer abstraction.

    The `_output_handler(self, line)` method must be
    provided by the subclasses.
    """

    #: Sniffer's command name
    command = ""
    #: Sniffer's options
    options = ""
    # Regexp to find "process terminated" line in sniffer output
    _re_sniffer_finished = re.compile(r"\(Process terminated with status (\d+)")

    def __init__(self, addr_cache, log_file, remote_opts=None):
        """
        Initializes the sniffer.

        :param addr_cache: Address cache to be updated.
        :param log_file: Log file name.
        :param remote_opts: Options of remote host session, is a tuple built
                            up by `(address, port, username, password,
                            prompt)`. If provided, launches the sniffer on
                            remote host, otherwise on local host.
        """
        self._cache = addr_cache
        self._logfile = log_file
        self._remote_opts = remote_opts
        self._process = None

    @classmethod
    def _is_supported_remote(cls, session):
        return session.cmd_status("which %s" % cls.command) == 0

    @classmethod
    def is_supported(cls, session=None):
        """
        Check if host supports the sniffer.

        :param session: Remote host session. If provided, performs the
                        check on remote host, otherwise on local host.
        """
        if session:
            return cls._is_supported_remote(session)
        try:
            utils_path.find_command(cls.command)
            return True
        except utils_path.CmdNotFoundError:
            return False

    def _output_handler(self, line):
        raise NotImplementedError

    def _output_logger_handler(self, line):
        try:
            log_line(self._logfile, line)
        except Exception as e:
            logging.warn("Can't log ip sniffer output: '%s'", e)
        if self._output_handler(line):
            return
        # We can check whether the process is terminated unexpectedly
        # here since the terminated status is a line of the output
        match = self._re_sniffer_finished.match(line)
        if match:
            if match.group(1) != "0":
                logging.error("IP sniffer (%s) terminated unexpectedly! "
                              "please check the log to get the details "
                              "(status: %s)", self.command, match.group(1))

    def _start_remote(self):
        address, port, username, password, prompt = self._remote_opts
        cmd = "%s %s" % (self.command, self.options)
        logging.debug("Run '%s' on host '%s'", cmd, address)
        login_cmd = ("ssh -o UserKnownHostsFile=/dev/null "
                     "-o StrictHostKeyChecking=no "
                     "-o PreferredAuthentications=password -p %s %s@%s" %
                     (port, username, address))

        self._process = aexpect.ShellSession(
            login_cmd,
            output_func=self._output_logger_handler)
        handle_prompts(self._process, username, password, prompt)
        self._process.sendline(cmd)

    def _start(self):
        cmd = "%s %s" % (self.command, self.options)
        if self._remote_opts:
            self._start_remote()
        else:
            self._process = aexpect.run_tail(
                command=cmd,
                output_func=self._output_logger_handler)

    def is_alive(self):
        """Check if the sniffer is alive."""
        if not self._process:
            return False
        return self._process.is_alive()

    def start(self):
        """Start sniffing."""
        if self.is_alive():
            return
        self.stop()
        self._start()

    def stop(self):
        """Stop sniffing."""
        if self._process:
            self._process.close()
            self._process = None

    def __del__(self):
        self.stop()


class TcpdumpSniffer(Sniffer):

    """
    Tcpdump sniffer class.
    """

    command = "tcpdump"
    options = "-tnpvvvi any 'port 68 or port 546'"

    def __init__(self, addr_cache, log_file, remote_opts=None):
        super(TcpdumpSniffer, self).__init__(addr_cache, log_file, remote_opts)
        self._context = {}

    def _output_handler(self, line):
        # BootP/DHCP (RFC 951/2131)
        matches = re.search(r"^IP\s", line)
        if matches:
            # Clear context upon receiving new packets
            self._context.clear()
            return True

        matches = re.search(r"Your.IP\s+(\S+)", line, re.I)
        if matches:
            self._context["ip"] = matches.group(1)
            return True

        matches = re.search(r"Client.Ethernet.Address\s+(\S+)", line, re.I)
        if matches:
            self._context["mac"] = matches.group(1)
            return True

        if re.search(r"DHCP.Message.*:\s+ACK", line, re.I):
            mac = self._context.get("mac")
            ip = self._context.get("ip")
            if mac and ip:
                self._cache[mac] = ip
            return True

        # DHCPv6 (RFC 3315)
        if re.search("dhcp6 reply", line, re.I):
            regex = "IA_ADDR (.*) pltime.*client-ID.*?([0-9a-fA-F]{12})\)"
            matches = re.search(regex, line, re.I)
            if matches:
                info = matches.groups()
                mac = ":".join(re.findall("..", info[1]))
                ip = info[0].lower()
                self._cache["%s_6" % mac] = ip
            return True


class TSharkSniffer(Sniffer):

    """
    TShark sniffer class.
    """

    command = "tshark"
    options = ("-npi any -T fields -E separator=/s -E occurrence=f "
               "-E header=y -e ip.src -e ip.dst -e bootp.type -e bootp.id "
               "-e bootp.hw.mac_addr -e bootp.ip.your -e bootp.option.dhcp "
               "-e ipv6.src -e ipv6.dst "
               # Positional arguments must be the last arguments
               "'port 68 or port 546'")

    def _output_handler(self, line):
        packet = line.lstrip().split()
        if not len(packet):
            return True

        # BootP/DHCP (RFC 951/2131)
        if re.match(r"\d+\.\d+\.\d+\.\d+", packet[0]):
            try:
                chaddr = packet[4]
                yiaddr = packet[5]
                m_type = packet[6]
            except IndexError:
                # Ignore problematical packets
                return True
            if m_type == "5" and yiaddr != "0.0.0.0":
                # Update cache only if get the ACK reply
                # and the previous request is not INFORM
                self._cache[chaddr] = yiaddr
            return True

        # DHCPv6 (RFC 3315)
        if re.match(r"[0-9a-fA-F]{1,4}:\S+", packet[0]):
            # TODO: support DHCPv6
            if not self.__dict__.setdefault("_ip6_warned", False):
                logging.warn("IPv6 address sniffing is not supported yet by "
                             "using TShark, please fallback to use other "
                             "sniffers by uninstalling TShark when testing "
                             "with IPv6")
                self._ip6_warned = True
            return True


#: All the defined sniffers
Sniffers = (TSharkSniffer, TcpdumpSniffer)
