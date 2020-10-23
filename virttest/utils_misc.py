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

from aexpect.utils.genio import _open_log_files

from avocado.core import exceptions
from avocado.utils import distro
from avocado.utils import git
from avocado.utils import path as utils_path
from avocado.utils import process
from avocado.utils import genio
from avocado.utils import aurl
from avocado.utils import download
from avocado.utils import linux_modules
from avocado.utils import memory
from avocado.utils.astring import string_safe_encode
from avocado.utils.astring import to_text
# Symlink avocado implementation of process functions
from avocado.utils.process import CmdResult
from avocado.utils.process import pid_exists  # pylint: disable=W0611
from avocado.utils.process import safe_kill   # pylint: disable=W0611
from avocado.utils.process import kill_process_tree as _kill_process_tree
from avocado.utils.process import kill_process_by_pattern  # pylint: disable=W0611
from avocado.utils.process import process_in_ptree_is_defunct as process_or_children_is_defunct  # pylint: disable=W0611
# Symlink avocado implementation of port-related functions

try:
    from avocado.utils.network.ports import is_port_free  # pylint: disable=W0611
    from avocado.utils.network.ports import find_free_port  # pylint: disable=W0611
    from avocado.utils.network.ports import find_free_ports  # pylint: disable=W0611
except ImportError:
    from avocado.utils.network import is_port_free  # pylint: disable=W0611
    from avocado.utils.network import find_free_port  # pylint: disable=W0611
    from avocado.utils.network import find_free_ports  # pylint: disable=W0611

try:
    from avocado.core import teststatus
except ImportError:
    from avocado.core import status as teststatus

from virttest import data_dir
from virttest import error_context
from virttest import cartesian_config
from virttest import utils_selinux
from virttest import utils_disk
from virttest import logging_manager
from virttest import kernel_interface
from virttest.staging import utils_koji
from virttest.staging import service
from virttest.xml_utils import XMLTreeFile


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


def run_tests(parser, job):
    """
    Runs the sequence of KVM tests based on the list of dictionaries
    generated by the configuration system, handling dependencies.

    :param parser: Config parser object.
    :param job: Autotest job object.

    :return: True, if all tests ran passed, False if any of them failed.
    """
    last_index = -1
    for count, dic in enumerate(parser.get_dicts()):
        logging.info("Test %4d:  %s" % (count + 1, dic["shortname"]))
        last_index += 1

    status_dict = {}
    failed = False
    # Add the parameter decide if setup host env in the test case
    # For some special tests we only setup host in the first and last case
    # When we need to setup host env we need the host_setup_flag as following:
    #    0(00): do nothing
    #    1(01): setup env
    #    2(10): cleanup env
    #    3(11): setup and cleanup env
    index = 0
    setup_flag = 1
    cleanup_flag = 2
    for param_dict in parser.get_dicts():
        cartesian_config.postfix_parse(param_dict)
        if param_dict.get("host_setup_flag", None) is not None:
            flag = int(param_dict["host_setup_flag"])
            if index == 0:
                param_dict["host_setup_flag"] = flag | setup_flag
            elif index == last_index:
                param_dict["host_setup_flag"] = flag | cleanup_flag
            else:
                param_dict["host_setup_flag"] = flag
        else:
            if index == 0:
                param_dict["host_setup_flag"] = setup_flag
            elif index == last_index:
                param_dict["host_setup_flag"] = cleanup_flag
        index += 1

        # Add kvm module status
        sysfs_dir = param_dict.get("sysfs_dir", "/sys")
        param_dict["kvm_default"] = get_module_params(sysfs_dir, 'kvm')

        if param_dict.get("skip") == "yes":
            continue
        dependencies_satisfied = True
        for dep in param_dict.get("dep"):
            for test_name in list(status_dict.keys()):
                if dep not in test_name:
                    continue
                # So the only really non-fatal state is WARN,
                # All the others make it not safe to proceed with dependency
                # execution
                if status_dict[test_name] not in ['GOOD', 'WARN']:
                    dependencies_satisfied = False
                    break
        test_iterations = int(param_dict.get("iterations", 1))
        test_tag = param_dict.get(
            "vm_type") + "." + param_dict.get("shortname")

        if dependencies_satisfied:
            # Setting up profilers during test execution.
            profilers = param_dict.get("profilers", "").split()
            for profiler in profilers:
                job.profilers.add(profiler, **param_dict)
            # We need only one execution, profiled, hence we're passing
            # the profile_only parameter to job.run_test().
            profile_only = bool(profilers) or None
            test_timeout = int(param_dict.get("test_timeout", 14400))
            current_status = job.run_test_detail("virt",
                                                 params=param_dict,
                                                 tag=test_tag,
                                                 iterations=test_iterations,
                                                 profile_only=profile_only,
                                                 timeout=test_timeout)
            for profiler in profilers:
                job.profilers.delete(profiler)
        else:
            # We will force the test to fail as TestSkip during preprocessing
            param_dict['dependency_failed'] = 'yes'
            current_status = job.run_test_detail("virt",
                                                 params=param_dict,
                                                 tag=test_tag,
                                                 iterations=test_iterations)

        if not teststatus.mapping[current_status]:
            failed = True

        status_dict[param_dict.get("name")] = current_status

    return not failed


def display_attributes(instance):
    """
    Inspects a given class instance attributes and displays them, convenient
    for debugging.
    """
    logging.debug("Attributes set:")
    for member in inspect.getmembers(instance):
        name, value = member
        attribute = getattr(instance, name)
        if not (name.startswith("__") or callable(attribute) or not value):
            logging.debug("    %s: %s", name, value)


def get_full_pci_id(pci_id):
    """
    Get full PCI ID of pci_id.

    :param pci_id: PCI ID of a device.
    """
    cmd = "lspci -D | awk '/%s/ {print $1}'" % pci_id
    try:
        return process.run(cmd, shell=True).stdout_text.strip()
    except process.CmdError:
        return None


def get_pci_id_using_filter(pci_filter, session=None):
    """
    Get PCI ID from pci filter in host or in guest.

    :param pci_filter: PCI filter regex of a device (adapter name)
    :param session: vm session object, if none use host pci info

    :return: list of pci ids with adapter name regex
    """
    cmd = "lspci | grep -F '%s' | awk '{print $1}'" % pci_filter
    status, output = cmd_status_output(cmd, shell=True, session=session)
    if status != 0 or not output:
        return []
    return str(output).strip().split()


def get_interface_from_pci_id(pci_id, session=None, nic_regex=""):
    """
    Get interface from pci id in host or in guest.

    :param pci_id: PCI id of the interface to be identified
    :param session: vm session object, if none use host interface
    :param nic_regex: regex to match nic interfaces

    :return: interface name associated with the pci id
    """
    if not nic_regex:
        nic_regex = "\w+(?=: flags)|\w+(?=\s*Link)"
    cmd = "ifconfig -a"
    status, output = cmd_status_output(cmd, shell=True, session=session)
    if status != 0:
        return None
    ethnames = re.findall(nic_regex, output.strip())
    for each_interface in ethnames:
        cmd = "ethtool -i %s | awk '/bus-info/ {print $2}'" % each_interface
        status, output = cmd_status_output(cmd, shell=True, session=session)
        if status:
            continue
        if pci_id in output.strip():
            return each_interface
    return None


def get_vendor_from_pci_id(pci_id):
    """
    Check out the device vendor ID according to pci_id.

    :param pci_id: PCI ID of a device.
    """
    cmd = "lspci -n | awk '/%s/ {print $3}'" % pci_id
    return re.sub(":", " ", process.run(cmd, shell=True,
                                        ignore_status=True).stdout_text)


def get_dev_pts_max_id():
    """
    Get the maxi ID of pseudoterminal interfaces for /dev/pts

    :param None
    """
    cmd = "ls /dev/pts/ | grep '^[0-9]*$' | sort -n"
    try:
        max_id = process.run(cmd, verbose=False,
                             shell=True).stdout_text.strip().split("\n")[-1]
    except IndexError:
        return None
    pts_file = "/dev/pts/%s" % max_id
    if not os.path.exists(pts_file):
        return None
    return max_id


def get_archive_tarball_name(source_dir, tarball_name, compression):
    '''
    Get the name for a tarball file, based on source, name and compression
    '''
    if tarball_name is None:
        tarball_name = os.path.basename(source_dir)

    if not tarball_name.endswith('.tar'):
        tarball_name = '%s.tar' % tarball_name

    if compression and not tarball_name.endswith('.%s' % compression):
        tarball_name = '%s.%s' % (tarball_name, compression)

    return tarball_name


def archive_as_tarball(source_dir, dest_dir, tarball_name=None,
                       compression='bz2', verbose=True):
    '''
    Saves the given source directory to the given destination as a tarball

    If the name of the archive is omitted, it will be taken from the
    source_dir. If it is an absolute path, dest_dir will be ignored. But,
    if both the destination directory and tarball name are given, and the
    latter is not an absolute path, they will be combined.

    For archiving directory '/tmp' in '/net/server/backup' as file
    'tmp.tar.bz2', simply use:

    >>> utils_misc.archive_as_tarball('/tmp', '/net/server/backup')

    To save the file it with a different name, say 'host1-tmp.tar.bz2'
    and save it under '/net/server/backup', use:

    >>> utils_misc.archive_as_tarball('/tmp', '/net/server/backup',
                                      'host1-tmp')

    To save with gzip compression instead (resulting in the file
    '/net/server/backup/host1-tmp.tar.gz'), use:

    >>> utils_misc.archive_as_tarball('/tmp', '/net/server/backup',
                                      'host1-tmp', 'gz')
    '''
    mode_str = 'w:%s' % compression
    if mode_str not in tarfile.open.__doc__:
        raise exceptions.TestError("compression %s is not supported method %s"
                                   % (mode_str, tarfile.open.__doc__))

    tarball_name = get_archive_tarball_name(source_dir,
                                            tarball_name,
                                            compression)
    if not os.path.isabs(tarball_name):
        tarball_path = os.path.join(dest_dir, tarball_name)
    else:
        tarball_path = tarball_name

    if verbose:
        logging.debug('Archiving %s as %s' % (source_dir,
                                              tarball_path))

    os.chdir(os.path.dirname(source_dir))
    tarball = tarfile.open(name=tarball_path, mode=mode_str)
    tarball.add(os.path.basename(source_dir))
    tarball.close()


def get_guest_service_status(session, service, service_former=None):
    """
    Get service's status in guest.
    Return 'active' for 'running' and 'active' case.
    Return 'inactive' for the other cases.

    :param session: An Expect or ShellSession instance to operate on
    :type devices: Expect or ShellSession class
    :param service: Service name that we want to check status.
    :type service: String
    :param service_former: Service's former name
    :type service: String
    :return: 'active' or 'inactive'
    :rtype: String
    """
    output = ""
    cmd = ("service %(key)s status || "
           "systemctl %(key)s.service status || "
           "status %(key)s")
    try:
        output = session.cmd_output(cmd % {'key': service})
    except Exception:
        if not service_former:
            raise exceptions.TestError("Fail to get %s status.\n%s" %
                                       (service, output))
        output = session.cmd_output(cmd % {'key': service_former})

    status = "inactive"
    if (re.search(r"Loaded: loaded", output, re.M) and
            output.count("Active: active") > 0):
        status = "active"
    elif (re.search(r"running", output.lower(), re.M) and
          not re.search(r"not running", output.lower(), re.M)):
        status = "active"

    return status


def parallel(targets):
    """
    Run multiple functions in parallel.

    :param targets: A sequence of tuples or functions.  If it's a sequence of
            tuples, each tuple will be interpreted as (target, args, kwargs) or
            (target, args) or (target,) depending on its length.  If it's a
            sequence of functions, the functions will be called without
            arguments.
    :return: A list of the values returned by the functions called.
    """
    threads = []
    for target in targets:
        if isinstance(target, tuple) or isinstance(target, list):
            t = InterruptedThread(*target)
        else:
            t = InterruptedThread(target)
        threads.append(t)
        t.start()
    return [t.join() for t in threads]


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


def check_exists(path, session=None):
    """
    wrapper method to check given path is exists in local/remote host/VM

    :param path: path to be check whether it exists
    :param session: ShellSession object of VM/remote host
    """
    if session:
        return session.cmd_status("ls -l %s" % path) == 0
    return os.path.exists(path)


def safe_rmdir(path, timeout=10, session=None):
    """
    Try to remove a directory safely, even on NFS filesystems.

    Sometimes, when running an autotest client test on an NFS filesystem, when
    not all filedescriptors are closed, NFS will create some temporary files,
    that will make shutil.rmtree to fail with error 39 (directory not empty).
    So let's keep trying for a reasonable amount of time before giving up.

    :param path: Path to a directory to be removed.
    :type path: string
    :param timeout: Time that the function will try to remove the dir before
                    giving up (seconds)
    :param session: ShellSession Object
    :type timeout: int
    :raises: OSError, with errno 39 in case after the timeout
             shutil.rmtree could not successfuly complete. If any attempt
             to rmtree fails with errno different than 39, that exception
             will be just raised.
    """
    assert check_isdir(path, session=session), "Invalid directory to remove %s" % path
    func = shutil.rmtree
    if session:
        func = session.cmd
        path = "rm -rf %s" % path
    step = int(timeout / 10)
    start_time = time.time()
    success = False
    attempts = 0
    while int(time.time() - start_time) < timeout:
        attempts += 1
        try:
            func(path)
            success = True
            break
        except OSError as err_info:
            # We are only going to try if the error happened due to
            # directory not empty (errno 39). Otherwise, raise the
            # original exception.
            if err_info.errno != 39:
                raise
            time.sleep(step)
        except (aexpect.ShellTimeoutError, aexpect.ShellError) as info:
            raise exceptions.TestSetupError("Failed to remove directory "
                                            "%s from remote machine: %s "
                                            % (path, info))

    if not success:
        raise OSError(39,
                      "Could not delete directory %s "
                      "after %d s and %d attempts." %
                      (path, timeout, attempts))


def umount(src, mount_point, fstype, verbose=False, fstype_mtab=None):
    """
    Umount the src mounted in mount_point.

    :src: mount source
    :mount_point: mount point
    :type: file system type
    :param fstype_mtab: file system type in mtab could be different
    :type fstype_mtab: str
    """
    return utils_disk.umount(src, mount_point, fstype, verbose)


def mount(src, mount_point, fstype, perm=None, verbose=False, fstype_mtab=None):
    """
    Mount the src into mount_point of the host.

    :src: mount source
    :mount_point: mount point
    :fstype: file system type
    :perm: mount permission
    :param fstype_mtab: file system type in mtab could be different
    :type fstype_mtab: str
    """
    return utils_disk.mount(src, mount_point, fstype, perm, verbose)


def is_mounted(src, mount_point, fstype, perm=None, verbose=False,
               fstype_mtab=None, session=None):
    """
    Check mount status from /etc/mtab

    :param src: mount source
    :type src: string
    :param mount_point: mount point
    :type mount_point: string
    :param fstype: file system type
    :type fstype: string
    :param perm: mount permission
    :type perm: string
    :param verbose: if display mtab content
    :type verbose: Boolean
    :param fstype_mtab: file system type in mtab could be different
    :type fstype_mtab: str
    :param session: Session Object
    :return: if the src is mounted as expect
    :rtype: Boolean
    """
    return utils_disk.is_mount(src, mount_point, fstype, perm, verbose, session)


def install_host_kernel(job, params):
    """
    Install a host kernel, given the appropriate params.

    :param job: Job object.
    :param params: Dict with host kernel install params.
    """
    install_type = params.get('host_kernel_install_type')

    if install_type == 'rpm':
        logging.info('Installing host kernel through rpm')

        rpm_url = params.get('host_kernel_rpm_url')
        k_basename = os.path.basename(rpm_url)
        dst = os.path.join(data_dir.get_tmp_dir(), k_basename)
        k = download.get_file(rpm_url, dst)
        host_kernel = job.kernel(k)
        host_kernel.install(install_vmlinux=False)
        write_keyval(job.resultdir,
                     {'software_version_kernel': k_basename})
        host_kernel.boot()

    elif install_type in ['koji', 'brew']:
        logging.info('Installing host kernel through koji/brew')

        koji_cmd = params.get('host_kernel_koji_cmd')
        koji_build = params.get('host_kernel_koji_build')
        koji_tag = params.get('host_kernel_koji_tag')

        k_deps = utils_koji.KojiPkgSpec(tag=koji_tag, build=koji_build,
                                        package='kernel',
                                        subpackages=['kernel-devel', 'kernel-firmware'])
        k = utils_koji.KojiPkgSpec(tag=koji_tag, build=koji_build,
                                   package='kernel', subpackages=['kernel'])

        c = utils_koji.KojiClient(koji_cmd)
        logging.info('Fetching kernel dependencies (-devel, -firmware)')
        c.get_pkgs(k_deps, job.tmpdir)
        logging.info('Installing kernel dependencies (-devel, -firmware) '
                     'through %s', install_type)
        k_deps_rpm_file_names = [os.path.join(job.tmpdir, rpm_file_name) for
                                 rpm_file_name in c.get_pkg_rpm_file_names(k_deps)]
        process.run('rpm -U --force %s' % " ".join(k_deps_rpm_file_names))

        c.get_pkgs(k, job.tmpdir)
        k_rpm = os.path.join(job.tmpdir,
                             c.get_pkg_rpm_file_names(k)[0])
        host_kernel = job.kernel(k_rpm)
        host_kernel.install(install_vmlinux=False)
        write_keyval(job.resultdir,
                     {'software_version_kernel':
                      " ".join(c.get_pkg_rpm_file_names(k_deps))})
        host_kernel.boot()

    elif install_type == 'git':
        logging.info('Chose to install host kernel through git, proceeding')

        repo = params.get('host_kernel_git_repo')
        repo_base = params.get('host_kernel_git_repo_base', None)
        branch = params.get('host_kernel_git_branch')
        commit = params.get('host_kernel_git_commit')
        patch_list = params.get('host_kernel_patch_list')
        if patch_list:
            patch_list = patch_list.split()
        kernel_config = params.get('host_kernel_config', None)

        repodir = os.path.join(data_dir.get_tmp_dir(), 'kernel_src')
        r = git.GitRepoHelper(uri=repo, branch=branch, destination_dir=repodir,
                              commit=commit, base_uri=repo_base)
        r.execute()
        host_kernel = job.kernel(r.destination_dir)
        if patch_list:
            host_kernel.patch(patch_list)
        if kernel_config:
            host_kernel.config(kernel_config)
        host_kernel.build()
        host_kernel.install()
        git_repo_version = '%s:%s:%s' % (r.uri, r.branch, r.get_top_commit())
        write_keyval(job.resultdir,
                     {'software_version_kernel': git_repo_version})
        host_kernel.boot()

    else:
        logging.info('Chose %s, using the current kernel for the host',
                     install_type)
        k_version = process.run('uname -r', ignore_status=True).stdout_text
        write_keyval(job.resultdir,
                     {'software_version_kernel': k_version})


def install_disktest_on_vm(test, vm, src_dir, dst_dir):
    """
    Install stress to vm.

    :param vm: virtual machine.
    :param src_dir: Source path.
    :param dst_dir: Instaltation path.
    """
    disktest_src = src_dir
    disktest_dst = os.path.join(dst_dir, "disktest")
    session = vm.wait_for_login()
    session.cmd("rm -rf %s" % (disktest_dst))
    session.cmd("mkdir -p %s" % (disktest_dst))
    session.cmd("sync")
    vm.copy_files_to(disktest_src, disktest_dst)
    session.cmd("sync")
    session.cmd("cd %s; make;" %
                (os.path.join(disktest_dst, "src")))
    session.cmd("sync")
    session.close()


def qemu_has_option(option, qemu_path="/usr/bin/qemu-kvm"):
    """
    Helper function for command line option wrappers

    :param option: Option need check.
    :param qemu_path: Path for qemu-kvm.
    """
    hlp = process.run("%s -help" % qemu_path, shell=True,
                      ignore_status=True, verbose=False).stdout_text
    return bool(re.search(r"^-%s(\s|$)" % option, hlp, re.MULTILINE))


def bitlist_to_string(data):
    """
    Transform from bit list to ASCII string.

    :param data: Bit list to be transformed
    """
    result = []
    pos = 0
    c = 0
    while pos < len(data):
        c += data[pos] << (7 - (pos % 8))
        if (pos % 8) == 7:
            result.append(c)
            c = 0
        pos += 1
    return ''.join([chr(c) for c in result])


def string_to_bitlist(data):
    """
    Transform from ASCII string to bit list.

    :param data: String to be transformed
    """
    data = [ord(c) for c in data]
    result = []
    for ch in data:
        i = 7
        while i >= 0:
            if ch & (1 << i) != 0:
                result.append(1)
            else:
                result.append(0)
            i -= 1
    return result


def strip_console_codes(output, custom_codes=None):
    """
    Remove the Linux console escape and control sequences from the console
    output. Make the output readable and can be used for result check. Now
    only remove some basic console codes using during boot up.

    :param output: The output from Linux console
    :type output: string
    :param custom_codes: The codes added to the console codes which is not
                         covered in the default codes
    :type output: string
    :return: the string wihout any special codes
    :rtype: string
    """
    if "\x1b" not in output:
        return output

    old_word = ""
    return_str = ""
    index = 0
    output = "\x1b[m%s" % output
    console_codes = "%[G@8]|\[[@A-HJ-MPXa-hl-nqrsu\`]"
    console_codes += "|\[[\d;]+[HJKgqnrm]|#8|\([B0UK]|\)|\[\d+S"
    if custom_codes is not None and custom_codes not in console_codes:
        console_codes += "|%s" % custom_codes
    while index < len(output):
        tmp_index = 0
        tmp_word = ""
        while (len(re.findall("\x1b", tmp_word)) < 2 and
               index + tmp_index < len(output)):
            tmp_word += output[index + tmp_index]
            tmp_index += 1

        tmp_word = re.sub("\x1b", "", tmp_word)
        index += len(tmp_word) + 1
        if tmp_word == old_word:
            continue
        try:
            special_code = re.findall(console_codes, tmp_word)[0]
        except IndexError:
            if index + tmp_index < len(output):
                raise ValueError("%s is not included in the known console "
                                 "codes list %s" % (tmp_word, console_codes))
            continue
        if special_code == tmp_word:
            continue
        old_word = tmp_word
        return_str += tmp_word[len(special_code):]
    return return_str


def get_module_params(sys_path, module_name):
    """
    Get the kvm module params
    :param sys_path: sysfs path for modules info
    :param module_name: module to check
    """
    dir_params = os.path.join(sys_path, "module", module_name, "parameters")
    module_params = {}
    if check_isdir(dir_params):
        for filename in os.listdir(dir_params):
            full_dir = os.path.join(dir_params, filename)
            tmp = open(full_dir, 'r').read().strip()
            module_params[full_dir] = tmp
    else:
        return None
    return module_params


def create_x509_dir(path, cacert_subj, server_subj, passphrase,
                    secure=False, bits=3072, days=1095):
    """
    Creates directory with freshly generated:
    ca-cart.pem, ca-key.pem, server-cert.pem, server-key.pem,

    :param path: defines path to directory which will be created
    :param cacert_subj: ca-cert.pem subject
    :param server_key.csr: subject
    :param passphrase: passphrase to ca-key.pem
    :param secure: defines if the server-key.pem will use a passphrase
    :param bits: bit length of keys
    :param days: cert expiration

    :raise ValueError: openssl not found or rc != 0
    :raise OSError: if os.makedirs() fails
    """

    ssl_cmd = utils_path.find_command("openssl")
    path = path + os.path.sep  # Add separator to the path
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path)

    server_key = "server-key.pem.secure"
    if secure:
        server_key = "server-key.pem"

    cmd_set = [
        ('%s genrsa -des3 -passout pass:%s -out %sca-key.pem %d' %
         (ssl_cmd, passphrase, path, bits)),
        ('%s req -new -x509 -days %d -key %sca-key.pem -passin pass:%s -out '
         '%sca-cert.pem -subj "%s"' %
         (ssl_cmd, days, path, passphrase, path, cacert_subj)),
        ('%s genrsa -out %s %d' % (ssl_cmd, path + server_key, bits)),
        ('chmod o+r %s' % path + server_key),
        ('%s req -new -key %s -out %s/server-key.csr -subj "%s"' %
         (ssl_cmd, path + server_key, path, server_subj)),
        ('%s x509 -req -passin pass:%s -days %d -in %sserver-key.csr -CA '
         '%sca-cert.pem -CAkey %sca-key.pem -set_serial 01 -out %sserver-cert.pem' %
         (ssl_cmd, passphrase, days, path, path, path, path))
    ]

    if not secure:
        cmd_set.append('%s rsa -in %s -out %sserver-key.pem' %
                       (ssl_cmd, path + server_key, path))

    for cmd in cmd_set:
        process.run(cmd)
        logging.info(cmd)


def convert_ipv4_to_ipv6(ipv4):
    """
    Translates a passed in string of an ipv4 address to an ipv6 address.

    :param ipv4: a string of an ipv4 address
    """

    converted_ip = "::ffff:"
    split_ipaddress = ipv4.split('.')
    try:
        socket.inet_aton(ipv4)
    except socket.error:
        raise ValueError("ipv4 to be converted is invalid")
    if (len(split_ipaddress) != 4):
        raise ValueError("ipv4 address is not in dotted quad format")

    for index, string in enumerate(split_ipaddress):
        if index != 1:
            test = str(hex(int(string)).split('x')[1])
            if len(test) == 1:
                final = "0"
                final += test
                test = final
        else:
            test = str(hex(int(string)).split('x')[1])
            if len(test) == 1:
                final = "0"
                final += test + ":"
                test = final
            else:
                test += ":"
        converted_ip += test
    return converted_ip


def compare_uuid(uuid1, uuid2):
    """
    compare UUID with uniform format

    :param uuid1: UUID
    :param uuid2: UUID
    :return: negative if x<y, zero if x==y, positive if x>y
    :rtype: integer
    """
    def cmp(x, y):
        return (x > y) - (x < y)
    return cmp(uuid1.replace('-', '').lower(), uuid2.replace('-', '').lower())


def add_identities_into_ssh_agent():
    """
    Adds RSA or DSA identities to the authentication agent
    """
    ssh_env = subprocess.check_output(["ssh-agent"]).decode("utf-8")
    logging.info("The current SSH ENV: %s", ssh_env)

    re_auth_sock = re.compile('SSH_AUTH_SOCK=(?P<SSH_AUTH_SOCK>[^;]*);')
    ssh_auth_sock = re.search(re_auth_sock, ssh_env).group("SSH_AUTH_SOCK")
    logging.debug("The SSH_AUTH_SOCK: %s", ssh_auth_sock)

    re_agent_pid = re.compile('SSH_AGENT_PID=(?P<SSH_AGENT_PID>[^;]*);')
    ssh_agent_pid = re.search(re_agent_pid, ssh_env).group("SSH_AGENT_PID")
    logging.debug("SSH_AGENT_PID: %s", ssh_agent_pid)

    logging.debug("Update SSH envrionment variables")
    os.environ['SSH_AUTH_SOCK'] = ssh_auth_sock
    os.system("set SSH_AUTH_SOCK " + ssh_auth_sock)
    os.environ['SSH_AGENT_PID'] = ssh_agent_pid
    process.run("set SSH_AGENT_PID " + ssh_agent_pid, shell=True)

    logging.info("Adds RSA or DSA identities to the authentication agent")
    process.run("ssh-add")


def make_dirs(dir_name, session=None):
    """
    wrapper method to create directory in local/remote host/VM

    :param dir_name: Directory name to be created
    :param session: ShellSession object of VM/remote host
    """
    if session:
        return session.cmd_status("mkdir -p %s" % dir_name) == 0
    return os.makedirs(dir_name)


def get_node_cpus(i=0):
    """
    Get cpu ids of one node

    :return: the cpu lists
    :rtype: builtin.list
    """
    cmd = process.run("numactl --hardware")
    return re.findall("node %s cpus: (.*)" % i, cmd.stdout_text)[0].split()


def cpu_str_to_list(origin_str):
    """
    Convert the cpu string to a list. The string may include comma and
    hyphen.

    :param origin_str: the cpu info string read from system
    :type origin_str: string
    :return: A list of the cpu ids
    :rtype: builtin.list
    """
    if isinstance(origin_str, six.string_types):
        origin_str = "".join([_ for _ in origin_str if _ in string.printable])
        cpu_list = []
        for cpu in origin_str.strip().split(","):
            if "-" in cpu:
                start, end = cpu.split("-")
                for cpu_id in range(int(start), int(end) + 1):
                    cpu_list.append(cpu_id)
            else:
                try:
                    cpu_id = int(cpu)
                    cpu_list.append(cpu_id)
                except ValueError:
                    logging.error("Illegimate string in cpu "
                                  "informations: %s" % cpu)
                    cpu_list = []
                    break
        cpu_list.sort()
        return cpu_list


def get_cpu_info(session=None):
    """
    Return information about the CPU architecture

    :param session: session Object
    :return: A dirt of cpu information
    """
    cpu_info = {}
    cmd = "lscpu"
    if session is None:
        output = process.run(cmd, ignore_status=True).stdout_text.splitlines()
    else:
        try:
            output = session.cmd_output(cmd).splitlines()
        finally:
            session.close()
    cpu_info = dict(map(lambda x: [i.strip() for i in x.split(":")], output))
    return cpu_info


def check_isfile(file_name, session=None):
    """
    check whether the file exist in local/remote host/VM

    :param file_name: File name to be checked
    :param session: ShellSession object of VM/remote host
    """
    if session:
        return session.cmd_status("cat %s" % file_name) == 0
    else:
        return os.path.isfile(file_name)


def make_symlink(target, link_name, session=None):
    """
    Create symlink in local/remote host/VM

    :param target: Target to be linked
    :param link_name: Link name of symbolic link
    :param session: ShellSession object of VM/remote host
    """
    if is_symlink(link_name, session):
        rm_link(link_name, session)
    if session:
        return session.cmd_status("ln -s {} {}".format(target, link_name)) == 0
    return os.symlink(target, link_name)


def rm_link(link_name, session=None):
    """
    Remove symlink in local/remote host/VM

    :param link_name: Link name to be removed
    :param session: ShellSession object of VM/remote host
    """
    if session:
        return session.cmd_status("unlink %s" % link_name) == 0
    return os.unlink(link_name)


def is_symlink(link_name, session=None):
    """
    Check if it's symlink in local/remote host/VM

    :param link_name: Link name to be checked
    :param session: ShellSession object of VM/remote host
    """
    if session:
        cmd = "file %s | grep -q 'symbolic link to'" % link_name
        return session.cmd_status(cmd) == 0
    return os.path.islink(link_name)


class NumaInfo(object):

    """
    Numa topology for host. Also provide the function for check the memory status
    of the node.
    """

    def __init__(self, all_nodes_path=None, online_nodes_path=None, session=None):
        """
        :param all_nodes_path: Alternative path to
                /sys/devices/system/node/possible. Useful for unittesting.
        :param online_nodes_path: Alternative path to
                /sys/devices/system/node/online. Useful for unittesting.
        :param session: ShellSession object
        """
        from virttest import utils_package
        self.session = session
        self.numa_sys_path = "/sys/devices/system/node"
        self.all_nodes = self.get_all_nodes(all_nodes_path)
        self.online_nodes = self.get_online_nodes(online_nodes_path)
        self.online_nodes_withmem = self.get_online_nodes_withmem()
        self.online_nodes_withcpu = self.get_online_nodes_withcpu()
        self.online_nodes_withcpumem = list(set(self.online_nodes_withcpu) &
                                            set(self.online_nodes_withmem))
        self.online_nodes_meminfo = self.get_all_node_meminfo()
        self.nodes = {}
        self.distances = {}
        self.online_nodes_cpus = self.get_all_node_cpus()

        # ensure numactl package is available
        if not utils_package.package_install('numactl', session=self.session):
            logging.error("Numactl package is not installed")

        for node_id in self.online_nodes:
            self.nodes[node_id] = NumaNode(node_id + 1, session=self.session)
            self.distances[node_id] = self.get_node_distance(node_id)

    def get_all_nodes(self, all_nodes_path=None):
        """
        Get all node ids in host.

        :return: All node ids in host
        :rtype: builtin.list
        """
        if all_nodes_path is None:
            all_nodes = get_path(self.numa_sys_path, "possible")
        else:
            all_nodes = all_nodes_path
        numa_sys = kernel_interface.SysFS(all_nodes, session=self.session,
                                          regex="\d+%s")
        return cpu_str_to_list(str(numa_sys.sys_fs_value))

    def get_online_nodes(self, online_nodes_path=None):
        """
        Get node ids online in host

        :return: The ids of node which is online
        :rtype: builtin.list
        """
        if online_nodes_path is None:
            online_nodes = get_path(self.numa_sys_path, "online")
        else:
            online_nodes = online_nodes_path
        numa_sys = kernel_interface.SysFS(online_nodes, session=self.session,
                                          regex="\d+%s")
        return cpu_str_to_list(str(numa_sys.sys_fs_value))

    def get_node_distance(self, node_id):
        """
        Get the distance from the give node to other nodes include itself.

        :param node_id: Node that you want to check
        :type node_id: string
        :return: A list in of distance for the node in positive-sequence
        :rtype: builtin.list
        """
        cmd = "numactl --hardware"
        status, output = cmd_status_output(cmd, shell=True,
                                           session=self.session)
        if status != 0:
            logging.error("Failed to get information from %s", cmd)
        try:
            node_distances = output.split("node distances:")[-1].strip()
            node_distance = re.findall("%s:.*" % node_id, node_distances)[0]
            node_distance = node_distance.split(":")[-1]
        except Exception:
            logging.warn("Get unexpect information from numctl")
            numa_sys_path = self.numa_sys_path
            distance_path = get_path(numa_sys_path,
                                     "node%s/distance" % node_id)
            if not check_isfile(distance_path, session=self.session):
                logging.error("Can not get distance information for"
                              " node %s" % node_id)
                return []
            numa_sys = kernel_interface.SysFS(distance_path, session=self.session,
                                              regex="\d+%s")
            node_distance = str(numa_sys.sys_fs_value)

        return node_distance.strip().split()

    def get_all_node_meminfo(self):
        """
        Get the complete meminfo of all online nodes.

        :return: All nodes' meminfo
        :rtype: Dict
        """
        meminfo = {}
        meminfo_file = os.path.join(self.numa_sys_path, "node%s/meminfo")
        # meminfo for online nodes are taken from numa_sys_path
        for node in self.get_online_nodes():
            node_meminfo = {}
            numa_sys = kernel_interface.SysFS(meminfo_file % node,
                                              session=self.session)
            for info in str(numa_sys.sys_fs_value.strip()).split("\n"):
                key, value = re.match(r'Node \d+ (\S+):\s+(\d+)', info).groups()
                node_meminfo[key] = value
            meminfo[node] = node_meminfo
        return meminfo

    def read_from_node_meminfo(self, node_id, key):
        """
        Get specific value of a given node from memoinfo file

        :param node_id: The node you want to check
        :type node_id: string
        :param key: The value you want to check such as MemTotal etc.
        :type key: string
        :return: The value in KB
        :rtype: string
        """
        return self.get_all_node_meminfo()[node_id][key]

    def get_all_node_cpus(self):
        """
        Get the cpus of all online nodes.

        :return: All nodes' cpus
        :rtype: Dict
        """
        cpus = {}
        cpulist_file = os.path.join(self.numa_sys_path, "node%s/cpulist")
        for node in self.get_online_nodes():
            numa_sys = kernel_interface.SysFS(cpulist_file % node,
                                              session=self.session)
            node_cpus = ""
            convert_list = re.findall("(\d+-\d+|\d+)", str(numa_sys.sys_fs_value))
            for cstr in convert_list:
                start = min(int(cstr.split("-")[0]),
                            int(cstr.split("-")[-1]))
                end = max(int(cstr.split("-")[0]),
                          int(cstr.split("-")[-1]))
                for n in range(start, end + 1, 1):
                    node_cpus += " %s" % str(n)
            cpus[node] = node_cpus
        return cpus

    def get_online_nodes_withmem(self):
        """
        Get online node with memory
        """

        online_nodes_mem = get_path(self.numa_sys_path,
                                    "has_normal_memory")
        if check_isfile(online_nodes_mem, session=self.session):
            numa_sys = kernel_interface.SysFS(online_nodes_mem,
                                              session=self.session,
                                              regex="\d+%s")
            nodes_info = str(numa_sys.sys_fs_value)
        else:
            logging.warning("sys numa node with memory file not"
                            "present, fallback to online nodes")
            return self.online_nodes
        return cpu_str_to_list(nodes_info)

    def get_online_nodes_withcpu(self):
        """
        Get online node with cpu
        """

        online_nodes_cpu = get_path(self.numa_sys_path,
                                    "has_cpu")
        if check_isfile(online_nodes_cpu, session=self.session):
            numa_sys = kernel_interface.SysFS(online_nodes_cpu,
                                              session=self.session,
                                              regex="\d+%s")
            nodes_info = str(numa_sys.sys_fs_value)
        else:
            logging.warning("sys numa node with cpu file not"
                            "present, fallback to online nodes")
            return self.online_nodes
        return cpu_str_to_list(nodes_info)


class NumaNode(object):

    """
    Numa node to control processes and shared memory.
    """

    def __init__(self, i=-1, all_nodes_path=None, online_nodes_path=None,
                 session=None):
        """
        :param all_nodes_path: Alternative path to
                /sys/devices/system/node/possible. Useful for unittesting.
        :param online_nodes_path: Alternative path to
                /sys/devices/system/node/online. Useful for unittesting.
        :param session: ShellSession object of VM/remote host
        """
        self.extra_cpus = []
        self.session = session
        if i < 0:
            host_numa_info = NumaInfo(all_nodes_path, online_nodes_path,
                                      session=self.session)
            available_nodes = list(host_numa_info.nodes.keys())
            self.cpus = self.get_node_cpus(available_nodes[-1]).split()
            if len(available_nodes) > 1:
                self.extra_cpus = self.get_node_cpus(
                    available_nodes[-2]).split()
            self.node_id = available_nodes[-1]
        else:
            self.cpus = self.get_node_cpus(i - 1).split()
            if i == 1:
                self.extra_cpus = self.get_node_cpus(i).split()
            else:
                self.extra_cpus = self.get_node_cpus(0).split()
            self.node_id = i - 1
        self.dict = {}
        for i in self.cpus:
            self.dict[i] = []
        for i in self.extra_cpus:
            self.dict[i] = []

    def get_node_cpus(self, i):
        """
        Get cpus of a specific node

        :param i: Index of the CPU inside the node.
        """
        cmd = "numactl --hardware"
        status, output = cmd_status_output(cmd, session=self.session)
        if status != 0:
            logging.error("Failed to get the information of %s", cmd)
        cpus = re.findall("node %s cpus: (.*)" % i, output)
        if cpus:
            cpus = cpus[0]
        else:
            break_flag = False
            cpulist_path = "/sys/devices/system/node/node%s/cpulist" % i
            try:
                numa_sys = kernel_interface.SysFS(cpulist_path,
                                                  session=self.session,
                                                  regex="\d+%s")
                cpus = str(numa_sys.sys_fs_value)
            except Exception as info:
                logging.warn("Can not find the cpu list information from both"
                             " numactl and sysfs. Please check your system.\n"
                             " Error: %s", info)
                break_flag = True
            if not break_flag:
                # Try to expand the numbers with '-' to a string of numbers
                # separated by blank. There number of '-' in the list depends
                # on the physical architecture of the hardware.
                try:
                    convert_list = re.findall("\d+-\d+", cpus)
                    for cstr in convert_list:
                        _ = " "
                        start = min(int(cstr.split("-")[0]),
                                    int(cstr.split("-")[1]))
                        end = max(int(cstr.split("-")[0]),
                                  int(cstr.split("-")[1]))
                        for n in range(start, end + 1, 1):
                            _ += "%s " % str(n)
                        cpus = re.sub(cstr, _, cpus)
                except (IndexError, ValueError):
                    logging.warn("The format of cpu list is not the same as"
                                 " expected.")
                    break_flag = False
            if break_flag:
                cpus = ""

        return cpus

    def get_cpu_topology(self, cpu_id):
        """
        Return cpu info dict get from sysfs.

        :param cpu_id: integer, cpu id number
        :return: topology dict of certain cpu
        """
        topology_path = "/sys/devices/system/node/node%s" % self.node_id
        topology_path += "/cpu%s/topology/" % cpu_id
        cpu_topo = {"id": str(cpu_id)}
        core_id_path = topology_path + "core_id"
        siblings_path = topology_path + "thread_siblings_list"
        socket_id_path = topology_path + "physical_package_id"
        key_list = ["core_id", "siblings", "socket_id"]
        for key in key_list:
            try:
                key_path = eval(key + '_path')
                numa_sys = kernel_interface.SysFS(key_path,
                                                  session=self.session,
                                                  regex="\d+%s")
                key_val = str(numa_sys.sys_fs_value).rstrip('\n')
                cpu_topo[key] = key_val
            except IOError:
                logging.warn("Can not find file %s from sysfs. Please check "
                             "your system." % key_path)
                cpu_topo[key] = None

        return cpu_topo

    def free_cpu(self, i, thread=None):
        """
        Release pin of one node.

        :param i: Index of the node.
        :param thread: Thread ID, remove all threads if thread ID isn't set
        """
        if not thread:
            self.dict[i] = []
        else:
            self.dict[i].remove(thread)

    def _flush_pin(self):
        """
        Flush pin dict, remove the record of exited process.
        """
        cmd = "ps -eLf | awk '{print $4}'"
        status, all_pids = cmd_status_output(cmd, shell=True, session=self.session)
        if status != 0:
            logging.error("Failed to get information of %s", cmd)
        for i in self.cpus:
            for j in self.dict[i]:
                if str(j) not in all_pids:
                    self.free_cpu(i, j)

    @error_context.context_aware
    def pin_cpu(self, pid, cpu=None, extra=False):
        """
        Pin one PID to a single cpu.

        :param pid: Process ID.
        :param cpu: CPU ID, pin thread to free CPU if cpu ID isn't set
        """
        self._flush_pin()
        if cpu:
            error_context.context(
                "Pinning process %s to the CPU(%s)" % (pid, cpu))
        else:
            error_context.context(
                "Pinning process %s to the available CPU" % pid)

        cpus = self.cpus
        if extra:
            cpus = self.extra_cpus

        for i in cpus:
            if (cpu is not None and cpu == i) or (cpu is None and not self.dict[i]):
                self.dict[i].append(pid)
                cmd = "taskset -cp %s %s" % (int(i), pid)
                logging.debug("NumaNode (%s): " % i + cmd)
                cmd_status_output(cmd, shell=True, session=self.session)
                return i

    def show(self):
        """
        Display the record dict in a convenient way.
        """
        logging.info("Numa Node record dict:")
        for i in self.cpus:
            logging.info("    %s: %s" % (i, self.dict[i]))


def get_dev_major_minor(dev):
    """
    Get the major and minor numbers of the device
    @return: Tuple(major, minor) numbers of the device
    """
    try:
        rdev = os.stat(dev).st_rdev
        return (os.major(rdev), os.minor(rdev))
    except IOError as details:
        raise exceptions.TestError("Fail to get major and minor numbers of the "
                                   "device %s:\n%s" % (dev, details))


def get_support_machine_type(qemu_binary="/usr/libexec/qemu-kvm", remove_alias=False):
    """
    Get all of the machine type the host support.

    :param qemu_binary: qemu-kvm binary file path
    :param remove_alias: True or Flase, whether remove alias or not

    :return: A tuple (s, c, v) include three lists.
    """
    o = process.run("%s -M ?" % qemu_binary).stdout_text.splitlines()
    s = []
    c = []
    v = []
    split_pattern = re.compile(r'^(\S+)\s+(.*?)(?: (\((?:alias|default).*))?$')
    for item in o[1:]:
        if remove_alias and "alias" in item:
            continue
        if "none" in item:
            continue
        machine_list = split_pattern.search(item).groups()
        s.append(machine_list[0])
        c.append(machine_list[1])
        v.append(machine_list[2])
    return (s, c, v)


def _get_backend_dir(params):
    """
    Get the appropriate backend directory. Example: backends/qemu.
    """
    return os.path.join(data_dir.get_root_dir(), 'backends',
                        params.get("vm_type", ""))


def get_qemu_binary(params):
    """
    Get the path to the qemu binary currently in use.
    """
    # Update LD_LIBRARY_PATH for built libraries (libspice-server)
    qemu_binary_path = get_path(_get_backend_dir(params),
                                params.get("qemu_binary", "qemu"))

    if not os.path.isfile(qemu_binary_path):
        logging.debug('Could not find params qemu in %s, searching the '
                      'host PATH for one to use', qemu_binary_path)
        QEMU_BIN_NAMES = ['qemu-kvm', 'qemu-system-%s' % (ARCH),
                          'qemu-system-ppc64', 'qemu-system-x86',
                          'qemu_system', 'kvm']
        for qemu_bin in QEMU_BIN_NAMES:
            try:
                qemu_binary = utils_path.find_command(qemu_bin)
                logging.debug('Found %s', qemu_binary)
                break
            except utils_path.CmdNotFoundError:
                continue
        else:
            raise exceptions.TestError("qemu binary names %s not found in "
                                       "system" % ' '.join(QEMU_BIN_NAMES))
    else:
        library_path = os.path.join(
            _get_backend_dir(params), 'install_root', 'lib')
        if check_isdir(library_path):
            library_path = os.path.abspath(library_path)
            qemu_binary = ("LD_LIBRARY_PATH=%s %s" %
                           (library_path, qemu_binary_path))
        else:
            qemu_binary = qemu_binary_path

    return qemu_binary


def get_qemu_dst_binary(params):
    """
    Get the path to the qemu dst binary currently in use.
    """
    qemu_dst_binary = params.get("qemu_dst_binary", None)
    if qemu_dst_binary is None:
        return qemu_dst_binary

    qemu_binary_path = get_path(_get_backend_dir(params), qemu_dst_binary)

    # Update LD_LIBRARY_PATH for built libraries (libspice-server)
    library_path = os.path.join(
        _get_backend_dir(params), 'install_root', 'lib')
    if check_isdir(library_path):
        library_path = os.path.abspath(library_path)
        qemu_dst_binary = ("LD_LIBRARY_PATH=%s %s" %
                           (library_path, qemu_binary_path))
    else:
        qemu_dst_binary = qemu_binary_path

    return qemu_dst_binary


def get_binary(binary_name, params):
    """
    Get the path to the binary currently in use.
    """
    key_in_params = "%s_binary" % binary_name.replace('-', '_')
    binary_path = get_path(_get_backend_dir(params),
                           params.get(key_in_params, binary_name))
    if not os.path.isfile(binary_path):
        logging.debug('Could not find params %s in %s, searching the '
                      'host PATH for one to use',
                      binary_name,
                      binary_path)
        binary_path = utils_path.find_command(binary_name)
        logging.debug('Found %s', binary_path)

    return binary_path


def get_qemu_nbd_binary(params):
    """
    Get the path to the qemu-nbd binary currently in use.
    """
    return get_binary('qemu-nbd', params)


def get_qemu_img_binary(params):
    """
    Get the path to the qemu-img binary currently in use.
    """
    return get_binary('qemu-img', params)


def get_qemu_io_binary(params):
    """
    Get the path to the qemu-io binary currently in use.
    """
    return get_binary('qemu-io', params)


def get_qemu_version(params=None):
    """
    Get the qemu-kvm(-rhev) version info.

    :param params: Passed to get_qemu_binary, can set to {} if not needed.
    :return: A dict contain qemu versoins info as {'major': int, 'minor': int,
    'update': int, 'is_rhev': bool}
    """
    version = {'major': None, 'minor': None, 'update': None, 'is_rhev': False, 'module': False}
    regex = r'\s*[Ee]mulator [Vv]ersion\s*(\d+)\.(\d+)\.(\d+)'

    if params is None:
        params = {}
    qemu_binary = get_qemu_binary(params)
    version_raw = process.run("%s -version" % qemu_binary,
                              shell=True).stdout_text.splitlines()
    for line in version_raw:
        search_result = re.search(regex, line)
        if search_result:
            version['major'] = int(search_result.group(1))
            version['minor'] = int(search_result.group(2))
            version['update'] = int(search_result.group(3))
        line_l = str(line).lower()
        if "rhev" in line_l:
            version['is_rhev'] = True
        if "module" in line_l or "scrmod" in line_l:
            version['module'] = True
    if None in list(version.values()):
        logging.error("Local install qemu version cannot be detected, "
                      "the version info is: %s" % version_raw)
        return None
    return version


def compare_qemu_version(major, minor, update, is_rhev=True, params={}):
    """
    Check if local install qemu versions is newer than provided version.

    :param major: The major version to be compared.
    :param minor: The minor version to be compared.
    :param update: The update version to be compared.
    :param is_rhev: If the qemu is a rhev version.
    :param params: Other params.
    :return: True means local installed version is equal or newer than the
    version provided, otherwise False will be returned.
    """
    installed_version = get_qemu_version(params)
    if installed_version is None:
        logging.error("Cannot get local qemu version, return False directly.")
        return False
    if installed_version['module']:
        is_rhev = False
    if is_rhev != installed_version['is_rhev']:
        return False
    installed_version_value = installed_version['major'] * 1000000 + \
        installed_version['minor'] * 1000 + \
        installed_version['update']
    compared_version_value = int(major) * 1000000 + \
        int(minor) * 1000 + \
        int(update)
    if compared_version_value > installed_version_value:
        return False
    return True


class ForAll(list):

    def __getattr__(self, name):
        def wrapper(*args, **kargs):
            return list(
                map(lambda o: o.__getattribute__(name)(*args, **kargs), self))
        return wrapper


class ForAllP(list):

    """
    Parallel version of ForAll
    """

    def __getattr__(self, name):
        def wrapper(*args, **kargs):
            threads = []
            for o in self:
                threads.append(
                    InterruptedThread(o.__getattribute__(name),
                                      args=args, kwargs=kargs))
            for t in threads:
                t.start()
            return list(map(lambda t: t.join(), threads))
        return wrapper


class ForAllPSE(list):

    """
    Parallel version of and suppress exception.
    """

    def __getattr__(self, name):
        def wrapper(*args, **kargs):
            threads = []
            for o in self:
                threads.append(
                    InterruptedThread(o.__getattribute__(name),
                                      args=args, kwargs=kargs))
            for t in threads:
                t.start()

            result = []
            for t in threads:
                ret = {}
                try:
                    ret["return"] = t.join()
                except Exception:
                    ret["exception"] = sys.exc_info()
                    ret["args"] = args
                    ret["kargs"] = kargs
                result.append(ret)
            return result
        return wrapper


def pid_is_alive(pid):
    """
    True if process pid exists and is not yet stuck in Zombie state.
    Zombies are impossible to move between cgroups, etc.
    pid can be integer, or text of integer.
    """
    path = '/proc/%s/stat' % pid

    try:
        state = genio.read_one_line(path)
    except IOError:
        if not os.path.exists(path):
            # file went away
            return False
        raise

    return state.split()[2] != 'Z'


def signal_pid(pid, sig):
    """
    Sends a signal to a process id. Returns True if the process terminated
    successfully, False otherwise.
    """
    try:
        os.kill(pid, sig)
    except OSError:
        # The process may have died before we could kill it.
        pass

    for i in range(5):
        if not pid_is_alive(pid):
            return True
        time.sleep(1)

    # The process is still alive
    return False


def get_pid_path(program_name, pid_files_dir=None):
    if not pid_files_dir:
        base_dir = os.path.dirname(__file__)
        pid_path = os.path.abspath(os.path.join(base_dir, "..", "..",
                                                "%s.pid" % program_name))
    else:
        pid_path = os.path.join(pid_files_dir, "%s.pid" % program_name)

    return pid_path


def write_pid(program_name, pid_files_dir=None):
    """
    Try to drop <program_name>.pid in the main autotest directory.

    Args:
      program_name: prefix for file name
    """
    pidfile = open(get_pid_path(program_name, pid_files_dir), "w")
    try:
        pidfile.write("%s\n" % os.getpid())
    finally:
        pidfile.close()


def delete_pid_file_if_exists(program_name, pid_files_dir=None):
    """
    Tries to remove <program_name>.pid from the main autotest directory.
    """
    pidfile_path = get_pid_path(program_name, pid_files_dir)

    try:
        os.remove(pidfile_path)
    except OSError:
        if not os.path.exists(pidfile_path):
            return
        raise


def get_pid_from_file(program_name, pid_files_dir=None):
    """
    Reads the pid from <program_name>.pid in the autotest directory.

    :param program_name the name of the program
    :return: the pid if the file exists, None otherwise.
    """
    pidfile_path = get_pid_path(program_name, pid_files_dir)
    if not os.path.exists(pidfile_path):
        return None

    pidfile = open(get_pid_path(program_name, pid_files_dir), 'r')

    try:
        try:
            pid = int(pidfile.readline())
        except IOError:
            if not os.path.exists(pidfile_path):
                return None
            raise
    finally:
        pidfile.close()

    return pid


def program_is_alive(program_name, pid_files_dir=None):
    """
    Checks if the process is alive and not in Zombie state.

    :param program_name the name of the program
    :return: True if still alive, False otherwise
    """
    pid = get_pid_from_file(program_name, pid_files_dir)
    if pid is None:
        return False
    return pid_is_alive(pid)


def signal_program(program_name, sig=signal.SIGTERM, pid_files_dir=None):
    """
    Sends a signal to the process listed in <program_name>.pid

    :param program_name the name of the program
    :param sig signal to send
    """
    pid = get_pid_from_file(program_name, pid_files_dir)
    if pid:
        signal_pid(pid, sig)


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


def get_free_disk(session, mount):
    """
    Get FreeSpace for given mount point.

    :param session: shell Object.
    :param mount: mount point(eg. C:, /mnt)

    :return string: freespace M-bytes
    """
    if re.match(r"[a-zA-Z]:", mount):
        cmd = "wmic logicaldisk where \"DeviceID='%s'\" " % mount
        cmd += "get FreeSpace"
        output = session.cmd_output(cmd)
        free = "%sK" % re.findall(r"\d+", output)[0]
    else:
        cmd = "df -h %s" % mount
        output = session.cmd_output(cmd)
        free = re.findall(r"\b([\d.]+[BKMGPETZ])\b",
                          output, re.M | re.I)[2]
    free = float(normalize_data_size(free, order_magnitude="M"))
    return int(free)


def get_free_mem(session, os_type):
    """
    Get Free memory for given OS.

    :param session: shell Object.
    :param os_type: os type (eg. linux or windows)

    :return string: freespace M-bytes
    """
    if os_type != "windows":
        free = "%s kB" % get_mem_info(session, 'MemFree')
    else:
        output = session.cmd_output("wmic OS get FreePhysicalMemory")
        free = "%sK" % re.findall("\d+", output)[0]
    free = float(normalize_data_size(free, order_magnitude="M"))
    return int(free)


def get_mem_info(session=None, attr='MemTotal'):
    """
    Get memory information attributes in host/guest

    :param session: VM session object
    :param attr: memory information attribute

    :return: memory information of attribute in kB
    """
    cmd = "grep '%s:' /proc/meminfo" % attr
    if session:
        output = session.cmd_output(cmd)
    else:
        output = process.run(cmd, shell=True).stdout_text
    output = re.findall(r"\d+\s\w", output)[0]
    output = float(normalize_data_size(output, order_magnitude="K"))
    return int(output)


def get_used_mem(session, os_type):
    """
    Get Used memory for given OS.

    :param session: shell Object.
    :param os_type: os type (eg. linux or windows)

    :return string: usedspace M-bytes
    """
    if os_type == "windows":
        cmd = "systeminfo"
        pattern = r'(Virtual Memory|Page File): In Use: (.+) MB'
    else:
        cmd = "free -m | grep 'Mem'"
        pattern = r'Mem:\s+(\d+)\s+(\d+)\s+'
    output = session.cmd_output(cmd, timeout=300)
    match = re.search(pattern, output, re.M | re.I)
    used = "%sM" % ''.join(match.group(2).split(","))
    used = float(normalize_data_size(used, order_magnitude="M"))
    return int(used)


def verify_running_as_root():
    """
    Verifies whether we're running under UID 0 (root).

    :raise: exceptions.TestSkipError
    """
    if os.getuid() != 0:
        raise exceptions.TestSkipError("This test requires root privileges "
                                       "(currently running with user %s)" %
                                       getpass.getuser())


def selinux_enforcing():
    """
    Deprecated function

    Returns True if SELinux is in enforcing mode, False if permissive/disabled

    Alias to utils_selinux.is_enforcing()
    """
    logging.warning("This function was deprecated, Please use "
                    "utils_selinux.is_enforcing().")
    return utils_selinux.is_enforcing()


def get_win_disk_vol(session, condition="VolumeName='WIN_UTILS'"):
    """
    Getting logicaldisk drive letter in windows guest.

    :param session: session Object.
    :param condition: supported condition via cmd "wmic logicaldisk list".

    :return: volume ID.
    """
    cmd = "wmic logicaldisk where (%s) get DeviceID" % condition
    output = session.cmd(cmd, timeout=120)
    device = re.search(r'(\w):', output, re.M)
    if not device:
        return ""
    return device.group(1)


def get_winutils_vol(session, label="WIN_UTILS"):
    """
    Return Volume ID of winutils CDROM ISO file should be create via command
    ``mkisofs -V $label -o winutils.iso``.

    :param session: session Object.
    :param label: volume label of WIN_UTILS.iso.

    :return: volume ID.
    """
    return wait_for(lambda: get_win_disk_vol(session,
                    condition="VolumeName='%s'" % label), 240)


def set_winutils_letter(session, cmd, label="WIN_UTILS"):
    """
    Replace label in command to real winutils CDROM drive letter.

    :param session: session Objest
    :param cmd: cmd path in winutils.iso
    :param label: volume label of WIN_UTILS.iso
    """
    if label in cmd:
        return cmd.replace(label, get_winutils_vol(session))
    return cmd


def get_uptime(session=None):
    """
    Get the uptime of system in secs

    :param session: VM session or remote session object, None for host

    :return: uptime of system in float, None on error
    """
    cmd = "cat /proc/uptime"
    if session:
        uptime = session.cmd_output(cmd)
    else:
        try:
            uptime = process.run(cmd, shell=True).stdout_text
        except process.CmdError:
            return None
    return float(uptime.split()[0])


def list_linux_guest_disks(session, partition=False):
    """
    List all disks OR disks with no partition in linux guest.

    :param session: session object to guest
    :param partition: if true, list all disks; otherwise,
                      list only disks with no partition.
    :return: the disks set.
    """
    cmd = "ls /dev/[vhs]d*"
    if not partition:
        cmd = "%s | grep -v [0-9]$" % cmd
    status, output = session.cmd_status_output(cmd)
    if status != 0:
        raise exceptions.TestFail("Get disks failed with output %s" % output)
    return set(output.split())


def get_all_disks_did(session, partition=False):
    """
    Get all disks did lists in a linux guest, each disk list
    include disk kname, serial and wwn.

    :param session: session object to guest.
    :param partition: if true, get all disks did lists; otherwise,
                      get the ones with no partition.
    :return: a dict with all disks did lists each include disk
             kname, serial and wwn.
    """
    disks = list_linux_guest_disks(session, partition)
    logging.debug("Disks detail: %s" % disks)
    all_disks_did = {}
    for line in disks:
        kname = line.split('/')[2]
        get_disk_info_cmd = "udevadm info -q property -p /sys/block/%s" % kname
        output = session.cmd_output_safe(get_disk_info_cmd)
        re_str = r"(?<=DEVNAME=/dev/)(.*)|(?<=ID_SERIAL=)(.*)|"
        re_str += "(?<=ID_SERIAL_SHORT=)(.*)|(?<=ID_WWN=)(.*)"
        did_list_group = re.finditer(re_str, output, re.M)
        did_list = [match.group() for match in did_list_group if match]
        all_disks_did[kname] = did_list

    return all_disks_did


def format_windows_disk(session, did, mountpoint=None, size=None, fstype="ntfs",
                        labletype=utils_disk.PARTITION_TABLE_TYPE_MBR, force=False):
    """
    Create a partition on disk in windows guest and format it.

    :param session: session object to guest.
    :param did: disk index which show in 'diskpart list disk'.
    :param mountpoint: mount point for the disk.
    :param size: partition size.
    :param fstype: filesystem type for the disk.
    :param labletype: disk partition table type.
    :param force: if need force format.
    :return Boolean: disk usable or not.
    """
    list_disk_cmd = "echo list disk > disk && "
    list_disk_cmd += "echo exit >> disk && diskpart /s disk"
    disks = session.cmd_output(list_disk_cmd, timeout=120)
    utils_disk.create_partition_table_windows(session, did, labletype)

    if size:
        size = int(float(normalize_data_size(size, order_magnitude="M")))

    for disk in disks.splitlines():
        if re.search(r"DISK %s" % did, disk, re.I | re.M):
            cmd_header = 'echo list disk > disk &&'
            cmd_header += 'echo select disk %s >> disk &&' % did
            cmd_footer = '&& echo exit>> disk && diskpart /s disk'
            cmd_footer += '&& del /f disk'
            detail_cmd = 'echo detail disk >> disk'
            detail_cmd = ' '.join([cmd_header, detail_cmd, cmd_footer])
            logging.debug("Detail for 'Disk%s'" % did)
            details = session.cmd_output(detail_cmd)

            pattern = "DISK %s.*Offline" % did
            if re.search(pattern, details, re.I | re.M):
                online_cmd = 'echo online disk>> disk'
                online_cmd = ' '.join([cmd_header, online_cmd, cmd_footer])
                logging.info("Online 'Disk%s'" % did)
                session.cmd(online_cmd)

            if re.search("Read.*Yes", details, re.I | re.M):
                set_rw_cmd = 'echo attributes disk clear readonly>> disk'
                set_rw_cmd = ' '.join([cmd_header, set_rw_cmd, cmd_footer])
                logging.info("Clear readonly bit on 'Disk%s'" % did)
                session.cmd(set_rw_cmd)

            if re.search(r"Volume.*%s" % fstype, details, re.I | re.M) and not force:
                logging.info("Disk%s has been formated, cancel format" % did)
                continue

            if not size:
                mkpart_cmd = 'echo create partition primary >> disk'
            else:
                mkpart_cmd = 'echo create partition primary size=%s '
                mkpart_cmd += '>> disk'
                mkpart_cmd = mkpart_cmd % size
            list_cmd = ' && echo list partition >> disk '
            cmds = ' '.join([cmd_header, mkpart_cmd, list_cmd, cmd_footer])
            logging.info("Create partition on 'Disk%s'" % did)
            partition_index = re.search(
                r'\*\s+Partition\s(\d+)\s+', session.cmd(cmds), re.M).group(1)
            logging.info("Format the 'Disk%s' to %s" % (did, fstype))
            format_cmd = 'echo list partition >> disk && '
            format_cmd += 'echo select partition %s >> disk && ' % partition_index
            if not mountpoint:
                format_cmd += 'echo assign >> disk && '
            else:
                format_cmd += 'echo assign letter=%s >> disk && ' % mountpoint
            format_cmd += 'echo format fs=%s quick >> disk ' % fstype
            format_cmd = ' '.join([cmd_header, format_cmd, cmd_footer])
            session.cmd(format_cmd, timeout=300)

            return True

    return False


def format_linux_disk(session, did, all_disks_did, partition=False,
                      mountpoint=None, size=None, fstype="ext3"):
    """
    Create a partition on disk in linux guest and format and mount it.

    :param session: session object to guest.
    :param did: disk kname, serial or wwn.
    :param all_disks_did: all disks did lists each include
                          disk kname, serial and wwn.
    :param partition: if true, can format all disks; otherwise,
                      only format the ones with no partition originally.
    :param mountpoint: mount point for the disk.
    :param size: partition size.
    :param fstype: filesystem type for the disk.
    :return Boolean: disk usable or not.
    """
    disks = list_linux_guest_disks(session, partition)
    logging.debug("Disks detail: %s" % disks)
    for line in disks:
        kname = line.split('/')[2]
        did_list = all_disks_did[kname]
        if did not in did_list:
            # Continue to search target disk
            continue
        if not size:
            size_output = session.cmd_output_safe("lsblk -oKNAME,SIZE|grep %s"
                                                  % kname)
            size = size_output.splitlines()[0].split()[1]
        all_disks_before = list_linux_guest_disks(session, True)
        devname = line
        logging.info("Create partition on disk '%s'" % devname)
        mkpart_cmd = "parted -s %s mklabel gpt mkpart "
        mkpart_cmd += "primary 0 %s"
        mkpart_cmd = mkpart_cmd % (devname, size)
        session.cmd_output_safe(mkpart_cmd)
        session.cmd_output_safe("partprobe %s" % devname)
        all_disks_after = list_linux_guest_disks(session, True)
        partname = (all_disks_after - all_disks_before).pop()
        logging.info("Format partition to '%s'" % fstype)
        format_cmd = "yes|mkfs -t %s %s" % (fstype, partname)
        session.cmd_output_safe(format_cmd)
        if not mountpoint:
            session.cmd_output_safe("mkdir /mnt/%s" % kname)
            mountpoint = os.path.join("/mnt", kname)
        logging.info("Mount the disk to '%s'" % mountpoint)
        mount_cmd = "mount -t %s %s %s" % (fstype, partname, mountpoint)
        session.cmd_output_safe(mount_cmd)
        return True

    return False


def format_guest_disk(session, did, all_disks_did, ostype, partition=False,
                      mountpoint=None, size=None, fstype=None):
    """
    Create a partition on disk in guest and format and mount it.

    :param session: session object to guest.
    :param did: disk ID in guest.
    :param all_disks_did: a dict contains all disks did lists each
                          include disk kname, serial and wwn for linux guest.
    :param ostype: guest os type 'windows' or 'linux'.
    :param partition: if true, can format all disks; otherwise,
                      only format the ones with no partition originally.
    :param mountpoint: mount point for the disk.
    :param size: partition size.
    :param fstype: filesystem type for the disk; when it's the default None,
                   it will use the default one for corresponding ostype guest
    :return Boolean: disk usable or not.
    """
    default_fstype = "ntfs" if (ostype == "windows") else "ext3"
    fstype = fstype or default_fstype
    if ostype == "windows":
        return format_windows_disk(session, did, mountpoint, size, fstype)
    return format_linux_disk(session, did, all_disks_did, partition,
                             mountpoint, size, fstype)


def get_linux_drive_path(session, did, timeout=120):
    """
    Get drive path in guest by drive serial or wwn

    :param session: session object to guest.
    :param did: drive serial or wwn.
    :return String: drive path
    """
    cmd = 'for dev_path in `ls -d /sys/block/*`; do '
    cmd += 'echo `udevadm info -q property -p $dev_path`; done'
    status, output = session.cmd_status_output(cmd, timeout=timeout)
    if status != 0:
        logging.error("Can not get drive infomation:\n%s" % output)
        return ""
    p = r"DEVNAME=([^\s]+)\s.*(?:ID_SERIAL|ID_SERIAL_SHORT|ID_WWN)=%s" % did
    dev = re.search(p, output, re.M)
    if dev:
        return dev.groups()[0]
    logging.error("Can not get drive path by id '%s', "
                  "command output:\n%s" % (did, output))
    return ""


def get_windows_drive_letters(session):
    """
    Get drive letters has been assigned

    :param session: session object to guest
    :return list: letters has been assigned
    """
    list_letters_cmd = "fsutil fsinfo drives"
    drive_letters = re.findall(
        r'(\w+):\\', session.cmd_output(list_letters_cmd), re.M)

    return drive_letters


def valued_option_dict(options, split_pattern, start_count=0, dict_split=None):
    """
    Divide the valued options into key and value

    :param options: the valued options get from cfg
    :param split_pattern: patten used to split options
    :param dict_split: patten used to split sub options and insert into dict
    :param start_count: the start_count to insert option_dict
    :return: dict include option and its value
    """
    option_dict = {}
    if options.strip() is not None:
        pat = re.compile(split_pattern)
        option_list = pat.split(options.lstrip(split_pattern))
        logging.debug("option_list is %s", option_list)

        for match in option_list[start_count:]:
            match_list = match.split(dict_split)
            if len(match_list) == 2:
                key = match_list[0]
                value = match_list[1]
                if key not in option_dict:
                    option_dict[key] = value
                else:
                    logging.debug("key %s in option_dict", key)
                    option_dict[key] = option_dict[key].split()
                    option_dict[key].append(value)

    return option_dict


def get_image_snapshot(image_file):
    """
    Get image snapshot ID and put it into a list.
    Image snapshots like this:

    Snapshot list:
    ID        TAG                 VM SIZE                DATE       VM CLOCK
    1         1460096943             3.1M 2016-04-08 14:29:03   00:00:00.110
    """
    try:
        cmd = "qemu-img snapshot %s -l" % image_file
        if compare_qemu_version(2, 10, 0):
            # Currently the qemu lock is only introduced in qemu-kvm-rhev,
            # if it's introduced in qemu-kvm, will need to update it here.
            # The "-U" is to avoid the qemu lock.
            cmd += " -U"
        snap_info = process.run(cmd, ignore_status=False).stdout_text.strip()
        snap_list = []
        if snap_info:
            pattern = "(\d+) +\d+ +.*"
            for line in snap_info.splitlines():
                snap_list.extend(re.findall(r"%s" % pattern, line))
        return snap_list
    except process.CmdError as detail:
        raise exceptions.TestError("Fail to get snapshot of %s:\n%s" %
                                   (image_file, detail))


def check_qemu_image_lock_support():
    """
    Check qemu-img whether supporting image lock or not
    :return: The boolean of checking result
    """
    cmd = "qemu-img"
    binary_path = utils_path.find_command(cmd)
    cmd_result = process.run(binary_path + ' -h', ignore_status=True,
                             shell=True, verbose=False)
    return b'-U' in cmd_result.stdout


def get_image_info(image_file):
    """
    Get image information and put it into a dict. Image information like this:

    ::

        *******************************
        image: /path/vm1_6.3.img
        file format: raw
        virtual size: 10G (10737418240 bytes)
        disk size: 888M
        ....
        image: /path/vm2_6.3.img
        file format: raw
        virtual size: 1.0M (1024000 bytes)
        disk size: 196M
        ....
        image: n3.qcow2
        file format: qcow2
        virtual size: 1.0G (1073741824 bytes)
        disk size: 260K
        cluster_size: 512
        Format specific information:
            compat: 1.1
            lazy refcounts: false
            refcount bits: 16
            corrupt: false
        ....
        *******************************

    And the image info dict will be like this

    ::

        image_info_dict = {'format':'raw',
                           'vsize' : '10737418240',
                           'dsize' : '931135488',
                           'csize' : '65536'}
    """
    try:
        cmd = "qemu-img info %s" % image_file
        if check_qemu_image_lock_support():
            # Currently the qemu lock is introduced in qemu-kvm-rhev/ma,
            # The " -U" is to avoid the qemu lock.
            cmd += " -U"
        image_info = process.run(cmd, ignore_status=False).stdout_text.strip()
        image_info_dict = {}
        vsize = None
        if image_info:
            for line in image_info.splitlines():
                if line.find("file format") != -1:
                    image_info_dict['format'] = line.split(':')[-1].strip()
                elif line.find("virtual size") != -1 and vsize is None:
                    # Use the value in (xxxxxx bytes) since it's the more
                    # realistic value. For a "1000k" disk, qemu-img will
                    # show 1.0M and 1024000 bytes. The 1.0M will translate
                    # into 1048576 bytes which isn't necessarily correct
                    vsize = line.split("(")[-1].strip().split(" ")[0]
                    image_info_dict['vsize'] = int(vsize)
                elif line.find("disk size") != -1:
                    dsize = line.split(':')[-1].strip()
                    image_info_dict['dsize'] = int(float(
                        normalize_data_size(dsize, order_magnitude="B",
                                            factor=1024)))
                elif line.find("cluster_size") != -1:
                    csize = line.split(':')[-1].strip()
                    image_info_dict['csize'] = int(csize)
                elif line.find("compat") != -1:
                    compat = line.split(':')[-1].strip()
                    image_info_dict['compat'] = compat
                elif line.find("lazy refcounts") != -1:
                    lazy_refcounts = line.split(':')[-1].strip()
                    image_info_dict['lcounts'] = lazy_refcounts
        return image_info_dict
    except (KeyError, IndexError, process.CmdError) as detail:
        raise exceptions.TestError("Fail to get information of %s:\n%s" %
                                   (image_file, detail))


def is_qemu_capability_supported(capability):
    """
    Check if the specified qemu capability is supported
    using libvirt cache.

    :param capability: the qemu capability to be queried
    :type capability: str

    :return: True if the capabilitity is found, otherwise False
    :rtype: Boolean
    :raise: exceptions.TestError: if no capability file or no directory
    """
    qemu_path = "/var/cache/libvirt/qemu/capabilities/"
    if not check_isdir(qemu_path) or not len(os.listdir(qemu_path)):
        raise exceptions.TestError("Missing the directory %s or no file "
                                   "exists in the directory" % qemu_path)
    qemu_capxml = qemu_path + os.listdir(qemu_path)[0]
    xmltree = XMLTreeFile(qemu_capxml)
    for elem in xmltree.getroot().findall('flag'):
        name = elem.attrib.get('name')
        if name == capability:
            logging.info("The qemu capability '%s' is supported", capability)
            return True
    logging.info("The qemu capability '%s' is not supported.", capability)
    return False


def get_test_entrypoint_func(name, module):
    '''
    Returns the test entry point function for a loaded module

    :param name: the name of the test. Usually supplied on a cartesian
                 config file using the "type" key
    :type name: str
    :param module: a loaded python module for containing the code
                        for the test named on ``name``
    :type module: module
    :raises: ValueError if module does not have a suitable function
    :returns: the test entry point function
    :rtype: func
    '''
    has_run = hasattr(module, "run")
    legacy_run = "run_%s" % name
    has_legacy_run = hasattr(module, legacy_run)

    if has_run:
        if has_legacy_run:
            msg = ('Both legacy and new test entry point function names '
                   'present. Please update your test and use "run()" '
                   'instead of "%s()". Also, please avoid using "%s()" '
                   'as a regular function name in your test as it causes '
                   'confusion with the legacy naming standard. Function '
                   '"run()" will be used in favor of "%s()"')
            logging.warn(msg, legacy_run, legacy_run, legacy_run)
        return getattr(module, "run")

    elif has_legacy_run:
        logging.warn('Legacy test entry point function name found. Please '
                     'update your test and use "run()" as the new function '
                     'name')
        return getattr(module, legacy_run)

    else:
        raise ValueError("Missing test entry point")


class KSMError(Exception):

    """
    Base exception for KSM setup
    """
    pass


class KSMNotSupportedError(KSMError):

    """
    Thrown when host does not support KSM.
    """
    pass


class KSMTunedError(KSMError):

    """
    Thrown when KSMTuned Error happen.
    """
    pass


class KSMTunedNotSupportedError(KSMTunedError):

    """
    Thrown when host does not support KSMTune.
    """
    pass


class KSMController(object):

    """KSM Manager"""

    def __init__(self):
        """
        Preparations for ksm.
        """
        _KSM_PATH = "/sys/kernel/mm/ksm/"
        self.ksm_path = _KSM_PATH
        self.ksm_params = {}

        # Default control way is files on host
        # But it will be ksmctl command on older ksm version
        self.interface = "sysfs"
        if check_isdir(self.ksm_path):
            _KSM_PARAMS = os.listdir(_KSM_PATH)
            for param in _KSM_PARAMS:
                self.ksm_params[param] = _KSM_PATH + param
            self.interface = "sysfs"
            if not os.path.isfile(self.ksm_params["run"]):
                raise KSMNotSupportedError
        else:
            try:
                utils_path.find_command("ksmctl")
            except utils_path.CmdNotFoundError:
                raise KSMNotSupportedError
            _KSM_PARAMS = ["run", "pages_to_scan", "sleep_millisecs"]
            # No _KSM_PATH needed here
            for param in _KSM_PARAMS:
                self.ksm_params[param] = None
            self.interface = "ksmctl"

    def is_module_loaded(self):
        """Check whether ksm module has been loaded."""
        if process.system("lsmod |grep ksm", ignore_status=True):
            return False
        return True

    def load_ksm_module(self):
        """Try to load ksm module."""
        process.system("modprobe ksm")

    def unload_ksm_module(self):
        """Try to unload ksm module."""
        process.system("modprobe -r ksm")

    def get_ksmtuned_pid(self):
        """
        Return ksmtuned process id(0 means not running).
        """
        try:
            utils_path.find_command("ksmtuned")
        except utils_path.CmdNotFoundError:
            raise KSMTunedNotSupportedError

        process_id = process.run("ps -C ksmtuned -o pid=",
                                 ignore_status=True).stdout_text
        if process_id:
            return int(re.findall("\d+", process_id)[0])
        return 0

    def start_ksmtuned(self):
        """Start ksmtuned service"""
        if self.get_ksmtuned_pid() == 0:
            process.system("setsid ksmtuned >& /dev/null", shell=True)

    def stop_ksmtuned(self):
        """Stop ksmtuned service"""
        pid = self.get_ksmtuned_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)

    def restart_ksmtuned(self):
        """Restart ksmtuned service"""
        self.stop_ksmtuned()
        self.start_ksmtuned()

    def start_ksm(self, pages_to_scan=None, sleep_ms=None):
        """
        Start ksm function.
        """
        if not self.is_ksm_running():
            feature_args = {'run': 1}
            if self.interface == "ksmctl":
                if pages_to_scan is None:
                    pages_to_scan = 5000
                if sleep_ms is None:
                    sleep_ms = 50
                feature_args["pages_to_scan"] = pages_to_scan
                feature_args["sleep_millisecs"] = sleep_ms
            self.set_ksm_feature(feature_args)

    def stop_ksm(self):
        """
        Stop ksm function.
        """
        if self.is_ksm_running():
            return self.set_ksm_feature({"run": 0})

    def restart_ksm(self, pages_to_scan=None, sleep_ms=None):
        """Restart ksm service"""
        self.stop_ksm()
        self.start_ksm(pages_to_scan, sleep_ms)

    def is_ksm_running(self):
        """
        Verify whether ksm is running.
        """
        if self.interface == "sysfs":
            running = process.run("cat %s" % self.ksm_params["run"]).stdout_text
        else:
            output = process.run("ksmctl info").stdout_text
            try:
                running = re.findall("\d+", output)[0]
            except IndexError:
                raise KSMError
        if running != '0':
            return True
        return False

    def get_writable_features(self):
        """Get writable features for setting"""
        writable_features = []
        if self.interface == "sysfs":
            # Get writable parameters
            for key, value in list(self.ksm_params.items()):
                if stat.S_IMODE(os.stat(value).st_mode) & stat.S_IWRITE:
                    writable_features.append(key)
        else:
            for key in list(self.ksm_params.keys()):
                writable_features.append(key)
        return writable_features

    def set_ksm_feature(self, feature_args):
        """
        Set ksm features.

        :param feature_args: a dict include features and their's value.
        """
        for key in list(feature_args.keys()):
            if key not in self.get_writable_features():
                logging.error("Do not support setting of '%s'.", key)
                raise KSMError
        if self.interface == "sysfs":
            # Get writable parameters
            for key, value in list(feature_args.items()):
                process.system("echo %s > %s" % (value, self.ksm_params[key]),
                               shell=True)
        else:
            if "run" in list(feature_args.keys()) and feature_args["run"] == 0:
                process.system("ksmctl stop")
            else:
                # For ksmctl both pages_to_scan and sleep_ms should have value
                # So start it anyway if run is 1
                # Default is original value if feature is not in change list.
                if "pages_to_scan" not in list(feature_args.keys()):
                    pts = self.get_ksm_feature("pages_to_scan")
                else:
                    pts = feature_args["pages_to_scan"]
                if "sleep_millisecs" not in list(feature_args.keys()):
                    ms = self.get_ksm_feature("sleep_millisecs")
                else:
                    ms = feature_args["sleep_millisecs"]
                process.system("ksmctl start %s %s" % (pts, ms))

    def get_ksm_feature(self, feature):
        """
        Get ksm feature's value.
        """
        if feature in list(self.ksm_params.keys()):
            feature = self.ksm_params[feature]

        if self.interface == "sysfs":
            return process.run("cat %s" % feature).stdout_text.strip()
        else:
            output = process.run("ksmctl info").stdout_text
            _KSM_PARAMS = ["run", "pages_to_scan", "sleep_millisecs"]
            ksminfos = re.findall("\d+", output)
            if len(ksminfos) != 3:
                raise KSMError
            try:
                return ksminfos[_KSM_PARAMS.index(feature)]
            except ValueError:
                raise KSMError


def monotonic_time():
    """
    Get monotonic time
    """
    def monotonic_time_os():
        """
        Get monotonic time using ctypes
        """
        class struct_timespec(ctypes.Structure):
            _fields_ = [('tv_sec', ctypes.c_long), ('tv_nsec', ctypes.c_long)]

        lib = ctypes.CDLL("librt.so.1", use_errno=True)
        clock_gettime = lib.clock_gettime
        clock_gettime.argtypes = [
            ctypes.c_int, ctypes.POINTER(struct_timespec)]

        timespec = struct_timespec()
        # CLOCK_MONOTONIC_RAW == 4
        if not clock_gettime(4, ctypes.pointer(timespec)) == 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))

        return timespec.tv_sec + timespec.tv_nsec * 10 ** -9

    monotonic_attribute = getattr(time, "monotonic", None)
    if callable(monotonic_attribute):
        # Introduced in Python 3.3
        return time.monotonic()
    else:
        return monotonic_time_os()


def verify_dmesg(dmesg_log_file=None, ignore_result=False, level_check=3,
                 session=None):
    """
    Find host/guest call trace in dmesg log.

    :param dmesg_log_file: The file used to save host dmesg. If None, will save
                           guest/host dmesg to logging.debug.
    :param ignore_result: True or False, whether to fail test case on issues
    :param level_check: level of severity of issues to be checked
                        1 - emerg
                        2 - emerg,alert
                        3 - emerg,alert,crit
                        4 - emerg,alert,crit,err
                        5 - emerg,alert,crit,err,warn
    :param session: session object to guest
    :param return: if ignore_result=True, return True if no errors/crash
                   observed, False otherwise.
    :param raise: if ignore_result=False, raise TestFail exception on
                  observing errors/crash
    """
    cmd = "dmesg -T -l %s|grep ." % ",".join(map(str, xrange(0, int(level_check))))
    if session:
        environ = "guest"
        status, output = session.cmd_status_output(cmd)
    else:
        environ = "host"
        out = process.run(cmd, timeout=30, ignore_status=True,
                          verbose=False, shell=True)
        status = out.exit_status
        output = out.stdout_text
    if status == 0:
        err = "Found failures in %s dmesg log" % environ
        d_log = "dmesg log:\n%s" % output
        if dmesg_log_file:
            with open(dmesg_log_file, "w+") as log_f:
                log_f.write(d_log)
            err += " Please check %s dmesg log %s." % (environ, dmesg_log_file)
        else:
            err += " Please check %s dmesg log in debug log." % environ
            logging.debug(d_log)
        if session:
            session.cmd("dmesg -C")
        else:
            process.system("dmesg -C", ignore_status=True)
        if not ignore_result:
            raise exceptions.TestFail(err)
        return False
    return True


def add_ker_cmd(kernel_cmdline, kernel_param, remove_similar=False):
    """
    Add a parameter to kernel command line content

    :param kernel_cmdline: Original kernel command line.
    :type kernel_cmdline: string
    :param kernel_param: parameter want to change include the value.
    :type kernel_param: string
    :param remove_similar: remove the value of the parameter that already in
                           kernel cmd line or not.
    :type remove_similar: bool
    :return: kernel command line
    :rtype: string
    """
    kernel_param = kernel_param.strip()
    kernel_cmdline = kernel_cmdline.strip()
    kernel_cmdline_cmp = " %s " % kernel_cmdline
    need_update = True
    if " %s " % kernel_param in kernel_cmdline_cmp:
        logging.debug("Parameter already in kernel command line.")
        need_update = False
    elif "=" in kernel_param and remove_similar:
        kernel_param_key = kernel_param.split("=")[0]
        kernel_cmdline = re.sub(" %s= " % kernel_param_key, " ",
                                kernel_cmdline_cmp).strip()

    if need_update:
        kernel_cmdline += " %s" % kernel_param
    return kernel_cmdline


def rm_ker_cmd(kernel_cmdline, kernel_param):
    """
    Remove a parameter from kernel command line content

    :param kernel_cmdline: Original kernel command line.
    :type kernel_cmdline: string
    :param kernel_param: parameter want to change include the value.
    :type kernel_param: string
    :return: kernel command line
    :rtype: string
    """
    kernel_param = kernel_param.strip()
    kernel_cmdline = kernel_cmdline.strip()
    kernel_cmdline_cmp = " %s " % kernel_cmdline
    if " %s " % kernel_param in kernel_cmdline_cmp:
        kernel_cmdline = re.sub(" %s " % kernel_param, " ",
                                kernel_cmdline_cmp).strip()
    return kernel_cmdline


def get_ker_cmd():
    """
    Get the kernel cmdline.

    :return: Return the kernel cmdline.
    """
    return genio.read_file('/proc/cmdline')


def check_module(module_name, submodules=[]):
    """
    Check whether module and its submodules work.
    """
    module_info = linux_modules.loaded_module_info(module_name)
    logging.debug(module_info)
    # Return if module is not loaded.
    if not len(module_info):
        logging.debug("Module %s was not loaded.", module_name)
        return False

    module_work = True
    l_sub = module_info.get('submodules')
    for submodule in submodules:
        if submodule not in l_sub:
            logging.debug("Submodule %s of %s is not loaded.",
                          submodule, module_name)
            module_work = False
    return module_work


def get_pci_devices_in_group(str_flag=""):
    """
    Get PCI Devices. Classify pci devices accroding its bus
    and slot, devices with same bus and slot will be put together.
    The format will be {'domain:bus:slot': 'device_function',...}

    :param str_flag: the match string to filter devices.
    """
    d_lines = process.run("lspci -bDnn | grep \"%s\"" % str_flag,
                          shell=True).stdout_text

    devices = {}
    for line in d_lines.splitlines():
        pci_id = line.strip().split()[0]
        # It's a string with format: domain:bus:slot -> 0000:00:12
        pci_slot = pci_id.split('.')[0]
        # The function of pci device
        pci_function = pci_id.split('.')[1]
        pci_list = devices.get(pci_slot, [])
        pci_list.append(pci_id)
        devices[pci_slot] = pci_list
    return devices


def get_pci_group_by_id(pci_id, device_type=""):
    """
    Fit pci_id to a group list which has same domain:bus:slot.

    :param pci_id: pci id of a device:
                        domain:bus:slot.function or domain:bus:slot
                        even bus:slot
    :param device_type: string which can stand device
                        like 'Ethernet', 'Fibre'
    """
    if len(pci_id.split(':')) < 2:
        logging.error("Please provide formal pci id.")
        # Informal pci_id, no matched list
        return []
    devices = get_pci_devices_in_group(device_type)
    for device_key, device_value in list(devices.items()):
        for value in device_value:
            if value.count(pci_id):
                return devices[device_key]
    # No matched devices
    return []


def get_pci_vendor_device(pci_id):
    """
    Get vendor and device number by pci id.

    :return: a 'vendor device' list include all matched devices
    """
    matched_pci = process.run("lspci -n -s %s" % pci_id,
                              ignore_status=True).stdout_text
    pci_vd = []
    for line in matched_pci.splitlines():
        for string in line.split():
            vd = re.match("\w\w\w\w:\w\w\w\w", string)
            if vd is not None:
                pci_vd.append(vd.group(0))
                break
    return pci_vd


def get_pci_path(pci_id, session=None):
    """
    Get pci absolute path

    :param pci_id: pci id of a device
    :param session: The session object to the host
    :raise: test.fail when fail to get path
    :return: The absolute path of pci device
    """
    cmd = "find /sys/devices/pci* -name %s" % pci_id
    s_, pci_path = cmd_status_output(cmd, shell=True)
    if s_ or not pci_path.strip():
        raise exceptions.TestFail("unable to find full path for %s." % pci_id)
    return pci_path.strip()


def bind_device_driver(pci_id, driver_type):
    """
    Bind device driver.

    :param driver_type: Supported drivers: igb, lpfc, vfio-pci
    """
    vd_list = get_pci_vendor_device(pci_id)
    if len(vd_list) == 0:
        logging.error("Can't find device matched.")
        return False
    bind_file = "/sys/bus/pci/drivers/%s/new_id" % driver_type
    vendor = vd_list[0].split(':')[0]
    device = vd_list[0].split(':')[1]
    bind_cmd = "echo %s %s > %s" % (vendor, device, bind_file)
    return process.run(bind_cmd, ignore_status=True,
                       shell=True).exit_status == 0


def unbind_device_driver(pci_id):
    """
    Unbind device current driver.
    """
    vd_list = get_pci_vendor_device(pci_id)
    if len(vd_list) == 0:
        logging.error("Can't find device matched.")
        return False
    unbind_file = "/sys/bus/pci/devices/%s/driver/unbind" % pci_id
    unbind_cmd = "echo %s > %s" % (pci_id, unbind_file)
    return process.run(unbind_cmd, ignore_status=True,
                       shell=True).exit_status == 0


def check_device_driver(pci_id, driver_type):
    """
    Check whether device's driver is same as expected.
    """
    device_driver = "/sys/bus/pci/devices/%s/driver" % pci_id
    if not check_isdir(device_driver):
        logging.debug("Make sure %s has binded driver.")
        return False
    driver = process.run("readlink %s" % device_driver,
                         ignore_status=True).stdout_text.strip()
    driver = os.path.basename(driver)
    logging.debug("% is %s, expect %s", pci_id, driver, driver_type)
    return driver == driver_type


def get_bootloader_cfg(session=None):
    """
    Find bootloader cfg file path of guest or host.

    :param session: session of the vm needs to locate bootloader cfg file.
    :return: bootloader cfg file path, empty string if no cfg file found.
    """
    bootloader_cfg = [
        '/boot/grub/grub.conf',
        '/boot/grub2/grub.cfg',
        '/etc/grub.conf',
        '/etc/grub2.cfg',
        '/boot/etc/yaboot.conf',
        '/etc/default/grub'
    ]
    cfg_path = ''
    for path in bootloader_cfg:
        cmd = "test -f %s" % path
        if session:
            status = session.cmd_status(cmd)
        else:
            status = process.system(cmd)
        if not status:
            cfg_path = path
            break
    if not cfg_path:
        logging.error("Failed to locate bootloader config file "
                      "in %s." % bootloader_cfg)
    return cfg_path


class VFIOError(Exception):

    def __init__(self, err):
        Exception.__init__(self, err)
        self.error = err

    def __str__(self):
        return self.error


class VFIOController(object):

    """Control Virtual Function for testing"""

    def __init__(self, load_modules=True, allow_unsafe_interrupts=True):
        """
        Initalize prerequisites for enabling VFIO.

        """
        # Step1: Check whether kernel add parameter of iommu
        self.check_iommu()

        # Step2: Check whether modules have been probed
        # Necessary modules for vfio and their sublinux_modules.
        self.vfio_modules = {'vfio': [],
                             'vfio_pci': [],
                             'vfio_iommu_type1': []}
        # Used for checking modules
        modules_error = []
        for key, value in list(self.vfio_linux_modules.items()):
            if check_module(key, value):
                continue
            elif load_modules:
                try:
                    linux_modules.load_module(key)
                except process.CmdError as detail:
                    modules_error.append("Load module %s failed: %s"
                                         % (key, detail))
            else:
                modules_error.append("Module %s does not work." % key)
        if len(modules_error):
            raise VFIOError(str(modules_error))

        # Step3: Enable the interrupt remapping support
        lnk = "/sys/module/vfio_iommu_type1/parameters/allow_unsafe_interrupts"
        if allow_unsafe_interrupts:
            try:
                process.run("echo Y > %s" % lnk, shell=True)
            except process.CmdError as detail:
                raise VFIOError(str(detail))

    def check_iommu(self):
        """
        Check whether iommu group is available.
        """
        grub_file = "/etc/grub2.cfg"
        if process.run("ls %s" % grub_file, ignore_status=True).exit_status:
            grub_file = "/etc/grub.cfg"

        grub_content = process.run("cat %s" % grub_file).stdout_text
        for line in grub_content.splitlines():
            if re.search("vmlinuz.*intel_iommu=on", line):
                return
        raise VFIOError("Please add 'intel_iommu=on' to kernel and "
                        "reboot to effect it.")

    def get_pci_iommu_group_id(self, pci_id, device_type=""):
        """
        Get pci devices iommu group id
        """
        pci_group_devices = get_pci_group_by_id(pci_id, device_type)
        if len(pci_group_devices) == 0:
            raise exceptions.TestError("Can't find device in provided pci group: %s"
                                       % pci_id)
        readlink_cmd = ("readlink /sys/bus/pci/devices/%s/iommu_group"
                        % pci_group_devices[0])
        try:
            group_id = int(os.path.basename(process.run(readlink_cmd).stdout_text))
        except ValueError as detail:
            raise exceptions.TestError("Get iommu group id failed:%s" % detail)
        return group_id

    def get_iommu_group_devices(self, group_id):
        """
        Get all devices in one group by its id.
        """
        output = process.run("ls /sys/kernel/iommu_groups/%s/devices/" % group_id).stdout_text
        group_devices = []
        for line in output.splitlines():
            devices = line.split()
            group_devices += devices
        return group_devices

    def bind_device_to_iommu_group(self, pci_id):
        """
        Bind device to iommu group.
        """
        return bind_device_driver(pci_id, "vfio-pci")

    def add_device_to_iommu_group(self, pci_id):
        """
        Add one single device to iommu group.
        """
        unbind_device_driver(pci_id)
        if not self.bind_device_to_iommu_group(pci_id):
            logging.debug('Bind vfio driver for %s failed.', pci_id)
            return False
        if not check_device_driver(pci_id, "vfio-pci"):
            logging.debug("Awesome, driver does not match after binding.")
            return False
        return True

    def check_vfio_id(self, group_id):
        """
        Check whether given vfio group has been established.
        """
        return os.path.exists("/dev/vfio/%s" % group_id)


class SELinuxBoolean(object):

    """
    SELinuxBoolean class for managing SELinux boolean value.
    """

    def __init__(self, params):
        self.server_ip = params.get("server_ip", None)
        self.ssh_user = params.get("server_user", "root")
        self.ssh_cmd = "ssh %s@%s " % (self.ssh_user, self.server_ip)
        self.ssh_obj = None
        if self.server_ip:
            # Setup SSH connection
            from virttest.utils_conn import SSHConnection
            self.ssh_obj = SSHConnection(params)
            ssh_timeout = int(params.get("ssh_timeout", 10))
            self.ssh_obj.conn_setup(timeout=ssh_timeout)
            cmd = "%s'getenforce'" % self.ssh_cmd
            try:
                result = process.run(cmd, shell=True)
                self.rem_selinux_disabled = (result.stdout_text.strip().lower() ==
                                             "disabled")
            except process.CmdError:
                self.rem_selinux_disabled = True
        self.cleanup_local = True
        self.cleanup_remote = True
        self.set_bool_local = params.get("set_sebool_local", "no")
        self.set_bool_remote = params.get("set_sebool_remote", "no")
        self.local_bool_var = params.get("local_boolean_varible")
        self.remote_bool_var = params.get("remote_boolean_varible",
                                          self.local_bool_var)
        self.local_bool_value = params.get("local_boolean_value")
        self.remote_bool_value = params.get("remote_boolean_value",
                                            self.local_bool_value)
        # initialize original value as off, if not it will override in setup
        self.local_boolean_orig = "off"
        self.remote_boolean_orig = "off"
        try:
            self.selinux_disabled = utils_selinux.get_status() == "disabled"
        except (utils_selinux.SeCmdError, utils_selinux.SelinuxError):
            self.selinux_disabled = True

    def get_sebool_local(self):
        """
        Get SELinux boolean value from local host.
        """
        get_sebool_cmd = "getsebool %s | awk -F'-->' '{print $2}'" % (
            self.local_bool_var)
        logging.debug("The command: %s", get_sebool_cmd)
        result = process.run(get_sebool_cmd, shell=True)
        return result.stdout_text.strip()

    def get_sebool_remote(self):
        """
        Get SELinux boolean value from remote host.
        """
        get_sebool_cmd = "getsebool %s" % self.remote_bool_var
        cmd = (self.ssh_cmd + "'%s'" %
               (get_sebool_cmd + "'| awk -F'-->' '{print $2}''"))
        logging.debug("The command: %s", cmd)
        result = process.run(cmd, shell=True)
        return result.stdout_text.strip()

    def setup(self):
        """
        Set SELinux boolean value.
        """
        # Change SELinux boolean value on local host
        if self.set_bool_local == "yes" and not self.selinux_disabled:
            self.setup_local()
        else:
            self.cleanup_local = False

        # Change SELinux boolean value on remote host
        if self.set_bool_remote == "yes" and not self.rem_selinux_disabled:
            self.setup_remote()
        else:
            self.cleanup_remote = False

    def cleanup(self, keep_authorized_keys=False, auto_recover=False):
        """
        Cleanup SELinux boolean value.
        """

        # Recover local SELinux boolean value
        if self.cleanup_local and not self.selinux_disabled:
            result = process.run("setsebool %s %s" % (self.local_bool_var,
                                                      self.local_boolean_orig))
            if result.exit_status:
                raise exceptions.TestError(result.stderr_text.strip())

        # Recover remote SELinux boolean value
        if self.cleanup_remote and not self.rem_selinux_disabled:
            cmd = (self.ssh_cmd + "'setsebool %s %s'" %
                   (self.remote_bool_var, self.remote_boolean_orig))
            result = process.run(cmd)
            if result.exit_status:
                raise exceptions.TestError(result.stderr_text.strip())

        # Recover SSH connection
        if self.ssh_obj:
            self.ssh_obj.auto_recover = auto_recover
            if self.ssh_obj.auto_recover and not keep_authorized_keys:
                del self.ssh_obj

    def setup_local(self):
        """
        Set SELinux boolean value on the local
        """
        # Get original SELinux boolean value, nothing to do if it
        # equals to specified value
        self.local_boolean_orig = self.get_sebool_local()
        if self.local_bool_value == self.local_boolean_orig:
            self.cleanup_local = False
            return

        result = process.run("setsebool %s %s" % (self.local_bool_var,
                                                  self.local_bool_value))
        if result.exit_status:
            raise exceptions.TestSkipError(result.stderr_text.strip())

        boolean_curr = self.get_sebool_local()
        logging.debug("To check local boolean value: %s", boolean_curr)
        if boolean_curr != self.local_bool_value:
            raise exceptions.TestFail(result.stderr_text.strip())

    def setup_remote(self):
        """
        Set SELinux boolean value on remote host.
        """
        # Get original SELinux boolean value, nothing to do if it
        # equals to specified value
        self.remote_boolean_orig = self.get_sebool_remote()
        if self.remote_bool_value == self.remote_boolean_orig:
            self.cleanup_remote = False
            return

        set_boolean_cmd = (self.ssh_cmd + "'setsebool %s %s'" %
                           (self.remote_bool_var, self.remote_bool_value))

        result = process.run(set_boolean_cmd)
        if result.exit_status:
            raise exceptions.TestSkipError(result.stderr_text.strip())

        boolean_curr = self.get_sebool_remote()
        logging.debug("To check remote boolean value: %s", boolean_curr)
        if boolean_curr != self.remote_bool_value:
            raise exceptions.TestFail(result.stderr_text.strip())


class _NullStream(object):

    def write(self, data):
        pass

    def flush(self):
        pass


TEE_TO_LOGS = object()
_the_null_stream = _NullStream()

DEFAULT_STDOUT_LEVEL = logging.DEBUG
DEFAULT_STDERR_LEVEL = logging.ERROR

# prefixes for logging stdout/stderr of commands
STDOUT_PREFIX = '[stdout] '
STDERR_PREFIX = '[stderr] '


def get_stream_tee_file(stream, level, prefix=''):
    if stream is None:
        return _the_null_stream
    if stream is TEE_TO_LOGS:
        return logging_manager.LoggingFile(level=level, prefix=prefix)
    return stream


class BgJob(object):

    def __init__(self, command, stdout_tee=None, stderr_tee=None, verbose=True,
                 stdin=None, stderr_level=DEFAULT_STDERR_LEVEL,
                 close_fds=False):
        self.command = command
        self.stdout_tee = get_stream_tee_file(stdout_tee, DEFAULT_STDOUT_LEVEL,
                                              prefix=STDOUT_PREFIX)
        self.stderr_tee = get_stream_tee_file(stderr_tee, stderr_level,
                                              prefix=STDERR_PREFIX)
        self.result = CmdResult(command)

        # Allow for easy stdin input by string, we'll let subprocess create
        # a pipe for stdin input and we'll write to it in the wait loop
        if isinstance(stdin, basestring):
            self.string_stdin = stdin
            stdin = subprocess.PIPE
        else:
            self.string_stdin = None

        if verbose:
            logging.debug("Running '%s'" % command)
        # Ok, bash is nice and everything, but we might face occasions where
        # it is not available. Just do the right thing and point to /bin/sh.
        shell = '/bin/bash'
        if not os.path.isfile(shell):
            shell = '/bin/sh'
        self.sp = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   preexec_fn=self._reset_sigpipe,
                                   close_fds=close_fds,
                                   shell=True,
                                   executable=shell,
                                   stdin=stdin,
                                   universal_newlines=True)

    def output_prepare(self, stdout_file=None, stderr_file=None):
        self.stdout_file = stdout_file
        self.stderr_file = stderr_file

    def process_output(self, stdout=True, final_read=False):
        """output_prepare must be called prior to calling this"""
        if stdout:
            pipe, buf, tee = self.sp.stdout, self.stdout_file, self.stdout_tee
        else:
            pipe, buf, tee = self.sp.stderr, self.stderr_file, self.stderr_tee

        if final_read:
            # Read in all the data we can from pipe and then stop
            data = []
            while select.select([pipe], [], [], 0)[0]:
                data.append(os.read(pipe.fileno(), 1024))
                if len(data[-1]) == 0:
                    break
            data = b"".join(data)
        else:
            # Perform a single read
            data = os.read(pipe.fileno(), 1024)
        buf.write(data)
        tee.write(data)

    def cleanup(self):
        self.stdout_tee.flush()
        self.stderr_tee.flush()
        self.sp.stdout.close()
        self.sp.stderr.close()
        self.result.stdout = self.stdout_file.getvalue()
        self.result.stderr = self.stderr_file.getvalue()

    def _reset_sigpipe(self):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


class AsyncJob(BgJob):

    def __init__(self, command, stdout_tee=None, stderr_tee=None, verbose=True,
                 stdin=None, stderr_level=DEFAULT_STDERR_LEVEL, kill_func=None,
                 close_fds=False):
        super(AsyncJob, self).__init__(command, stdout_tee=stdout_tee,
                                       stderr_tee=stderr_tee, verbose=verbose, stdin=stdin,
                                       stderr_level=stderr_level, close_fds=close_fds)

        # Start time for CmdResult
        self.start_time = time.time()

        if kill_func is None:
            self.kill_func = self._kill_self_process
        else:
            self.kill_func = kill_func

        if self.string_stdin:
            self.stdin_lock = threading.Lock()
            string_stdin = self.string_stdin
            # Replace with None so that _wait_for_commands will not try to re-write it
            self.string_stdin = None
            self.stdin_thread = threading.Thread(target=AsyncJob._stdin_string_drainer, name=("%s-stdin" % command),
                                                 args=(string_stdin, self.sp.stdin))
            self.stdin_thread.daemon = True
            self.stdin_thread.start()

        self.stdout_lock = threading.Lock()
        self.stdout_file = BytesIO()
        self.stdout_thread = threading.Thread(target=AsyncJob._fd_drainer, name=("%s-stdout" % command),
                                              args=(self.sp.stdout, [self.stdout_file, self.stdout_tee],
                                                    self.stdout_lock))
        self.stdout_thread.daemon = True

        self.stderr_lock = threading.Lock()
        self.stderr_file = BytesIO()
        self.stderr_thread = threading.Thread(target=AsyncJob._fd_drainer, name=("%s-stderr" % command),
                                              args=(self.sp.stderr, [self.stderr_file, self.stderr_tee],
                                                    self.stderr_lock))
        self.stderr_thread.daemon = True

        self.stdout_thread.start()
        self.stderr_thread.start()

    @staticmethod
    def _stdin_string_drainer(input_string, stdin_pipe):
        """
        input is a string and output is PIPE
        """
        try:
            while True:
                # We can write PIPE_BUF bytes without blocking after a poll or
                # select we aren't doing either but let's write small chunks
                # anyway. POSIX requires PIPE_BUF is >= 512
                # 512 should be replaced with select.PIPE_BUF in Python 2.7+
                tmp = input_string[:512]
                if tmp == '':
                    break
                stdin_pipe.write(tmp)
                input_string = input_string[512:]
        finally:
            # Close reading PIPE so that the reader doesn't block
            stdin_pipe.close()

    @staticmethod
    def _fd_drainer(input_pipe, outputs, lock):
        """
        input is a pipe and output is file-like. if lock is non-None, then
        we assume output isn't thread-safe
        """
        # If we don't have a lock object, then call a noop function like bool
        acquire = getattr(lock, 'acquire', bool)
        release = getattr(lock, 'release', bool)
        writable_objs = [obj for obj in outputs if hasattr(obj, 'write')]
        fileno = input_pipe.fileno()
        while True:
            # 1024 because that's what we did before
            tmp = os.read(fileno, 1024)
            if tmp == '':
                break
            acquire()
            try:
                for f in writable_objs:
                    f.write(tmp)
            finally:
                release()
        # Don't close writeable_objs, the callee will close

    def output_prepare(self, stdout_file=None, stderr_file=None):
        raise NotImplementedError("This object automatically prepares its own "
                                  "output")

    def process_output(self, stdout=True, final_read=False):
        raise NotImplementedError("This object has background threads "
                                  "automatically polling the process. Use the "
                                  "locked accessors")

    def get_stdout(self):
        self.stdout_lock.acquire()
        tmp = self.stdout_file.getvalue()
        self.stdout_lock.release()
        return tmp

    def get_stderr(self):
        self.stderr_lock.acquire()
        tmp = self.stderr_file.getvalue()
        self.stderr_lock.release()
        return tmp

    def cleanup(self):
        raise NotImplementedError("This must be waited for to get a result")

    def _kill_self_process(self):
        try:
            os.kill(self.sp.pid, signal.SIGTERM)
        except OSError:
            pass  # don't care if the process is already gone

    def wait_for(self, timeout=None):
        """
        Wait for the process to finish. When timeout is provided, process is
        safely destroyed after timeout.
        :param timeout: Acceptable timeout
        :return: results of this command
        """
        if timeout is None:
            self.sp.wait()

        if timeout > 0:
            start_time = time.time()
            while time.time() - start_time < timeout:
                self.result.exit_status = self.sp.poll()
                if self.result.exit_status is not None:
                    break
        else:
            timeout = 1     # Increase the timeout to check if it really died
        # first need to kill the threads and process, then no more locking
        # issues for superclass's cleanup function
        self.kill_func()
        # Verify it was really killed with provided kill function
        stop_time = time.time() + timeout
        while time.time() < stop_time:
            self.result.exit_status = self.sp.poll()
            if self.result.exit_status is not None:
                break
        else:   # Process is immune against self.kill_func() use -9
            try:
                os.kill(self.sp.pid, signal.SIGKILL)
            except OSError:
                pass  # don't care if the process is already gone
        # We need to fill in parts of the result that aren't done automatically
        try:
            _, self.result.exit_status = os.waitpid(self.sp.pid, 0)
        except OSError:
            self.result.exit_status = self.sp.poll()
        self.result.duration = time.time() - self.start_time
        assert self.result.exit_status is not None

        # Make sure we've got stdout and stderr
        self.stdout_thread.join(1)
        self.stderr_thread.join(1)
        assert not self.stdout_thread.isAlive()
        assert not self.stderr_thread.isAlive()

        super(AsyncJob, self).cleanup()

        return self.result


def get_stderr_level(stderr_is_expected):
    if stderr_is_expected:
        return DEFAULT_STDOUT_LEVEL
    return DEFAULT_STDERR_LEVEL


def join_bg_jobs(bg_jobs, timeout=None):
    """Joins the bg_jobs with the current thread.

    Returns the same list of bg_jobs objects that was passed in.
    """
    ret, timeout_error = 0, False
    for bg_job in bg_jobs:
        bg_job.output_prepare(BytesIO(), BytesIO())

    try:
        # We are holding ends to stdin, stdout pipes
        # hence we need to be sure to close those fds no mater what
        start_time = time.time()
        timeout_error = _wait_for_commands(bg_jobs, start_time, timeout)

        for bg_job in bg_jobs:
            # Process stdout and stderr
            bg_job.process_output(stdout=True, final_read=True)
            bg_job.process_output(stdout=False, final_read=True)
    finally:
        # close our ends of the pipes to the sp no matter what
        for bg_job in bg_jobs:
            bg_job.cleanup()

    if timeout_error:
        # TODO: This needs to be fixed to better represent what happens when
        # running in parallel. However this is backwards compatible, so it will
        # do for the time being.
        raise process.CmdError(bg_jobs[0].command, bg_jobs[0].result,
                               "Command(s) did not complete within %d seconds"
                               % timeout)

    return bg_jobs


def run_parallel(commands, timeout=None, ignore_status=False,
                 stdout_tee=None, stderr_tee=None):
    """
    Behaves the same as run() with the following exceptions:

    - commands is a list of commands to run in parallel.
    - ignore_status toggles whether or not an exception should be raised
      on any error.

    :return: a list of CmdResult objects
    """
    bg_jobs = []
    for command in commands:
        bg_jobs.append(BgJob(command, stdout_tee, stderr_tee,
                             stderr_level=get_stderr_level(ignore_status)))

    # Updates objects in bg_jobs list with their process information
    join_bg_jobs(bg_jobs, timeout)

    for bg_job in bg_jobs:
        if not ignore_status and bg_job.result.exit_status:
            raise process.CmdError(command, bg_job.result,
                                   "Command returned non-zero exit status")

    return [bg_job.result for bg_job in bg_jobs]


def nuke_subprocess(subproc):
    # check if the subprocess is still alive, first
    if subproc.poll() is not None:
        return subproc.poll()

    # the process has not terminated within timeout,
    # kill it via an escalating series of signals.
    signal_queue = [signal.SIGTERM, signal.SIGKILL]
    for sig in signal_queue:
        signal_pid(subproc.pid, sig)
        if subproc.poll() is not None:
            return subproc.poll()


def _wait_for_commands(bg_jobs, start_time, timeout):
    # This returns True if it must return due to a timeout, otherwise False.

    # To check for processes which terminate without producing any output
    # a 1 second timeout is used in select.
    SELECT_TIMEOUT = 1

    read_list = []
    write_list = []
    reverse_dict = {}

    for bg_job in bg_jobs:
        read_list.append(bg_job.sp.stdout)
        read_list.append(bg_job.sp.stderr)
        reverse_dict[bg_job.sp.stdout] = (bg_job, True)
        reverse_dict[bg_job.sp.stderr] = (bg_job, False)
        if bg_job.string_stdin is not None:
            write_list.append(bg_job.sp.stdin)
            reverse_dict[bg_job.sp.stdin] = bg_job

    if timeout:
        stop_time = start_time + timeout
        time_left = stop_time - time.time()
    else:
        time_left = None  # so that select never times out

    while not timeout or time_left > 0:
        # select will return when we may write to stdin or when there is
        # stdout/stderr output we can read (including when it is
        # EOF, that is the process has terminated).
        read_ready, write_ready, _ = select.select(read_list, write_list, [],
                                                   SELECT_TIMEOUT)

        # os.read() has to be used instead of
        # subproc.stdout.read() which will otherwise block
        for file_obj in read_ready:
            bg_job, is_stdout = reverse_dict[file_obj]
            bg_job.process_output(is_stdout)

        for file_obj in write_ready:
            # we can write PIPE_BUF bytes without blocking
            # POSIX requires PIPE_BUF is >= 512
            bg_job = reverse_dict[file_obj]
            file_obj.write(bg_job.string_stdin[:512])
            bg_job.string_stdin = bg_job.string_stdin[512:]
            # no more input data, close stdin, remove it from the select set
            if not bg_job.string_stdin:
                file_obj.close()
                write_list.remove(file_obj)
                del reverse_dict[file_obj]

        all_jobs_finished = True
        for bg_job in bg_jobs:
            if bg_job.result.exit_status is not None:
                continue

            bg_job.result.exit_status = bg_job.sp.poll()
            if bg_job.result.exit_status is not None:
                # process exited, remove its stdout/stdin from the select set
                bg_job.result.duration = time.time() - start_time
                read_list.remove(bg_job.sp.stdout)
                read_list.remove(bg_job.sp.stderr)
                del reverse_dict[bg_job.sp.stdout]
                del reverse_dict[bg_job.sp.stderr]
            else:
                all_jobs_finished = False

        if all_jobs_finished:
            return False

        if timeout:
            time_left = stop_time - time.time()

    # Kill all processes which did not complete prior to timeout
    for bg_job in bg_jobs:
        if bg_job.result.exit_status is not None:
            continue

        logging.warn('run process timeout (%s) fired on: %s', timeout,
                     bg_job.command)
        nuke_subprocess(bg_job.sp)
        bg_job.result.exit_status = bg_job.sp.poll()
        bg_job.result.duration = time.time() - start_time

    return True


def get_pid(name, session=None):
    """
    Get pid by process name

    :param name: Name of the process/string in process cmdline to retrieve its pid
    :param session: ShellSession object of VM or remote host
    :return: Pid of the process or None in case of exceptions
    """
    cmd = "pgrep -f '%s'" % name
    status, output = cmd_status_output(cmd, shell=True, session=session)
    if status != 0:
        return None
    else:
        return int(output.split()[0])


def start_rsyslogd():
    """
    Start rsyslogd service
    """
    try:
        utils_path.find_command("rsyslogd")
    except utils_path.CmdNotFoundError:
        exceptions.TestError("No rsyslogd command found.")
    rsyslogd = service.Factory.create_service('rsyslog')
    if not rsyslogd.status():
        logging.info("Need to start rsyslog service")
        return rsyslogd.start()
    return True


def get_distro(session=None):
    """
    Get distribution name of the Host/Guest/Remote Host

    :param session: ShellSession object of VM or remote host
    :return: distribution name of type str
    """
    if not session:
        return distro.detect().name
    else:
        distro_name = ""
        cmd = "cat /etc/os-release | grep '^ID='"
        try:
            status, output = session.cmd_status_output(cmd, timeout=300)
            if status:
                logging.debug("Unable to get the distro name: %s" % output)
            else:
                distro_name = output.split('=')[1].strip()
        finally:
            return distro_name


def get_sosreport(path=None, session=None, remote_ip=None, remote_pwd=None,
                  remote_user="root", sosreport_name="", sosreport_pkg="sos",
                  timeout=1800, ignore_status=True):
    """
    Get sosreport in host/guest

    :param path: local host path for sosreport to be saved, defaults to logdir
    :param session: ShellSession object of VM or remote host
    :param remote_ip: remote host/guest ip address
    :param remote_pwd: remote host/guest password
    :param remote user: remote host/guest username
    :param sosreport_name: name to distinguish the sosreport of host/guest/remote
    :param sosreport_pkg: package name sos or sosreport depends on rhel or ubuntu
    :param timeout: duration to wait for sosreport to be taken are return prompt
    :param ignore_status: False, raise an exception True, to ignore

    :return: sosreport log path on success, None on fail
    """
    from aexpect import remote
    from avocado.core import data_dir
    from virttest import utils_package

    if "ubuntu" in get_distro(session=session).lower():
        sosreport_pkg = "sosreport"

    if not utils_package.package_install(sosreport_pkg, session=session):
        logging.error("Failed to install sos package")
        return None
    cmd = "sosreport --batch --all-logs"
    func = process.getstatusoutput
    host_path = path
    if not path:
        report_name = sosreport_name
        if not report_name:
            cmd = "hostname"
            if session:
                report_name = session.cmd_output(cmd)
            else:
                report_name = process.getoutput(cmd)
        path = host_path = get_path(get_log_file_dir(),
                                    "sosreport-%s" % report_name)
    if session:
        func = session.cmd_status_output
        path = "/tmp/sosreport"
        session.cmd("mkdir -p %s" % path)
    else:
        if check_isdir(path):
            os.remove(path)
        os.makedirs(path)
    cmd += " --tmp-dir %s" % path
    try:
        status, output = func(cmd, timeout=timeout)
        if status != 0:
            logging.error(output)
            return None
        if session:
            logging.info("copying sosreport from remote host/guest path: %s "
                         "to host path: %s", path, host_path)
            remote.copy_files_from(remote_ip, 'scp', remote_user, remote_pwd, "22",
                                   path, host_path, directory=True)
    except Exception as info:
        if ignore_status:
            logging.error(info)
        else:
            raise exceptions.TestError(info)
    finally:
        if session:
            session.close()
        return host_path


def asterisk_passwd(passwd):
    """
    Proctect plain password to be printed in log files

    In order to debug, Keep the 1st and last charactor.

    :param passwd: a password string
    :return: a string replaced with asterisk
    """
    if not passwd:
        return '*' * 8
    return passwd[0] + '*' * 6 + passwd[-1]


def compare_md5(file_a, file_b):
    """
    Compare two file's md5, return True if they are same.

    :param file_a: a file
    :param file_b: a file
    """
    def _md5(fd):
        m = md5()
        buf = fd.read()
        m.update(buf)
        return m.hexdigest()

    if not os.path.exists(file_a) or not os.path.exists(file_b):
        return False

    with open(file_a, 'rb') as fd_a, open(file_b, 'rb') as fd_b:
        if _md5(fd_a) == _md5(fd_b):
            return True
    return False
