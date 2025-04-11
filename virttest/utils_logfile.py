"""
Control log file utility functions.

An easy way to log lines to files when the logging system can't be used.

Naive module that keeps tacks of some opened files and somehow manages them.

:copyright: 2020 Red Hat Inc.
"""

import logging
import os
import re
import threading
import time

from avocado.core import exceptions
from avocado.utils import aurl
from avocado.utils import path as utils_path
from avocado.utils.astring import string_safe_encode

from virttest import data_dir

LOG = logging.getLogger("avocado." + __name__)

_log_file_dir = data_dir.get_tmp_dir()
_log_lock = threading.RLock()

# File descriptor dictionary for all open log files
_open_log_files = {}  # pylint: disable=C0103


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
        raise LogLockError(
            "Could not acquire exclusive lock to access" " _open_log_files"
        )
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
            _open_log_files[base_file] = open(log_file, "a")
        timestr = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            line = string_safe_encode(line)
        except UnicodeDecodeError:
            line = line.decode("utf-8", "ignore").encode("utf-8")
        _open_log_files[base_file].write("%s: %s\n" % (timestr, line))
        _open_log_files[base_file].flush()
    finally:
        _log_lock.release()


def get_match_count(file_path, key_message, encoding="ISO-8859-1"):
    """
    Get expected messages count in path

    :param file_path: file path to be checked
    :param key_message: key message that needs to be captured
    :param encoding: encoding method ,default 'ISO-8859-1'
    :return count: the count of key message
    """
    count = 0
    try:
        with open(file_path, "r", encoding=encoding) as fp:
            for line in fp.readlines():
                if re.findall(key_message, line):
                    count += 1
                    LOG.debug(
                        "Get '%s' in %s %s times" % (key_message, file_path, str(count))
                    )
    except IOError as details:
        raise exceptions.TestError(
            "Fail to read :%s and get error: %s" % (file_path, details)
        )
    return count


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
        os.path.abspath(utils_path.get_path(_log_file_dir, filename))
    )


def close_log_file(filename="*"):
    """
    Close log files with the same base name as filename or all by default.

    :param filename: Log file name
    :raise: LogLockError if the lock is unavailable
    """
    global _open_log_files, _log_file_dir, _log_lock
    remove = []
    if not _acquire_lock(_log_lock):
        raise LogLockError(
            "Could not acquire exclusive lock to access" " _open_log_files"
        )
    try:
        for log_file, log_fd in _open_log_files.items():
            if filename == "*" or os.path.basename(log_file) == os.path.basename(
                filename
            ):
                log_fd.close()
                remove.append(log_file)
        if remove:
            for key_to_remove in remove:
                _open_log_files.pop(key_to_remove)

    finally:
        _log_lock.release()


def close_own_log_file(log_file):
    """Closing hook for sessions with log_file managed locally."""

    def hook(self):
        close_log_file(log_file)

    return hook
