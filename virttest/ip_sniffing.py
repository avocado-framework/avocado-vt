"""
IP sniffing facilities
"""

import threading
import logging
import re

import aexpect
from avocado.utils import path as utils_path

from remote import handle_prompts
from utils_misc import log_line
from utils_misc import format_str_for_message


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
        if hasattr(cache, "iteritems"):
            cache = cache.iteritems()
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
        self._output_handler(line)

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

        if not self._process.is_alive():
            logging.warn("Could not start ip sniffer (%s)", self.command)
            logging.warn("Status: %s", self._process.get_status())
            msg = format_str_for_message(self._process.get_output())
            logging.warn("Output: %s", msg)

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
            # Clear context upon receiving a new packet
            self._context.clear()
            return

        matches = re.search(r"Your.IP\s+(\S+)", line, re.I)
        if matches:
            self._context["ip"] = matches.group(1)
            return

        matches = re.search(r"Client.Ethernet.Address\s+(\S+)", line, re.I)
        if matches:
            self._context["mac"] = matches.group(1)
            return

        if re.search(r"DHCP.Message.*:\s+ACK", line, re.I):
            mac = self._context.get("mac")
            ip = self._context.get("ip")
            if mac and ip:
                self._cache[mac] = ip
            return

        # DHCPv6 (RFC 3315)
        if re.search("dhcp6 reply", line, re.I):
            regex = "IA_ADDR (.*) pltime.*client-ID.*?([0-9a-fA-F]{12})\)"
            matches = re.search(regex, line, re.I)
            if matches:
                info = matches.groups()
                mac = ":".join(re.findall("..", info[1]))
                ip = info[0].lower()
                self._cache["%s_6" % mac] = ip
            return


class TSharkSniffer(Sniffer):

    """
    TShark sniffer class.
    """

    command = "tshark"
    options = ("-npi any 'port 68 or port 546' -T fields -E header=y "
               "-E separator=/s -E occurrence=f -e ip.src -e ip.dst "
               "-e bootp.type -e bootp.id -e bootp.hw.mac_addr "
               "-e bootp.ip.your -e bootp.option.dhcp")

    def _output_handler(self, line):
        packet = line.split()
        if not len(packet):
            return

        # BootP/DHCP (RFC 951/2131)
        if re.match(r"\d+\.\d+\.\d+\.\d+", packet[0]):
            chaddr = packet[4]
            yiaddr = packet[5]
            m_type = packet[6]
            if m_type == "5" and yiaddr != "0.0.0.0":
                # Update cache only if get the ACK reply
                # and the previous request is not INFORM
                self._cache[chaddr] = yiaddr
            return

        # DHCPv6 (RFC 3315)
        # TODO: support DHCPv6
        pass


#: All the defined sniffers
Sniffers = (TSharkSniffer, TcpdumpSniffer)
