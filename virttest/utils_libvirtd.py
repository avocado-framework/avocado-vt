"""
Module to control libvirtd service.
"""
import re
import logging

import aexpect
from avocado.utils import path
from avocado.utils import process
from avocado.utils import wait

from virttest import libvirt_version
from virttest import utils_split_daemons

from . import remote as remote_old
from . import utils_misc
from .staging import service
from .utils_gdb import GDB

try:
    path.find_command("libvirtd")
    LIBVIRTD = "libvirtd"
except path.CmdNotFoundError:
    LIBVIRTD = None


class Libvirtd(object):

    """
    Class to manage libvirtd service on host or guest.
    """

    def __init__(self, service_name=None, session=None):
        """
        Initialize an service object for libvirtd.

        :params service_name: Service name such as virtqemud or libvirtd.
            If service_name is None, all sub daemons will be operated when
            modular daemon environment is enabled. Otherwise,if service_name is
            a single string, only the given daemon/service will be operated.
        :params session: An session to guest or remote host.
        """
        self.session = session
        if self.session:
            self.remote_runner = remote_old.RemoteRunner(session=self.session)
            runner = self.remote_runner.run
        else:
            runner = process.run

        self.daemons = []
        self.service_list = []

        if LIBVIRTD is None:
            logging.warning("Libvirtd service is not available in host, "
                            "utils_libvirtd module will not function normally")

        self.service_name = "libvirtd" if not service_name else service_name

        if libvirt_version.version_compare(5, 6, 0, self.session):
            if utils_split_daemons.is_modular_daemon(session=self.session):
                if self.service_name in ["libvirtd", "libvirtd.service"]:
                    self.service_list = ['virtqemud', 'virtproxyd',
                                         'virtnetworkd', 'virtinterfaced',
                                         'virtnodedevd', 'virtsecretd',
                                         'virtstoraged', 'virtnwfilterd']
                elif self.service_name == "libvirtd.socket":
                    self.service_name = "virtqemud.socket"
                elif self.service_name in ["libvirtd-tcp.socket", "libvirtd-tls.socket"]:
                    self.service_name = re.sub("libvirtd", "virtproxyd",
                                               self.service_name)
            else:
                self.service_name = re.sub("^virt.*d", "libvirtd",
                                           self.service_name)
        else:
            self.service_name = "libvirtd"
        if not self.service_list:
            self.service_list = [self.service_name]
        for serv in self.service_list:
            self.daemons.append(service.Factory.create_service(serv, run=runner))

    def _wait_for_start(self, timeout=60):
        """
        Wait n seconds for libvirt to start. Default is 10 seconds.
        """
        def _check_start():
            virsh_cmd = "virsh list"
            try:
                if self.session:
                    self.session.cmd(virsh_cmd, timeout=2)
                else:
                    process.run(virsh_cmd, timeout=2)
                return True
            except Exception:
                return False
        return utils_misc.wait_for(_check_start, timeout=timeout)

    def start(self, reset_failed=True):
        result = []
        for daem_item in self.daemons:
            if reset_failed:
                daem_item.reset_failed()
            if not daem_item.start():
                return False
            result.append(self._wait_for_start())
        return all(result)

    def stop(self):
        result = []
        for daem_item in self.daemons:
            result.append(daem_item.stop())
        return all(result)

    def restart(self, reset_failed=True):
        result = []
        for daem_item in self.daemons:
            if reset_failed:
                daem_item.reset_failed()
            if not daem_item.restart():
                return False
            result.append(self._wait_for_start())
        return all(result)

    def is_running(self):
        result = []
        for daem_item in self.daemons:
            result.append(daem_item.status())
        return all(result)


class DaemonSocket(object):

    """
    Class to manage libvirt/virtproxy tcp/tls socket on host or guest.
    """

    def __init__(self, daemon_name, session=None):
        """
        Initialize an service object for virt daemons.

        :param daemon_name: daemon name such as virtproxyd-tls.socket,
            libvirtd-tcp.socket,etc,.
        :param session: An session to guest or remote host.
        """
        self.session = session
        if self.session:
            self.remote_runner = remote_old.RemoteRunner(session=self.session)
            self.runner = self.remote_runner.run
        else:
            self.runner = process.run

        self.daemon_name = daemon_name
        supported_daemon = ["libvirtd-tcp.socket", "libvirtd-tls.socket",
                            "virtproxyd-tls.socket", "virtproxyd-tcp.socket"]
        if self.daemon_name not in supported_daemon:
            raise ValueError("Invalid daemon: %s" % self.daemon_name)

        self.daemon_service_inst = Libvirtd("virtproxyd", session=self.session)
        self.daemon_inst = Libvirtd(self.daemon_name, session=self.session)
        self.daemon_socket = Libvirtd("virtproxyd.socket", session=self.session)

    def stop(self):
        self.daemon_socket.stop()
        self.daemon_service_inst.stop()
        self.daemon_inst.stop()
        self.runner("systemctl daemon-reload")
        self.daemon_socket.start()

    def start(self):
        self.daemon_socket.stop()
        self.daemon_service_inst.stop()
        self.runner("systemctl daemon-reload")
        self.daemon_inst.start()
        self.daemon_service_inst.start()

    def restart(self, reset_failed=True):
        self.daemon_socket.stop()
        self.daemon_service_inst.stop()
        self.runner("systemctl daemon-reload")
        self.daemon_inst.restart()
        self.daemon_service_inst.start()
        self.daemon_inst._wait_for_start()


class LibvirtdSession(object):

    """
    Interaction daemon session by directly call the command.
    With gdb debugging feature can be optionally started.
    It is recommended to use the service in the modular daemons for
    initialization, because Libvirtd() class will switch to the
    corresponding service according to the environment,
    eg. If the value of "service_name" is "virtqemud",
    it will take "virtqemud" if the modular daemon is enabled
    and "libvirtd" if it's disabled.
    """

    def __init__(self, gdb=False,
                 logging_handler=None,
                 logging_params=(),
                 logging_pattern=r'.*',
                 service_name=None):
        """
        :param gdb: Whether call the session with gdb debugging support
        :param logging_handler: Callback function to handle logging
        :param logging_pattern: Regex for filtering specific log lines
        :param service_name: Service name such as virtqemud or libvirtd
        """
        self.gdb = None
        self.tail = None
        self.running = False
        self.pid = None
        self.service_name = service_name
        self.bundle = {"stop-info": None}
        # Get an executable program to debug by GDB
        self.service_exec = Libvirtd(
            service_name=self.service_name).service_list[0]
        self.libvirtd_service = Libvirtd(service_name=self.service_exec)
        self.was_running = self.libvirtd_service.is_running()
        if self.was_running:
            logging.debug('Stopping %s service', self.service_exec)
            self.libvirtd_service.stop()

        self.logging_handler = logging_handler
        self.logging_params = logging_params
        self.logging_pattern = logging_pattern

        if gdb:
            self.gdb = GDB(self.service_exec)
            self.gdb.set_callback('stop', self._stop_callback, self.bundle)
            self.gdb.set_callback('start', self._start_callback, self.bundle)
            self.gdb.set_callback('termination', self._termination_callback)

    def _output_handler(self, line):
        """
        Adapter output callback function.
        """
        if self.logging_handler is not None:
            if re.match(self.logging_pattern, line):
                self.logging_handler(line, *self.logging_params)

    def _termination_handler(self, status):
        """
        Helper aexpect terminaltion handler
        """
        self.running = False
        self.exit_status = status
        self.pid = None

    def _termination_callback(self, gdb, status):
        """
        Termination handler function triggered when libvirtd exited.

        :param gdb: Instance of the gdb session
        :param status: Return code of exited libvirtd session
        """
        self.running = False
        self.exit_status = status
        self.pid = None

    def _stop_callback(self, gdb, info, params):
        """
        Stop handler function triggered when gdb libvirtd stopped.

        :param gdb: Instance of the gdb session
        :param status: Return code of exited libvirtd session
        """
        self.running = False
        params['stop-info'] = info

    def _start_callback(self, gdb, info, params):
        """
        Stop handler function triggered when gdb libvirtd started.

        :param gdb: Instance of the gdb session
        :param status: Return code of exited libvirtd session
        """
        self.running = True
        params['stop-info'] = None

    def set_callback(self, callback_type, callback_func, callback_params=None):
        """
        Set a customized gdb callback function.
        """
        if self.gdb:
            self.gdb.set_callback(
                callback_type, callback_func, callback_params)
        else:
            logging.error("Only gdb session supports setting callback")

    def start(self, arg_str='', wait_for_working=True):
        """
        Start libvirtd session.

        :param arg_str: Argument passing to the session
        :param wait_for_working: Whether wait for libvirtd finish loading
        """
        if self.gdb:
            self.gdb.run(arg_str=arg_str)
            self.pid = self.gdb.pid
        else:
            self.tail = aexpect.Tail(
                "%s %s" % (self.service_exec, arg_str),
                output_func=self._output_handler,
                termination_func=self._termination_handler,
            )
            self.running = True

        if wait_for_working:
            self.wait_for_working()

    def cont(self):
        """
        Continue a stopped libvirtd session.
        """
        if self.gdb:
            self.gdb.cont()
        else:
            logging.error("Only gdb session supports continue")

    def kill(self):
        """
        Kill the libvirtd session.
        """
        if self.gdb:
            self.gdb.kill()
        else:
            self.tail.kill()

    def restart(self, arg_str='', wait_for_working=True):
        """
        Restart the libvirtd session.

        :param arg_str: Argument passing to the session
        :param wait_for_working: Whether wait for libvirtd finish loading
        """
        logging.debug("Restarting %s session", self.service_exec)
        self.kill()
        self.start(arg_str=arg_str, wait_for_working=wait_for_working)

    def wait_for_working(self, timeout=60):
        """
        Wait for libvirtd to work.

        :param timeout: Max wait time
        """
        logging.debug('Waiting for %s to work', self.service_exec)
        return utils_misc.wait_for(
            self.is_working,
            timeout=timeout,
        )

    def back_trace(self):
        """
        Get the backtrace from gdb session.
        """
        if self.gdb:
            return self.gdb.back_trace()
        else:
            logging.warning('Can not get back trace without gdb')

    def insert_break(self, break_func):
        """
        Insert a function breakpoint.

        :param break_func: Function at which breakpoint inserted
        """
        if self.gdb:
            return self.gdb.insert_break(break_func)
        else:
            logging.warning('Can not insert breakpoint without gdb')

    def is_working(self):
        """
        Check if libvirtd is start by return status of 'virsh list'
        """
        virsh_cmd = "virsh list"
        try:
            process.run(virsh_cmd, timeout=2)
            return True
        except process.CmdError:
            return False

    def wait_for_stop(self, timeout=60, step=0.1):
        """
        Wait for libvirtd to stop.

        :param timeout: Max wait time
        :param step: Checking interval
        """
        logging.debug('Waiting for %s to stop', self.service_exec)
        if self.gdb:
            return self.gdb.wait_for_stop(timeout=timeout)
        else:
            return wait.wait_for(
                lambda: not self.running,
                timeout=timeout,
                step=step,
            )

    def wait_for_termination(self, timeout=60):
        """
        Wait for libvirtd gdb session to exit.

        :param timeout: Max wait time
        """
        logging.debug('Waiting for %s to terminate', self.service_exec)
        if self.gdb:
            return self.gdb.wait_for_termination(timeout=timeout)
        else:
            logging.error("Only gdb session supports wait_for_termination.")

    def exit(self):
        """
        Exit the libvirtd session.
        """
        if self.gdb:
            self.gdb.exit()
        else:
            if self.tail:
                self.tail.close()

        if self.was_running:
            self.libvirtd_service.start()


def deprecation_warning():
    """
    As the utils_libvirtd.libvirtd_xxx interfaces are deprecated,
    this function are printing the warning to user.
    """
    logging.warning("This function was deprecated, Please use "
                    "class utils_libvirtd.Libvirtd to manage "
                    "libvirtd service.")


def libvirtd_start():
    libvirtd_instance = Libvirtd()
    deprecation_warning()
    return libvirtd_instance.start()


def libvirtd_is_running():
    libvirtd_instance = Libvirtd()
    deprecation_warning()
    return libvirtd_instance.is_running()


def libvirtd_stop():
    libvirtd_instance = Libvirtd()
    deprecation_warning()
    return libvirtd_instance.stop()


def libvirtd_restart():
    libvirtd_instance = Libvirtd()
    deprecation_warning()
    return libvirtd_instance.restart()


def service_libvirtd_control(action, session=None):
    libvirtd_instance = Libvirtd(session=session)
    deprecation_warning()
    getattr(libvirtd_instance, action)()


def unmark_storage_autostarted():
    """
    By removing this file libvirt start behavior at boot
    is simulated.
    """
    cmd = "rm -rf /var/run/libvirt/storage/autostarted"
    process.run(cmd, ignore_status=True, shell=True)
