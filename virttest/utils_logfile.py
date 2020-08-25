"""
Control log file utility functions.
An easy way to log lines to files when the logging system can't be used

:copyright: 2020 Red Hat Inc.
"""
import os
import time
import threading

from avocado.utils import aurl
from avocado.utils import path as utils_path
from aexpect.utils.genio import _open_log_files
from avocado.utils.astring import string_safe_encode

from virttest import data_dir


_log_file_dir = data_dir.get_tmp_dir()
_log_lock = threading.RLock()


def _acquire_lock(lock, timeout=10):
    """
    Check if the lock is available

    :param lock: threading.RLock object
    :param timeout: time to Wait for the lock

    :return: boolean. True if the lock is available
                      False if the lock is unavailable
    """
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
    :raise LogLockError: If the lock is unavailable
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
    Set the base directory for log files created by log_line()

    :param directory: Directory for log files
    """
    global _log_file_dir
    _log_file_dir = directory


def get_log_file_dir():
    """
    Get the base directory for log files created by log_line()
    """
    global _log_file_dir
    return _log_file_dir


def get_log_filename(filename):
    """
    Return full path of log file name

    :param filename: Log file name
    :return: str. The full path of the log file
    """
    if aurl.is_url(filename):
        return filename
    return os.path.realpath(
            os.path.abspath(utils_path.get_path(_log_file_dir, filename)))


def close_log_file(filename):
    """
    Close the log file

    :param filename: Log file name
    :raise: LogLockError if the lock is unavailable
    """
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
