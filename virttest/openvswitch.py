import logging
import re
import os
import signal

from avocado.utils import path
from avocado.utils import process
from avocado.utils import linux_modules

from .versionable_class import VersionableClass, Manager, factory
from . import utils_misc


# Register to class manager.
man = Manager(__name__)


class ServiceManagerInterface(object):

    def __new__(cls, *args, **kargs):
        ServiceManagerInterface.master_class = ServiceManagerInterface
        return super(ServiceManagerInterface, cls).__new__(cls, *args, **kargs)

    @classmethod
    def get_version(cls):
        """
        Get version of ServiceManager.
        :return: Version of ServiceManager.
        """
        return open("/proc/1/comm", "r").read().strip()

    def stop(self, service_name):
        raise NotImplementedError("Method 'stop' must be"
                                  " implemented in child class")

    def start(self, service_name):
        raise NotImplementedError("Method 'start' must be"
                                  " implemented in child class")

    def restart(self, service_name):
        raise NotImplementedError("Method 'restart' must be"
                                  " implemented in child class")

    def status(self, service_name):
        raise NotImplementedError("Method 'status' must be"
                                  " implemented in child class")


class ServiceManagerSysvinit(ServiceManagerInterface):

    @classmethod
    def _is_right_ver(cls):
        version = cls.get_version()
        if version == "init":
            return True
        return False

    def stop(self, service_name):
        process.run("/etc/init.d/%s stop" % (service_name))

    def start(self, service_name):
        process.run("/etc/init.d/%s start" % (service_name))

    def restart(self, service_name):
        process.run("/etc/init.d/%s restart" % (service_name))


class ServiceManagerSystemD(ServiceManagerSysvinit):

    @classmethod
    def _is_right_ver(cls):
        version = cls.get_version()
        if version == "systemd":
            return True
        return False

    def stop(self, service_name):
        process.run("systemctl stop %s.service" % (service_name))

    def start(self, service_name):
        process.run("systemctl start %s.service" % (service_name))

    def restart(self, service_name):
        process.run("systemctl restart %s.service" % (service_name))

    def status(self, service_name):
        process.run("systemctl show %s.service" % (service_name))


class ServiceManager(VersionableClass):
    __master__ = ServiceManagerSystemD


class OpenVSwitchControl(object):

    """
    Class select the best matches control class for installed version
    of OpenVSwitch.

    OpenVSwtich parameters are described in man ovs-vswitchd.conf.db
    """
    def __new__(cls, db_path=None, db_socket=None, db_pidfile=None,
                ovs_pidfile=None, dbschema=None, install_prefix=None):
        """
        Makes initialization of OpenVSwitch.

        :param tmpdir: Tmp directory for save openvswitch test files.
        :param db_path: Path of OVS databimpoty ase.
        :param db_socket: Path of OVS db socket.
        :param db_pidfile: Path of OVS db ovsdb-server pid.
        :param ovs_pidfile: Path of OVS ovs-vswitchd pid.
        :param install_prefix: Path where is openvswitch installed.
        """
        # if path is None set default path.
        if not install_prefix:
            install_prefix = "/"
        if not db_path:
            db_path = os.path.join(install_prefix,
                                   "/etc/openvswitch/conf.db")
        if not db_socket:
            db_socket = os.path.join(install_prefix,
                                     "/var/run/openvswitch/db.sock")
        if not db_pidfile:
            db_pidfile = os.path.join(install_prefix,
                                      "/var/run/openvswitch/ovsdb-server.pid")
        if not ovs_pidfile:
            ovs_pidfile = os.path.join(install_prefix,
                                       "/var/run/openvswitch/ovs-vswitchd.pid")
        if not dbschema:
            dbschema = os.path.join(install_prefix,
                                    "/usr/share/openvswitch/vswitch.ovsschema")

        OpenVSwitchControl.install_prefix = install_prefix

        OpenVSwitchControl.db_path = db_path
        OpenVSwitchControl.db_socket = db_socket
        OpenVSwitchControl.db_pidfile = db_pidfile
        OpenVSwitchControl.ovs_pidfile = ovs_pidfile

        OpenVSwitchControl.dbschema = install_prefix, dbschema
        os.environ["PATH"] = (os.path.join(install_prefix, "usr/bin:") +
                              os.environ["PATH"])
        os.environ["PATH"] = (os.path.join(install_prefix, "usr/sbin:") +
                              os.environ["PATH"])

        return super(OpenVSwitchControl, cls).__new__(cls)

    @staticmethod
    def convert_version_to_int(version):
        """
        :param version: (int) Converted from version string 1.4.0 => int 140
        """
        if isinstance(version, int):
            return version
        try:
            a = re.findall('^(\d+)\.?(\d+)\.?(\d+)\-?', version)[0]
            int_ver = ''.join(a)
        except Exception:
            raise ValueError("Wrong version format '%s'" % version)
        return int(int_ver)

    @classmethod
    def get_version(cls):
        """
        Get version of installed OpenVSwtich.

        :return: Version of OpenVSwtich.
        """
        version = None
        try:
            result = process.run("%s --version" %
                                 path.find_command("ovs-vswitchd"))
            pattern = "ovs-vswitchd \(Open vSwitch\) (\d+\.\d+\.\d+).*"
            version = re.search(pattern,
                                result.stdout_text).group(1)
        except process.CmdError:
            logging.debug("OpenVSwitch is not available in system.")
        return version

    def status(self):
        raise NotImplementedError()

    def add_br(self, br_name):
        raise NotImplementedError()

    def del_br(self, br_name):
        raise NotImplementedError()

    def br_exist(self, br_name):
        raise NotImplementedError()

    def list_br(self):
        raise NotImplementedError()

    def add_port(self, br_name, port_name):
        raise NotImplementedError()

    def del_port(self, br_name, port_name):
        raise NotImplementedError()

    def add_port_tag(self, port_name, tag):
        raise NotImplementedError()

    def add_port_trunk(self, port_name, trunk):
        raise NotImplementedError()

    def set_vlanmode(self, port_name, vlan_mode):
        raise NotImplementedError()

    def check_port_in_br(self, br_name, port_name):
        raise NotImplementedError()


class OpenVSwitchControlDB_140(OpenVSwitchControl):

    """
    Don't use this class directly. This class is automatically selected by
    OpenVSwitchControl.
    """
    @classmethod
    def _is_right_ver(cls):
        """
        Check condition for select control class.

        :param version: version of OpenVSwtich
        """
        version = cls.get_version()
        if version is not None:
            int_ver = cls.convert_version_to_int(version)
            if int_ver >= 140:
                return True
        return False

    # TODO: implement database manipulation methods.


class OpenVSwitchControlDB_CNT(VersionableClass):
    __master__ = OpenVSwitchControlDB_140


class OpenVSwitchControlCli_140(OpenVSwitchControl):

    """
    Don't use this class directly. This class is automatically selected by
    OpenVSwitchControl.
    """
    @classmethod
    def _is_right_ver(cls):
        """
        Check condition for select control class.

        :param version: version of OpenVSwtich
        """
        version = cls.get_version()
        if version is not None:
            int_ver = cls.convert_version_to_int(version)
            if int_ver >= 140:
                return True
        return False

    def ovs_vsctl(self, params, ignore_status=False):
        return process.run('%s --db=unix:%s %s' %
                           (path.find_command("ovs-vsctl"),
                            self.db_socket, " ".join(params)), timeout=10,
                           ignore_status=ignore_status, verbose=False)

    def status(self):
        return self.ovs_vsctl(["show"]).stdout_text

    def add_br(self, br_name):
        self.ovs_vsctl(["add-br", br_name])

    def add_fake_br(self, br_name, parent, vlan):
        self.ovs_vsctl(["add-br", br_name, parent, vlan])

    def del_br(self, br_name):
        try:
            self.ovs_vsctl(["del-br", br_name])
        except process.CmdError as e:
            logging.debug(e.result)
            raise

    def br_exist(self, br_name):
        try:
            self.ovs_vsctl(["br-exists", br_name])
        except process.CmdError as e:
            if e.result.exit_status == 2:
                return False
            else:
                raise
        return True

    def list_br(self):
        return self.ovs_vsctl(["list-br"]).stdout_text.splitlines()

    def list_interface(self):
        return self.ovs_vsctl(["list", "interface"]).stdout_text.strip()

    def add_port(self, br_name, port_name):
        self.ovs_vsctl(["add-port", br_name, port_name])

    def del_port(self, br_name, port_name):
        self.ovs_vsctl(["del-port", br_name, port_name])

    def add_port_tag(self, port_name, tag):
        self.ovs_vsctl(["set", "Port", port_name, "tag=%s" % tag])

    def add_port_trunk(self, port_name, trunk):
        """
        :param trunk: list of vlans id.
        """
        trunk = list(map(lambda x: str(x), trunk))
        trunk = "[" + ",".join(trunk) + "]"
        self.ovs_vsctl(["set", "Port", port_name, "trunk=%s" % trunk])

    def set_vlanmode(self, port_name, vlan_mode):
        self.ovs_vsctl(["set", "Port", port_name, "vlan-mode=%s" % vlan_mode])

    def list_ports(self, br_name):
        result = self.ovs_vsctl(["list-ports", br_name])
        return result.stdout_text.splitlines()

    def port_to_br(self, port_name):
        """
        Return bridge which contain port.

        :param port_name: Name of port.
        :return: Bridge name or None if there is no bridge which contain port.
        """
        bridge = None
        try:
            result = self.ovs_vsctl(["port-to-br", port_name])
            bridge = result.stdout_text.strip()
        except process.CmdError as e:
            if e.result.exit_status == 1:
                pass
        return bridge


class OpenVSwitchControlCli_CNT(VersionableClass):
    __master__ = OpenVSwitchControlCli_140


class OpenVSwitchSystem(OpenVSwitchControlCli_CNT, OpenVSwitchControlDB_CNT):

    """
    OpenVSwtich class.
    """

    def __init__(self, db_path=None, db_socket=None, db_pidfile=None,
                 ovs_pidfile=None, dbschema=None, install_prefix=None):
        """
        Makes initialization of OpenVSwitch.

        :param db_path: Path of OVS database.
        :param db_socket: Path of OVS db socket.
        :param db_pidfile: Path of OVS db ovsdb-server pid.
        :param ovs_pidfile: Path of OVS ovs-vswitchd pid.
        :param install_prefix: Path where is openvswitch installed.
        """
        self.cleanup = False
        self.pid_files_path = None

    def is_installed(self):
        """
        Check if OpenVSwitch is already installed in system on default places.

        :return: Version of OpenVSwtich.
        """
        if self.get_version():
            return True
        else:
            return False

    def check_db_daemon(self):
        """
        Check if OVS daemon is started correctly.
        """
        working = utils_misc.program_is_alive(
            "ovsdb-server", self.pid_files_path)
        if not working:
            logging.error("OpenVSwitch database daemon with PID in file %s"
                          " not working.", self.db_pidfile)
        return working

    def check_switch_daemon(self):
        """
        Check if OVS daemon is started correctly.
        """
        working = utils_misc.program_is_alive(
            "ovs-vswitchd", self.pid_files_path)
        if not working:
            logging.error("OpenVSwitch switch daemon with PID in file %s"
                          " not working.", self.ovs_pidfile)
        return working

    def check_db_file(self):
        """
        Check if db_file exists.
        """
        exists = os.path.exists(self.db_path)
        if not exists:
            logging.error("OpenVSwitch database file %s not exists.",
                          self.db_path)
        return exists

    def check_db_socket(self):
        """
        Check if db socket exists.
        """
        exists = os.path.exists(self.db_socket)
        if not exists:
            logging.error("OpenVSwitch database socket file %s not exists.",
                          self.db_socket)
        return exists

    def check(self):
        return (self.check_db_daemon() and self.check_switch_daemon() and
                self.check_db_file() and self.check_db_socket())

    def init_system(self):
        """
        Create new dbfile without any configuration.
        """
        sm = factory(ServiceManager)()
        try:
            if linux_modules.load_module("openvswitch"):
                sm.restart("openvswitch")
        except process.CmdError:
            logging.error("Service OpenVSwitch is probably not"
                          " installed in system.")
            raise
        self.pid_files_path = "/var/run/openvswitch/"

    def clean(self):
        """
        Empty cleanup function
        """
        pass


class OpenVSwitch(OpenVSwitchSystem):

    """
    OpenVSwtich class.
    """

    def __init__(self, tmpdir, db_path=None, db_socket=None, db_pidfile=None,
                 ovs_pidfile=None, dbschema=None, install_prefix=None):
        """
        Makes initialization of OpenVSwitch.

        :param tmpdir: Tmp directory for save openvswitch test files.
        :param db_path: Path of OVS database.
        :param db_socket: Path of OVS db socket.
        :param db_pidfile: Path of OVS db ovsdb-server pid.
        :param ovs_pidfile: Path of OVS ovs-vswitchd pid.
        :param install_prefix: Path where is openvswitch installed.
        """
        self.tmpdir = "/%s/openvswitch" % (tmpdir)
        try:
            os.makedirs(self.tmpdir)
        except OSError as e:
            if e.errno != 17:
                raise

    def init_db(self):
        process.run('%s %s %s %s' %
                    (path.find_command("ovsdb-tool"), "create",
                     self.db_path, self.dbschema))
        process.run('%s %s %s %s %s' %
                    (path.find_command("ovsdb-server"),
                     "--remote=punix:%s" % (self.db_socket),
                     "--remote=db:Open_vSwitch,Open_vSwitch,manager_options",
                     "--pidfile=%s" % (self.db_pidfile),
                     "--detach --log-file %s") % (self.db_path))
        self.ovs_vsctl(["--no-wait", "init"])

    def start_ovs_vswitchd(self):
        """
        Start ovs vswitch daemon with only 1 socket
        """
        self.ovs_vsctl(["--no-wait", "set", "Open_vSwitch",
                        ".", "other_config:dpdk-init=true"])
        self.ovs_vsctl(["--no-wait", "set", "Open_vSwitch",
                        ".", "other_config:dpdk-socket-mem='1024'"])
        self.ovs_vsctl(["--no-wait", "set", "Open_vSwitch",
                        ".", "other_config:dpdk-lcore-mask='0x1'"])
        process.run('%s %s %s %s' %
                    (path.find_command("ovs-vswitchd"),
                     "--detach",
                     "--pidfile=%s" % self.ovs_pidfile,
                     "unix:%s" % self.db_socket))

    def create_bridge(self, br_name):
        """
        Create bridge

        :param br_name: name of bridge
        """
        self.ovs_vsctl(["add-br", br_name, "-- set bridge", br_name,
                        "datapath_type=netdev"])

    def add_ports(self, br_name, port_names):
        """
        Add ports into bridge

        :param br_name: name of bridge
        :param port_names: port names split by space
        """
        for port_name in port_names.split():
            self.ovs_vsctl(["add-port", br_name, port_name, "-- set Interface",
                            port_name, "type=dpdkvhostuser"])
            process.run('chown qemu:qemu %s/%s' % (self.pid_files_path, port_name),
                        shell=True)

    def enable_multiqueue(self, port_names, size):
        """
        Enable multiqueue

        :param port_names: port names split by space
        :param size: multiqueue size, type int
        """
        for port_name in port_names.split():
            self.ovs_vsctl(["set", "Interface", port_name,
                            "options:n_rxq=%s" % size])

    def init_new(self):
        """
        Create new dbfile without any configuration.
        """
        self.pid_files_path = "/var/run/openvswitch"
        self.db_path = os.path.join(self.tmpdir, "conf.db")
        self.db_socket = os.path.join(self.pid_files_path, "db.sock")
        self.db_pidfile = utils_misc.get_pid_path("ovsdb-server", self.pid_files_path)
        self.ovs_pidfile = utils_misc.get_pid_path("ovs-vswitchd", self.pid_files_path)
        self.dbschema = "/usr/share/openvswitch/vswitch.ovsschema"

        self.cleanup = True
        sm = factory(ServiceManager)()
        # Stop system openvswitch
        try:
            sm.stop("openvswitch")
        except process.CmdError:
            pass
        linux_modules.load_module("openvswitch")
        self.clean()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        self.init_db()
        self.start_ovs_vswitchd()

    def clean(self):
        logging.debug("Killall ovsdb-server")
        utils_misc.signal_program("ovsdb-server")
        if utils_misc.program_is_alive("ovsdb-server"):
            utils_misc.signal_program("ovsdb-server", signal.SIGKILL)
        logging.debug("Killall ovs-vswitchd")
        utils_misc.signal_program("ovs-vswitchd")
        if utils_misc.program_is_alive("ovs-vswitchd"):
            utils_misc.signal_program("ovs-vswitchd", signal.SIGKILL)
