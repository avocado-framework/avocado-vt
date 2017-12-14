import cPickle
import UserDict
import os
import logging
import re
import threading
import time

import aexpect
from avocado.core import exceptions
from avocado.utils import path as utils_path

import utils_misc
import virt_vm
import remote

ENV_VERSION = 1


def get_env_version():
    return ENV_VERSION


class EnvSaveError(Exception):
    pass


def lock_safe(function):
    """
    Get the environment safe lock, run the function, then release the lock.

    Unfortunately, it only works if the 1st argument of the function is an
    Env instance. This is mostly to save up code.

    :param function: Function to wrap.
    """
    def wrapper(*args, **kwargs):
        env = args[0]
        env.save_lock.acquire()
        try:
            return function(*args, **kwargs)
        finally:
            env.save_lock.release()
    wrapper.__name__ = function.__name__
    wrapper.__doc__ = function.__doc__
    wrapper.__dict__.update(function.__dict__)
    return wrapper


def _update_addr_cache(cache, mac, ip):
    """Update mac <-> ip relationship"""
    if cache.get(mac) != ip:
        cache[mac] = ip
        logging.debug("Update MAC (%s)<->(%s) IP pair "
                      "into address cache", mac, ip)


@lock_safe
def _output_handler_tcpdump(env, line):
    """Output handler of Tcpdump"""
    address_cache = env["address_cache"]
    matches = re.search(r"Your.IP\s+(\S+)", line, re.I)
    if matches:
        ip = matches.group(1)
        if ip != address_cache.get("last_seen_ip"):
            address_cache["last_seen_ip"] = ip
        return

    matches = re.search(r"Client.Ethernet.Address\s+(\S+)", line, re.I)
    if matches:
        mac = matches.group(1).lower()
        if mac != address_cache.get("last_seen_mac"):
            address_cache["last_seen_mac"] = mac
        return

    if re.search(r"DHCP.Message.*:\s+ACK", line, re.I):
        if (address_cache.get('last_seen_mac') and
                address_cache.get('last_seen_ip')):
            mac = address_cache['last_seen_mac']
            ip = address_cache['last_seen_ip']
            _update_addr_cache(address_cache, mac, ip)
            address_cache["last_seen_mac"] = None
            address_cache["last_seen_ip"] = None
        return

    # ipv6 address cache:
    mac_ipv6_reg = r"client-ID.*?([0-9a-fA-F]{12})\).*IA_ADDR (.*) pltime"
    if re.search("dhcp6 (request|renew|confirm)", line, re.IGNORECASE):
        matches = re.search(mac_ipv6_reg, line, re.I)
        if matches:
            ipinfo = matches.groups()
            mac_address = ":".join(re.findall("..", ipinfo[0])).lower()
            request_ip = ipinfo[1].lower()
            mac = "%s_6" % mac_address
            _update_addr_cache(address_cache, mac, request_ip)
        return

    if re.search("dhcp6 (reply|advertise)", line, re.IGNORECASE):
        ipv6_mac_reg = "IA_ADDR (.*) pltime.*client-ID.*?([0-9a-fA-F]{12})\)"
        matches = re.search(ipv6_mac_reg, line, re.I)
        if matches:
            ipinfo = matches.groups()
            mac_address = ":".join(re.findall("..", ipinfo[1])).lower()
            allocate_ip = ipinfo[0].lower()
            mac = "%s_6" % mac_address
            _update_addr_cache(address_cache, mac, allocate_ip)
        return


@lock_safe
def _output_handler_tshark(env, line):
    """Output handler of TShark"""
    cache = env["address_cache"]

    packet = line.split()
    if not len(packet):
        return

    # BootP/DHCP (RFC 951/RFC 2131)
    if re.match(r"\d+\.\d+\.\d+\.\d+", packet[0]):
        chaddr = packet[5]
        yiaddr = packet[6]
        m_type = packet[7]
        if m_type == "5" and yiaddr != "0.0.0.0":
            # Update cache only if get the ACK reply
            # and the previous request is not INFORM
            _update_addr_cache(cache, chaddr, yiaddr)
        return

    # DHCPv6 (RFC 3315)
    # TODO: support DHCPv6
    pass


def _sniffer_handler_helper(s_hdlr, filename):
    """Helper for handling ip sniffer output."""
    def hdlr_f(env, line):
        try:
            utils_misc.log_line(filename, line)
        except Exception, reason:
            logging.warn("Can't log ip sniffer output, '%s'", reason)
        s_hdlr(env, line)
    return hdlr_f


class Env(UserDict.IterableUserDict):

    """
    A dict-like object containing global objects used by tests.
    """

    def __init__(self, filename=None, version=0):
        """
        Create an empty Env object or load an existing one from a file.

        If the version recorded in the file is lower than version, or if some
        error occurs during unpickling, or if filename is not supplied,
        create an empty Env object.

        :param filename: Path to an env file.
        :param version: Required env version (int).
        """
        UserDict.IterableUserDict.__init__(self)
        empty = {"version": version}
        self._filename = filename
        self._sniffer = None
        self._params = None
        self.save_lock = threading.RLock()
        if filename:
            try:
                if os.path.isfile(filename):
                    f = open(filename, "r")
                    env = cPickle.load(f)
                    f.close()
                    if env.get("version", 0) >= version:
                        self.data = env
                    else:
                        logging.warn(
                            "Incompatible env file found. Not using it.")
                        self.data = empty
                else:
                    # No previous env file found, proceed...
                    logging.warn("Creating new, empty env file")
                    self.data = empty
            # Almost any exception can be raised during unpickling, so let's
            # catch them all
            except Exception, e:
                logging.warn("Exception thrown while loading env")
                logging.warn(e)
                logging.warn("Creating new, empty env file")
                self.data = empty
        else:
            logging.warn("Creating new, empty env file")
            self.data = empty

    def save(self, filename=None):
        """
        Pickle the contents of the Env object into a file.

        :param filename: Filename to pickle the dict into.  If not supplied,
                use the filename from which the dict was loaded.
        """
        filename = filename or self._filename
        if filename is None:
            raise EnvSaveError("No filename specified for this env file")
        self.save_lock.acquire()
        try:
            f = open(filename, "w")
            cPickle.dump(self.data, f)
            f.close()
        finally:
            self.save_lock.release()

    def get_all_vms(self):
        """
        Return a list of all VM objects in this Env object.
        """
        vm_list = []
        for key in self.data.keys():
            if key and key.startswith("vm__"):
                vm_list.append(self.data[key])
        return vm_list

    def clean_objects(self):
        """
        Destroy all objects registered in this Env object.
        """
        self.stop_ip_sniffer()
        for key in self.data:
            try:
                if key.startswith("vm__"):
                    self.data[key].destroy(gracefully=False)
            except Exception:
                pass
        self.data = {}

    def destroy(self):
        """
        Destroy all objects stored in Env and remove the backing file.
        """
        self.clean_objects()
        if self._filename is not None:
            if os.path.isfile(self._filename):
                os.unlink(self._filename)

    def get_vm(self, name):
        """
        Return a VM object by its name.

        :param name: VM name.
        """
        return self.data.get("vm__%s" % name)

    def create_vm(self, vm_type, target, name, params, bindir):
        """
        Create and register a VM in this Env object
        """
        vm_class = virt_vm.BaseVM.lookup_vm_class(vm_type, target)
        if vm_class is not None:
            vm = vm_class(name, params, bindir, self.get("address_cache"))
            self.register_vm(name, vm)
            return vm

    @lock_safe
    def register_vm(self, name, vm):
        """
        Register a VM in this Env object.

        :param name: VM name.
        :param vm: VM object.
        """
        self.data["vm__%s" % name] = vm

    @lock_safe
    def unregister_vm(self, name):
        """
        Remove a given VM.

        :param name: VM name.
        """
        del self.data["vm__%s" % name]

    @lock_safe
    def register_syncserver(self, port, server):
        """
        Register a Sync Server in this Env object.

        :param port: Sync Server port.
        :param server: Sync Server object.
        """
        self.data["sync__%s" % port] = server

    @lock_safe
    def unregister_syncserver(self, port):
        """
        Remove a given Sync Server.

        :param port: Sync Server port.
        """
        del self.data["sync__%s" % port]

    def get_syncserver(self, port):
        """
        Return a Sync Server object by its port.

        :param port: Sync Server port.
        """
        return self.data.get("sync__%s" % port)

    @lock_safe
    def register_lvmdev(self, name, lvmdev):
        """
        Register lvm device object into env;

        :param name: name of register lvmdev object
        :param lvmdev: lvmdev object;
        """
        self.data["lvmdev__%s" % name] = lvmdev

    @lock_safe
    def unregister_lvmdev(self, name):
        """
        Remove lvm device object from env;

        :param name: name of lvm device object;
        """
        del self.data["lvmdev__%s" % name]

    def get_lvmdev(self, name):
        """
        Get lvm device object by name from env;

        :param name: lvm device object name;
        :return: lvmdev object
        """
        return self.data.get("lvmdev__%s" % name)

    def _start_sniffer(self):
        ip_s = [("tshark",
                 "%s -npVi any 'port 68 or port 546' -T fields -E header=y "
                 "-E separator=/s -E occurrence=f -e ip.src -e ip.dst "
                 "-e bootp.type -e bootp.id -e bootp.ip.client "
                 "-e bootp.hw.mac_addr -e bootp.ip.your -e bootp.option.dhcp",
                 _output_handler_tshark),
                ("tcpdump",
                 "%s -npvvvi any 'port 68 or port 546'",
                 _output_handler_tcpdump)]

        remote_pp = self._params.get("remote_preprocess") == "yes"
        s_cmd = None
        s_hdlr = None

        if remote_pp:
            client = self._params.get('remote_shell_client', 'ssh')
            port = self._params.get('remote_shell_port', '22')
            prompt = self._params.get('remote_shell_prompt', '#')
            address = self._params.get('remote_node_address')
            username = self._params.get('remote_node_user')
            password = self._params.get('remote_node_password')
            rsession = remote.remote_login(client, address,
                                           port, username,
                                           password, prompt)

            for cmd_n, cmd_t, s_hdlr in ip_s:
                st, cmd_b = rsession.cmd_status_output("which %s" % cmd_n)
                if st == 0:
                    s_cmd = cmd_t % cmd_b.strip()
                    break
            rsession.close()
        else:
            for cmd_n, cmd_t, s_hdlr in ip_s:
                try:
                    s_cmd = cmd_t % utils_path.find_command(cmd_n)
                    if s_cmd:
                        break
                except utils_path.CmdNotFoundError:
                    pass
        if not s_cmd:
            raise exceptions.TestError("Can't find any valid ip sniffer "
                                       "binary! %s" % [sn[0] for sn in ip_s])

        if remote_pp:
            logging.debug("Run '%s' on host '%s'", s_cmd, address)
            login_cmd = ("ssh -o UserKnownHostsFile=/dev/null "
                         "-o StrictHostKeyChecking=no "
                         "-o PreferredAuthentications=password -p %s %s@%s" %
                         (port, username, address))

            self._sniffer = aexpect.ShellSession(login_cmd,
                                                 output_func=s_hdlr,
                                                 output_params=(self,))

            remote.handle_prompts(self._sniffer, username, password, prompt)
            self._sniffer.sendline(s_cmd)
        else:
            s_hdlr = _sniffer_handler_helper(s_hdlr, "ipsniffer.log")
            self._sniffer = aexpect.Tail(command=s_cmd,
                                         output_func=s_hdlr,
                                         output_params=(self,))

        # Check if sniffer was terminated immediately
        time.sleep(1)
        if not self._sniffer.is_alive():
            logging.warn("Could not start ip sniffer")
            logging.warn("Status: %s", self._sniffer.get_status())
            msg = utils_misc.format_str_for_message(self._sniffer.get_output())
            logging.warn("Output: %s", msg)

    def start_ip_sniffer(self, params):
        self._params = params

        if "address_cache" not in self.data:
            self.data["address_cache"] = {}

        if self._sniffer is None:
            self._start_sniffer()
        else:
            if not self._sniffer.is_alive():
                del self._sniffer
                self._start_sniffer()

    def stop_ip_sniffer(self):
        if self._sniffer is not None:
            self._sniffer.close()
            del self._sniffer
            self._sniffer = None
