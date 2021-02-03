"""
Virtualization test utility functions.

:copyright: 2008-2009 Red Hat Inc.
"""

from __future__ import division
import time
import string
import random
import socket
import os
import stat
import signal
import re
import logging
import subprocess
import fcntl
import sys
import inspect
import tarfile
import shutil
import getpass
import ctypes
import threading
import platform
import traceback
import math
import select
import aexpect

from hashlib import md5

try:
    from io import BytesIO
except ImportError:
    from BytesIO import BytesIO

try:
    basestring
except NameError:
    basestring = (str, bytes)

# from aexpect.utils.genio import _open_log_files
#
# from avocado.core import exceptions
# from avocado.utils import distro
# from avocado.utils import git
from remote_avocado.utils import path as utils_path
from remote_avocado.utils import process
# from avocado.utils import genio
from remote_avocado.utils import aurl
# from avocado.utils import download
# from avocado.utils import linux_modules
from remote_avocado.utils import memory
from remote_avocado.utils.astring import string_safe_encode
from remote_avocado.utils.astring import to_text
# Symlink avocado implementation of process functions
# from avocado.utils.process import CmdResult
from remote_avocado.utils.process import pid_exists  # pylint: disable=W0611
# from avocado.utils.process import safe_kill   # pylint: disable=W0611
from remote_avocado.utils.process import kill_process_tree as _kill_process_tree
# from avocado.utils.process import kill_process_by_pattern  # pylint: disable=W0611
# from avocado.utils.process import process_in_ptree_is_defunct as process_or_children_is_defunct  # pylint: disable=W0611
# Symlink avocado implementation of port-related functions

try:
    from remote_avocado.utils.network.ports import is_port_free  # pylint: disable=W0611
    from remote_avocado.utils.network.ports import find_free_port  # pylint: disable=W0611
    from remote_avocado.utils.network.ports import find_free_ports  # pylint: disable=W0611
except ImportError:
    from remote_avocado.utils.network import is_port_free  # pylint: disable=W0611
    from remote_avocado.utils.network import find_free_port  # pylint: disable=W0611
    from remote_avocado.utils.network import find_free_ports  # pylint: disable=W0611

try:
    from remote_avocado.core import teststatus
except ImportError:
    from remote_avocado.core import status as teststatus

from remote_avocado_vt.virttest import data_dir
from remote_avocado_vt.virttest import error_context
# from virttest import cartesian_config
# from virttest import utils_selinux
# from virttest import utils_disk
# from virttest import logging_manager
# from virttest import kernel_interface
# from virttest.staging import utils_koji
# from virttest.staging import service
# from virttest.xml_utils import XMLTreeFile


import six
from six.moves import xrange


ARCH = platform.machine()


class InterruptedThread(threading.Thread):

    """
    Run a function in a background thread.
    """

    def __init__(self, target, args=(), kwargs={}):
        """
        Initialize the instance.

        :param target: Function to run in the thread.
        :param args: Arguments to pass to target.
        :param kwargs: Keyword arguments to pass to target.
        """
        threading.Thread.__init__(self)
        self._target = target
        self._args = args
        self._kwargs = kwargs

    def run(self):
        """
        Run target (passed to the constructor).  No point in calling this
        function directly.  Call start() to make this function run in a new
        thread.
        """
        self._e = None
        self._retval = None
        try:
            try:
                self._retval = self._target(*self._args, **self._kwargs)
            except Exception:
                self._e = sys.exc_info()
                raise
        finally:
            # Avoid circular references (start() may be called only once so
            # it's OK to delete these)
            del self._target, self._args, self._kwargs

    def join(self, timeout=None, suppress_exception=False):
        """
        Join the thread.  If target raised an exception, re-raise it.
        Otherwise, return the value returned by target.

        :param timeout: Timeout value to pass to threading.Thread.join().
        :param suppress_exception: If True, don't re-raise the exception.
        """
        threading.Thread.join(self, timeout)
        try:
            if self._e:
                if not suppress_exception:
                    # Because the exception was raised in another thread, we
                    # need to explicitly insert the current context into it
                    s = error_context.exception_context(self._e[1])
                    s = error_context.join_contexts(error_context.get_context(), s)
                    error_context.set_exception_context(self._e[1], s)
                    six.reraise(*self._e)
            else:
                return self._retval
        finally:
            # Avoid circular references (join() may be called multiple times
            # so we can't delete these)
            self._e = None
            self._retval = None


def cmd_status_output(cmd, shell=False, ignore_status=True, verbose=True,
                      timeout=60, session=None):
    """
    common wrapper method of `def cmd_status_output()` with
    ShellSession object for VM/remote host

    NOTE: this function was previously concerned with 52LTS compatibility,
    consider its removal.

    :param cmd: command line to be run
    :param shell: Whether to run the command on a subshell
    :param ignore_status: Whether to raise an exception when command fails
    :param verbose: Whether to log the command run and stdout/stderr
    :param timeout: Time limit in seconds to wait for cmd to complete
    :param session: ShellSession object of VM/remote host
    :return: command status and output
    """
    status = None
    stdout = None
    try:
        if session:
            status, stdout = session.cmd_status_output(cmd, timeout=timeout)

        else:
            cmd_obj = process.run(cmd, shell=shell, ignore_status=ignore_status,
                                  verbose=verbose, timeout=timeout)
            status = cmd_obj.exit_status
            stdout = cmd_obj.stdout_text.strip()
    except Exception as info:
        status = 1
        stdout = to_text(info)
    finally:
        return status, stdout


def check_isdir(path, session=None):
    """
    wrapper method to check given path is dir in local/remote host/VM

    :param path: path to be checked
    :param session: ShellSession object of VM/remote host
    """
    if session:
        output = session.cmd_output("file %s" % path)
        return "directory" in output.strip()
    return os.path.isdir(path)


def write_keyval(path, dictionary, type_tag=None, tap_report=None):
    """
    Write a key-value pair format file out to a file. This uses append
    mode to open the file, so existing text will not be overwritten or
    reparsed.

    If type_tag is None, then the key must be composed of alphanumeric
    characters (or dashes+underscores). However, if type-tag is not
    null then the keys must also have "{type_tag}" as a suffix. At
    the moment the only valid values of type_tag are "attr" and "perf".

    :param path: full path of the file to be written
    :param dictionary: the items to write
    :param type_tag: see text above
    """
    if check_isdir(path):
        path = os.path.join(path, 'keyval')
    keyval = open(path, 'a')

    if type_tag is None:
        key_regex = re.compile(r'^[-\.\w]+$')
    else:
        if type_tag not in ('attr', 'perf'):
            raise ValueError('Invalid type tag: %s' % type_tag)
        escaped_tag = re.escape(type_tag)
        key_regex = re.compile(r'^[-\.\w]+\{%s\}$' % escaped_tag)
    try:
        for key in sorted(dictionary.keys()):
            if not key_regex.search(key):
                raise ValueError('Invalid key: %s' % key)
            keyval.write('%s=%s\n' % (key, dictionary[key]))
    finally:
        keyval.close()

    # same for tap
    if tap_report is not None and tap_report.do_tap_report:
        tap_report.record_keyval(path, dictionary, type_tag=type_tag)


def normalize_data_size(value_str, order_magnitude="M", factor="1024"):
    """
    Normalize a data size in one order of magnitude to another (MB to GB,
    for example).

    :param value_str: a string include the data default unit is 'B'
    :param order_magnitude: the magnitude order of result
    :param factor: the factor between two relative order of magnitude.
                   Normally could be 1024 or 1000
    """
    def __get_unit_index(M):
        try:
            return ['B', 'K', 'M', 'G', 'T'].index(M.upper())
        except ValueError:
            pass
        return 0

    regex = r"(\d+\.?\d*)\s*(\w?)"
    match = re.search(regex, value_str)
    try:
        value = match.group(1)
        unit = match.group(2)
        if not unit:
            unit = 'B'
    except TypeError:
        raise ValueError("Invalid data size format 'value_str=%s'" % value_str)
    from_index = __get_unit_index(unit)
    to_index = __get_unit_index(order_magnitude)
    scale = int(factor) ** (to_index - from_index)
    data_size = float(value) / scale
    # Control precision to avoid scientific notaion
    if data_size.is_integer():
        return "%.1f" % data_size
    else:
        return ("%.20f" % data_size).rstrip('0')


def get_usable_memory_size(align=None):
    """
    Sync, then drop host caches, then return host free memory size.

    :param align: MB use to align free memory size
    :return: host free memory size in MB
    """
    memory.drop_caches()
    usable_mem = memory.read_from_meminfo('MemFree')
    usable_mem = float(normalize_data_size("%s KB" % usable_mem))
    if align:
        usable_mem = math.floor(usable_mem / align) * align
    return usable_mem


def log_last_traceback(msg=None, log=logging.error):
    """
    Writes last traceback into specified log.

    :note: Though this function had been moved into autotest,
           keep it here for less dependencies on autotest.

    :param msg: Override the default message. ["Original traceback"]
    :param log: Where to log the traceback [logging.error]
    """
    if not log:
        log = logging.error
    if msg:
        log(msg)
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if not exc_traceback:
        log('Requested log_last_traceback but no exception was raised.')
        return
    log("Original " +
        "".join(traceback.format_exception(exc_type, exc_value,
                                           exc_traceback)))


def aton(sr):
    """
    Transform a string to a number(include float and int). If the string is
    not in the form of number, just return false.

    :param sr: string to transfrom
    :return: float, int or False for failed transform
    """
    try:
        return int(sr)
    except ValueError:
        try:
            return float(sr)
        except ValueError:
            return False


def find_substring(string, pattern1, pattern2=None):
    """
    Return the match of pattern1 in string. Or return the match of pattern2
    if pattern is not matched.

    :param string: string
    :param pattern1: first pattern want to match in string, must set.
    :param pattern2: second pattern, it will be used if pattern1 not match, optional.

    :return: Match substring or None
    """
    if not pattern1:
        logging.debug("pattern1: get empty string.")
        return None
    pattern = pattern1
    if pattern2:
        pattern += "|%s" % pattern2
    ret = re.findall(pattern, string)
    if not ret:
        logging.debug("Could not find matched string with pattern: %s",
                      pattern)
        return None
    return ret[0]


def lock_file(filename, mode=fcntl.LOCK_EX):
    lockfile = open(filename, "w")
    fcntl.lockf(lockfile, mode)
    return lockfile


def unlock_file(lockfile):
    fcntl.lockf(lockfile, fcntl.LOCK_UN)
    lockfile.close()


# Utility functions for dealing with external processes


def unique(llist):
    """
    Return a list of the elements in list, but without duplicates.

    :param list: List with values.
    :return: List with non duplicate elements.
    """
    n = len(llist)
    if n == 0:
        return []
    u = {}
    try:
        for x in llist:
            u[x] = 1
    except TypeError:
        return None
    else:
        return list(u.keys())


def find_command(cmd):
    """
    Try to find a command in the PATH, paranoid version.

    :param cmd: Command to be found.
    :raise: ValueError in case the command was not found.
    """
    logging.warning("Function utils_misc.find_command is deprecated. "
                    "Please use avocado.utils.path.find_command instead.")
    return utils_path.find_command(cmd)


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
        logging.warning("Trying to kill_process_tree with timeout but running"
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


def get_open_fds(pid):
    return len(os.listdir('/proc/%s/fd' % pid))


def get_virt_test_open_fds():
    return get_open_fds(os.getpid())


# An easy way to log lines to files when the logging system can't be used

_log_file_dir = data_dir.get_tmp_dir()
_log_lock = threading.RLock()


def _acquire_lock(lock, timeout=10):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if lock.acquire(False):
            return True
        time.sleep(0.05)
    return False


class LogLockError(Exception):
    pass


def log_line(filename, line):
    """
    Write a line to a file.

    :param filename: Path of file to write to, either absolute or relative to
                     the dir set by set_log_file_dir().
    :param line: Line to write.
    """
    global _open_log_files, _log_file_dir, _log_lock

    if not _acquire_lock(_log_lock):
        raise LogLockError("Could not acquire exclusive lock to access"
                           " _open_log_files")
    log_file = get_log_filename(filename)
    base_file = os.path.basename(log_file)
    try:
        if base_file not in _open_log_files:
            # First, let's close the log files opened in old directories
            close_log_file(base_file)
            # Then, let's open the new file
            try:
                os.makedirs(os.path.dirname(log_file))
            except OSError:
                pass
            _open_log_files[base_file] = open(log_file, "w")
        timestr = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            line = string_safe_encode(line)
        except UnicodeDecodeError:
            line = line.decode("utf-8", "ignore").encode("utf-8")
        _open_log_files[base_file].write("%s: %s\n" % (timestr, line))
        _open_log_files[base_file].flush()
    finally:
        _log_lock.release()


def set_log_file_dir(directory):
    """
    Set the base directory for log files created by log_line().

    :param dir: Directory for log files.
    """
    global _log_file_dir
    _log_file_dir = directory


def get_log_file_dir():
    """
    get the base directory for log files created by log_line().

    """
    global _log_file_dir
    return _log_file_dir


def get_log_filename(filename):
    """return full path of log file name"""
    return get_path(_log_file_dir, filename)


def close_log_file(filename):
    global _open_log_files, _log_file_dir, _log_lock
    remove = []
    if not _acquire_lock(_log_lock):
        raise LogLockError("Could not acquire exclusive lock to access"
                           " _open_log_files")
    try:
        for k in _open_log_files:
            if os.path.basename(k) == filename:
                f = _open_log_files[k]
                f.close()
                remove.append(k)
        if remove:
            for key_to_remove in remove:
                _open_log_files.pop(key_to_remove)
    finally:
        _log_lock.release()


# The following are miscellaneous utility functions.

def get_path(base_path, user_path):
    """
    Translate a user specified path to a real path.
    If user_path is relative, append it to base_path.
    If user_path is absolute, return it as is.

    :param base_path: The base path of relative user specified paths.
    :param user_path: The user specified path.
    """
    if aurl.is_url(user_path):
        return user_path
    if not os.path.isabs(user_path):
        user_path = os.path.join(base_path, user_path)
        user_path = os.path.abspath(user_path)
    return os.path.realpath(user_path)


def generate_random_string(length, ignore_str=string.punctuation,
                           convert_str=""):
    """
    Return a random string using alphanumeric characters.

    :param length: Length of the string that will be generated.
    :param ignore_str: Characters that will not include in generated string.
    :param convert_str: Characters that need to be escaped (prepend "\\").

    :return: The generated random string.
    """
    r = random.SystemRandom()
    sr = ""
    chars = string.ascii_letters + string.digits + string.punctuation
    if not ignore_str:
        ignore_str = ""
    for i in ignore_str:
        chars = chars.replace(i, "")

    while length > 0:
        tmp = r.choice(chars)
        if convert_str and (tmp in convert_str):
            tmp = "\\%s" % tmp
        sr += tmp
        length -= 1
    return sr


def generate_random_id():
    """
    Return a random string suitable for use as a qemu id.
    """
    return "id" + generate_random_string(6)


def generate_tmp_file_name(file_name, ext=None,
                           directory=data_dir.get_tmp_dir()):
    """
    Returns a temporary file name. The file is not created.
    """
    while True:
        file_name = (file_name + '-' + time.strftime("%Y%m%d-%H%M%S-") +
                     generate_random_string(4))
        if ext:
            file_name += '.' + ext
        file_name = os.path.join(directory, file_name)
        if not os.path.exists(file_name):
            break

    return file_name


def format_str_for_message(msg):
    """
    Format str so that it can be appended to a message.
    If str consists of one line, prefix it with a space.
    If str consists of multiple lines, prefix it with a newline.

    :param str: string that will be formatted.
    """
    lines = msg.splitlines()
    num_lines = len(lines)
    msg = "\n".join(lines)
    if num_lines == 0:
        return ""
    elif num_lines == 1:
        return " " + msg
    else:
        return "\n" + msg


def wait_for(func, timeout, first=0.0, step=1.0, text=None, ignore_errors=False):
    """
    Wait until func() evaluates to True.

    If func() evaluates to True before timeout expires, return the
    value of func(). Otherwise return None.

    :param timeout: Timeout in seconds
    :param first: Time to sleep before first attempt
    :param steps: Time to sleep between attempts in seconds
    :param text: Text to print while waiting, for debug purposes
    :param ignore_errors: If True, log any error and retry
    """
    start_time = time.time()
    end_time = time.time() + float(timeout)

    time.sleep(first)

    while time.time() < end_time:
        if text:
            logging.debug("%s (%f secs)", text, (time.time() - start_time))

        try:
            output = func()
        except:  # pylint: disable=W0702
            if not ignore_errors:
                raise
            else:
                logging.debug("Ignoring error '%s'", sys.exc_info())
                output = None
        if output:
            return output

        time.sleep(step)

    return None


def get_hash_from_file(hash_path, dvd_basename):
    """
    Get the a hash from a given DVD image from a hash file
    (Hash files are usually named MD5SUM or SHA1SUM and are located inside the
    download directories of the DVDs)

    :param hash_path: Local path to a hash file.
    :param cd_image: Basename of a CD image
    """
    hash_file = open(hash_path, 'r')
    for line in hash_file.readlines():
        if dvd_basename in line:
            return line.split()[0]