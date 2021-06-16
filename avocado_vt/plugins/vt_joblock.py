import errno
import logging
import os
import re
import random
import string
import sys

from avocado.core import exit_codes
from avocado.utils.process import pid_exists
from avocado.utils.stacktrace import log_exc_info

from avocado.core.plugin_interfaces import JobPreTests as Pre
from avocado.core.plugin_interfaces import JobPostTests as Post

from ..test import VirtTest

from virttest.compat import get_settings_value

from six.moves import xrange


class LockCreationError(Exception):

    """
    Represents any error situation when attempting to create a lock file
    """
    pass


class OtherProcessHoldsLockError(Exception):

    """
    Represents a condition where other process has the lock
    """


class VTJobLock(Pre, Post):

    name = 'vt-joblock'
    description = 'Avocado-VT Job Lock/Unlock'

    def __init__(self, **kwargs):
        self.log = logging.getLogger("avocado.app")
        lock_dir = get_settings_value("plugins.vtjoblock", "dir",
                                      key_type=str, default='/tmp')
        self.lock_dir = os.path.expanduser(lock_dir)
        self.lock_file = None

    def _create_self_lock_file(self, job):
        """
        Creates the lock file for this job process

        :param job: the currently running job
        :type job: :class:`avocado.core.job.Job`
        :raises: :class:`LockCreationError`
        :returns: the full path for the lock file created
        :rtype: str
        """
        pattern = 'avocado-vt-joblock-%(jobid)s-%(uid)s-%(random)s.pid'
        # the job unique id is already random, but, let's add yet another one
        rand = ''.join([random.choice(string.ascii_lowercase + string.digits)
                        for i in xrange(8)])
        path = pattern % {'jobid': job.unique_id,
                          'uid': os.getuid(),
                          'random': rand}
        path = os.path.join(self.lock_dir, path)

        try:
            with open(path, 'w') as lockfile:
                lockfile.write("%u" % os.getpid())
            return path
        except Exception as e:
            raise LockCreationError(e)

    def _get_lock_files(self):
        """
        Get the list of lock file names under the current lock dir

        :returns: a list with the full path of files that match the
                  lockfile pattern
        :rtype: list
        """
        try:
            files = os.listdir(self.lock_dir)
            pattern = re.compile(r'avocado-vt-joblock-[0-9a-f]{40}-[0-9]+'
                                 '-[0-9a-z]{8}\.pid')
            return [os.path.join(self.lock_dir, _) for _ in files
                    if pattern.match(_)]
        except OSError as e:
            if e.errno == errno.ENOENT:
                return []

    def _lock(self, job):
        self.lock_file = self._create_self_lock_file(job)
        lock_files = self._get_lock_files()
        lock_files.remove(self.lock_file)
        for path in lock_files:
            try:
                lock_pid = int(open(path, 'r').read())
            except Exception:
                msg = 'Cannot read PID from "%s".' % path
                raise LockCreationError(msg)
            else:
                if pid_exists(lock_pid):
                    msg = 'File "%s" acquired by PID %u. ' % (path, lock_pid)
                    raise OtherProcessHoldsLockError(msg)
                else:
                    try:
                        os.unlink(path)
                    except OSError:
                        self.log.warn("Unable to remove stale lock: %s", path)

    @staticmethod
    def _get_klass_or_none(test_factory):
        try:
            return test_factory[0]
        except TypeError:
            return None

    def pre_tests(self, job):
        try:
            if job.test_suite is not None:
                if hasattr(job.test_suite, 'tests'):
                    tests = job.test_suite.tests
                else:
                    tests = job.test_suite
                if any(self._get_klass_or_none(test_factory) is VirtTest
                       for test_factory in tests):
                    self._lock(job)
        except Exception as detail:
            msg = "Failure trying to set Avocado-VT job lock: %s" % detail
            self.log.error(msg)
            log_exc_info(sys.exc_info(), self.log.name)
            sys.exit(exit_codes.AVOCADO_JOB_FAIL | job.exitcode)

    def post_tests(self, job):
        if self.lock_file is not None:
            os.unlink(self.lock_file)
