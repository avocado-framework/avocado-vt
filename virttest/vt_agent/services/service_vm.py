import os
import signal
import time
import logging

from virttest import data_dir

from avocado.utils.process import kill_process_tree as _kill_process_tree
from avocado.utils.process import pid_exists
from avocado.utils import process
from avocado.utils.astring import to_text

from virttest.utils_misc import *


LOG = logging.getLogger('avocado.' + __name__)


def get_testlog_filename(instance):
    return os.path.join(data_dir.get_tmp_dir(), "testlog-%s" % instance)


def kill_process_tree(pid, sig=signal.SIGKILL, send_sigcont=True, timeout=0):
    """Signal a process and all of its children.

    If the process does not exist -- return.

    :param pid: The pid of the process to signal.
    :param sig: The signal to send to the processes.
    :param send_sigcont: Send SIGCONT to allow destroying stopped processes
    :param timeout: How long to wait for the pid(s) to die
                    (negative=infinity, 0=don't wait,
                    positive=number_of_seconds)
    """
    try:
        return _kill_process_tree(pid, sig, send_sigcont, timeout)
    except TypeError:
        LOG.warning("Trying to kill_process_tree with timeout but running"
                    " old Avocado without it's support. Sleeping for 10s "
                    "instead.")
        # Depending on the Avocado version this can either return None or
        # list of killed pids.
        ret = _kill_process_tree(pid, sig, send_sigcont)    # pylint: disable=E1128
        if timeout != 0:
            # Use fixed 10s wait when no support for timeout in Avocado
            time.sleep(10)
            if pid_exists(pid):
                raise RuntimeError("Failed to kill_process_tree(%s)" % pid)
        return ret


def get_nic_device_name(nic_params):
    return process.run(nic_params.get("device_name").split(':', 1)[1], shell=True).stdout_text


def get_pid(pid):
    """
    Return the VM's PID.  If the VM is dead return None.

    :note: This works under the assumption that self.process.get_pid()
    :return: the PID of the parent shell process.
    """
    try:
        cmd = "ps --ppid=%d -o pid=" % pid
        children = process.run(cmd, verbose=False, ignore_status=True).stdout_text.split()
        return int(children[0])
    except (TypeError, IndexError, ValueError):
        return None


def get_qemu_threads(pid):
    """
    Return the list of qemu SPIDs

    :return: the list of qemu SPIDs
    """
    try:
        return os.listdir("/proc/%d/task" % pid)
    except Exception:
        return []


def get_serial_console_filename(instance, name=None):
    if name:
        return os.path.join(data_dir.get_tmp_dir(),
                            "serial-%s-%s" % (name, instance))
    return os.path.join(data_dir.get_tmp_dir(),
                        "serial-%s" % instance)


def get_qemu_version(qemu_binary):
    return process.run("%s -version" % qemu_binary, verbose=False,
                       ignore_status=True, shell=True).stdout_text.split(',')[0]


def get_support_cpu_model(qemu_binary):
    return to_text(process.run("%s -cpu \\?" % qemu_binary, verbose=False,
                               ignore_status=True, shell=True).stdout, errors='replace')
