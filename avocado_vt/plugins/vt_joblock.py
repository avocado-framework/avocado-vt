import errno
import logging
import os
import re
import random
import string
import sys

from avocado.core import exit_codes
from avocado.core.settings import settings

# Avocado's plugin interface module has changed location. Let's keep
# compatibility with old for at, least, a new LTS release
try:
    from avocado.core.plugin_interfaces import JobPre, JobPost
except ImportError:
    from avocado.plugins.base import JobPre, JobPost

from ..test import VirtTest


class LockCreationError(Exception):

    """
    Represents any error situation when attempting to create a lock file
    """
    pass


class VTJobLock(JobPre, JobPost):

    name = 'vt-joblock'
    description = 'Avocado-VT Job Lock/Unlock'

    def __init__(self):
        self.log = logging.getLogger("avocado.app")
        self.lock_dir = os.path.expanduser(settings.get_value(
            section="plugins.vtjoblock",
            key="dir",
            key_type=str,
            default='/tmp'))
        self.lock_file = None

    def _abort(self, message, job):
        """
        Aborts the Job by exiting Avocado, adding a failure to the job status
        """
        self.log.error(message)
        sys.exit(exit_codes.AVOCADO_JOB_FAIL | job.exitcode)

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

    def _get_lock_file_pid(self):
        """
        Gets the lock file path and the process ID

        If the lock file can not be located, this returns (None, 0).

        :returns: the path and the (integer) process id
        :rtype: tuple(str, int)
        """
        files = self._get_lock_files()
        if not files:
            return (None, 0)
        path = files[0]
        content = int(open(path, 'r').read())
        pid = int(content)
        if pid > 0:
            return (path, pid)

    def _lock(self, job):
        filename, lock_pid = self._get_lock_file_pid()
        if lock_pid > 0:
            msg = ('Avocado-VT job lock file "%s" acquired by PID %u. '
                   'Aborting...' % (filename, lock_pid))
            self._abort(msg, job)
        self.lock_file = self._create_self_lock_file(job)

    def _unlock(self):
        if self.lock_file:
            os.unlink(self.lock_file)

    def pre(self, job):
        try:
            if any(test_factory[0] is VirtTest
                   for test_factory in job.test_suite):
                self._lock(job)
        except Exception as detail:
            msg = "Failure trying to set Avocado-VT job lock: %s" % detail
            self._abort(msg, job)

    def post(self, job):
        if self.lock_file is not None:
            self._unlock()
