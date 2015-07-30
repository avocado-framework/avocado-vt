"""
Module to control libvirtd service.
"""
import re
import logging
import aexpect

from virttest import remote, utils_misc
from autotest.client import utils, os_dep
from autotest.client.shared import error
from virttest.staging import service
from virttest.utils_gdb import GDB


try:
    os_dep.command("libvirtd")
    LIBVIRTD = "libvirtd"
except ValueError:
    LIBVIRTD = None


class Libvirtd(object):

    """
    Class to manage libvirtd service on host or guest.
    """

    def __init__(self, session=None):
        """
        Initialize an service object for libvirtd.

        :params session: An session to guest or remote host.
        """
        self.session = session

        if self.session:
            self.remote_runner = remote.RemoteRunner(session=self.session)
            runner = self.remote_runner.run
        else:
            runner = utils.run

        if LIBVIRTD is None:
            logging.warning("Libvirtd service is not available in host, "
                            "utils_libvirtd module will not function normally")
        self.libvirtd = service.Factory.create_service(LIBVIRTD, run=runner)

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
                    utils.run(virsh_cmd, timeout=2)
                return True
            except:
                return False
        return utils_misc.wait_for(_check_start, timeout=timeout)

    def start(self, reset_failed=True):
        if reset_failed:
            self.libvirtd.reset_failed()
        if not self.libvirtd.start():
            return False
        return self._wait_for_start()

    def stop(self):
        return self.libvirtd.stop()

    def restart(self, reset_failed=True):
        if reset_failed:
            self.libvirtd.reset_failed()
        if not self.libvirtd.restart():
            return False
        return self._wait_for_start()

    def is_running(self):
        return self.libvirtd.status()


class LibvirtdSession(object):

    """
    Interaction libvirt daemon session by directly call the libvirtd command.
    With gdb debugging feature can be optionally started.
    """

    def __init__(self, gdb=False,
                 logging_handler=None,
                 logging_pattern=r'.*'):
        """
        :param gdb: Whether call the session with gdb debugging support
        :param logging_handler: Callback function to handle logging
        :param logging_pattern: Regex for filtering specific log lines
        """
        self.gdb = None
        self.tail = None
        self.running = False
        self.pid = None
        self.bundle = {"stop-info": None}
        self.libvirtd_service = Libvirtd()
        self.was_running = self.libvirtd_service.is_running()
        if self.was_running:
            logging.debug('Stopping libvirtd service')
            self.libvirtd_service.stop()

        self.logging_handler = logging_handler
        self.logging_pattern = logging_pattern

        if gdb:
            self.gdb = GDB(LIBVIRTD)
            self.gdb.set_callback('stop', self._stop_callback, self.bundle)
            self.gdb.set_callback('start', self._start_callback, self.bundle)
            self.gdb.set_callback('termination', self._termination_callback)

    def _output_handler(self, line):
        """
        Adapter output callback function.
        """
        if self.logging_handler is not None:
            if re.match(self.logging_pattern, line):
                self.logging_handler(line)

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
            self.gdb.set_callback(callback_type, callback_func, callback_params)
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
                "%s %s" % (LIBVIRTD, arg_str),
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
        logging.debug("Restarting libvirtd session")
        self.kill()
        self.start(arg_str=arg_str, wait_for_working=wait_for_working)

    def wait_for_working(self, timeout=60):
        """
        Wait for libvirtd to work.

        :param timeout: Max wait time
        """
        logging.debug('Waiting for libvirtd to work')
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
            utils.run(virsh_cmd, timeout=2)
            return True
        except error.CmdError:
            return False

    def wait_for_stop(self, timeout=60, step=0.1):
        """
        Wait for libvirtd to stop.

        :param timeout: Max wait time
        :param step: Checking interval
        """
        logging.debug('Waiting for libvirtd to stop')
        if self.gdb:
            return self.gdb.wait_for_stop(timeout=timeout)
        else:
            return utils.wait_for(
                lambda: not self.running,
                timeout=timeout,
                step=step,
            )

    def wait_for_termination(self, timeout=60):
        """
        Wait for libvirtd gdb session to exit.

        :param timeout: Max wait time
        """
        logging.debug('Waiting for libvirtd to terminate')
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
    libvirtd_instance = Libvirtd(session)
    deprecation_warning()
    getattr(libvirtd_instance, action)()
