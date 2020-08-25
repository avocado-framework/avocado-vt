"""
Module to control split daemon service.
"""
# pylint: disable=E0611
import re
import logging

import aexpect
from avocado.utils import process
from avocado.utils import wait

from virttest import libvirtd_decorator
from virttest import remote
from virttest import utils_misc
from virttest.staging import service
from virttest.utils_gdb import GDB

IS_MODULAR_DAEMON = {'local': None}


class VirtDaemonCommon(object):

    """
    Common class to manage libvirt split daemon service on host or guest.
    """
    daemon_name = ''
    virsh_cmd = "virsh -c qemu:///system list"

    def __init__(self, daemon_name='', session=None):
        """
        Initialize an service object for virt daemons.

        :param daemon_name: daemon name such as virtqemud, networkd,etc,.
        :param session: An session to guest or remote host.
        """
        if daemon_name:
            self.daemon_name = daemon_name

        self.session = session
        if self.session:
            self.remote_runner = remote.RemoteRunner(session=self.session)
            runner = self.remote_runner.run
        else:
            runner = process.run

        if not self.daemon_name:
            logging.warning("libvirt split daemon service is not available in host, "
                            "utils_daemons module will not function normally")
        self.virtdaemon = service.Factory.create_service(self.daemon_name, run=runner)

    def _wait_for_start(self, timeout=60):
        """
        Wait n seconds for daemon to start. Default is 10 seconds.

        :param timeout: time out for waiting start
        """
        def _check_start():
            try:
                if self.session:
                    self.session.cmd(self.virsh_cmd, timeout=2)
                else:
                    process.run(self.virsh_cmd, timeout=2)
                return True
            except Exception:
                return False
        return utils_misc.wait_for(_check_start, timeout=timeout)

    @libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
    def start(self, reset_failed=True):
        if reset_failed:
            self.virtdaemon.reset_failed()
        if not self.virtdaemon.start():
            return False
        return self._wait_for_start()

    @libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
    def stop(self):
        return self.virtdaemon.stop()

    @libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
    def restart(self, reset_failed=True):
        if reset_failed:
            self.virtdaemon.reset_failed()
        if not self.virtdaemon.restart():
            return False
        return self._wait_for_start()

    @libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
    def is_running(self):
        return self.virtdaemon.status()


class VirtQemud(VirtDaemonCommon):
    """
    Class for manage virtqemud daemon service on host or guest.
    """
    # Override daemon name in super class.
    daemon_name = 'virtqemud'


class VirtProxyd(VirtDaemonCommon):
    """
    Class for manage virtproxyd daemon service on host or guest.
    """
    # Override daemon name in super class.
    daemon_name = 'virtproxyd'


class VirtQemudSession(object):

    """
    Interaction virtqemud daemon session by directly call the virtqemud command.
    With gdb debugging feature can be optionally started.
    """

    def __init__(self, gdb=False,
                 logging_handler=None,
                 logging_params=(),
                 logging_pattern=r'.*'):
        """
        :param gdb: Whether call the session with gdb debugging support
        :param logging_handler: Callback function to handle logging
        :param logging_params: additional logging parameters
        :param logging_pattern: Regex for filtering specific log lines
        """
        self.gdb = None
        self.tail = None
        self.running = False
        self.pid = None
        self.bundle = {"stop-info": None}
        self.virtqemud_service = VirtQemud()
        self.was_running = self.virtqemud_service.is_running()
        if self.was_running:
            logging.debug('Stopping virtqemud service')
            self.virtqemud_service.stop()

        self.logging_handler = logging_handler
        self.logging_params = logging_params
        self.logging_pattern = logging_pattern

        if gdb:
            self.gdb = GDB('virtqemud')
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
        Termination handler function triggered when virtqemud exited.

        :param gdb: Instance of the gdb session
        :param status: Return code of exited virtqemud session
        """
        self.running = False
        self.exit_status = status
        self.pid = None

    def _stop_callback(self, gdb, info, params):
        """
        Stop handler function triggered when gdb virtqemud stopped.

        :param gdb: Instance of the gdb session
        :param info: information
        :param params: Parameter lists
        """
        self.running = False
        params['stop-info'] = info

    def _start_callback(self, gdb, info, params):
        """
        Stop handler function triggered when gdb virtqemud started.

        :param gdb: Instance of the gdb session
        :param status: Return code of exited virtqemud session
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
        Start virtqemud session.

        :param arg_str: Argument passing to the session
        :param wait_for_working: Whether wait for virtqemud finish loading
        """
        if self.gdb:
            self.gdb.run(arg_str=arg_str)
            self.pid = self.gdb.pid
        else:
            self.tail = aexpect.Tail(
                "%s %s" % ('virtqemud', arg_str),
                output_func=self._output_handler,
                termination_func=self._termination_handler,
            )
            self.running = True

        if wait_for_working:
            self.wait_for_working()

    def cont(self):
        """
        Continue a stopped virtqemud session.
        """
        if self.gdb:
            self.gdb.cont()
        else:
            logging.error("Only gdb session supports continue")

    def kill(self):
        """
        Kill the virtqemud session.
        """
        if self.gdb:
            self.gdb.kill()
        else:
            self.tail.kill()

    def restart(self, arg_str='', wait_for_working=True):
        """
        Restart the virtqemud session.

        :param arg_str: Argument passing to the session
        :param wait_for_working: Whether wait for virtqemud finish loading
        """
        logging.debug("Restarting virtqemud session")
        self.kill()
        self.start(arg_str=arg_str, wait_for_working=wait_for_working)

    def wait_for_working(self, timeout=60):
        """
        Wait for virtqemud to work.

        :param timeout: Max wait time
        """
        logging.debug('Waiting for virtqemud to work')
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
        Check if virtqemud is start by return status of 'virsh -c qemu:///system list'
        """
        virsh_cmd = "virsh -c qemu:///system list"
        try:
            process.run(virsh_cmd, timeout=2)
            return True
        except process.CmdError:
            return False

    def wait_for_stop(self, timeout=60, step=0.1):
        """
        Wait for virtqemud to stop.

        :param timeout: Max wait time
        :param step: Checking interval
        """
        logging.debug('Waiting for virtqemud to stop')
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
        Wait for virtqemud gdb session to exit.

        :param timeout: Max wait time
        """
        logging.debug('Waiting for virtqemud to terminate')
        if self.gdb:
            return self.gdb.wait_for_termination(timeout=timeout)
        else:
            logging.error("Only gdb session supports wait_for_termination.")

    def exit(self):
        """
        Exit the virtqemud session.
        """
        if self.gdb:
            self.gdb.exit()
        else:
            if self.tail:
                self.tail.close()

        if self.was_running:
            self.virtqemud_service.start()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def virtqemud_start():
    virtqemud_instance = VirtQemud()
    return virtqemud_instance.start()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def virtqemud_is_running():
    virtqemud_instance = VirtQemud()
    return virtqemud_instance.is_running()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def virtqemud_stop():
    virtqemud_instance = VirtQemud()
    return virtqemud_instance.stop()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def virtqemud_restart():
    virtqemud_instance = VirtQemud()
    return virtqemud_instance.restart()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def service_virtqemud_control(action, session=None):
    virtqemud_instance = VirtQemud(session)
    getattr(virtqemud_instance, action)()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def virtproxyd_start():
    virtproxyd_instance = VirtProxyd()
    return virtproxyd_instance.start()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def virtproxyd_is_running():
    virtproxyd_instance = VirtProxyd()
    return virtproxyd_instance.is_running()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def virtproxyd_stop():
    virtproxyd_instance = VirtProxyd()
    return virtproxyd_instance.stop()


@libvirtd_decorator.libvirt_version_context_aware_libvirtd_split
def virtproxyd_restart():
    virtproxyd_instance = VirtProxyd()
    return virtproxyd_instance.restart()


def is_modular_daemon(session=None):
    """
    Check whether modular daemon is enabled

    :params session: An session to guest or remote host
    :return: True if modular daemon is enabled
    """
    if session:
        runner = remote.RemoteRunner(session=session).run
        host_key = runner('hostname').stdout_text.strip()
        if host_key not in IS_MODULAR_DAEMON:
            IS_MODULAR_DAEMON[host_key] = None
    else:
        runner = process.run
        host_key = "local"
    if IS_MODULAR_DAEMON[host_key] is None:
        daemons = ["virtqemud.socket", "virtinterfaced.socket",
                   "virtnetworkd.socket", "virtnodedevd.socket",
                   "virtnwfilterd.socket", "virtsecretd.socket",
                   "virtstoraged.socket", "virtproxyd.socket"]

        if any([service.Factory.create_service(d, run=runner).status()
           for d in daemons]):
            IS_MODULAR_DAEMON[host_key] = True
        else:
            IS_MODULAR_DAEMON[host_key] = False
    return IS_MODULAR_DAEMON[host_key]
