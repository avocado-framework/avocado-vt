import errno
import logging
import os
import re
import random
import string
import sys

from avocado.core import exit_codes
from avocado.core.settings import settings
from avocado.plugins.base import JobPre, JobPost
from avocado.utils.process import pid_exists

from ..test import VirtTest


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

    def _set_lock(self, job):
        if not os.path.isdir(self.lock_dir):
            msg = ('VT Job lock directory "%s" does not exist... '
                   'exiting...' % self.lock_dir)
            self._abort(msg, job)

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
            self.lock_file = path
        except IOError as e:
            msg = ('Failed to create VT Job lock file "%s". Exiting...' % path)
            self._abort(msg, job)

    def _get_lock_file_pid(self):
        """
        Gets the lock file path and the process ID

        If the lock file can not be located, this returns (None, 0).

        :returns: the path and the (integer) process id
        :rtype: tuple(str, int)
        """
        try:
            files = os.listdir(self.lock_dir)
            if not files:
                return (None, 0)
        except OSError as e:
            if e.errno == errno.ENOENT:
                return (None, 0)

        pattern = re.compile(r'avocado-vt-joblock-[0-9a-f]{40}-[0-9]+'
                             '-[0-9a-z]{8}\.pid')
        for lock_file in files:
            if pattern.match(lock_file):
                path = os.path.join(self.lock_dir, lock_file)
                if os.path.isfile(path):
                    content = int(open(path, 'r').read())
                    pid = int(content)
                    if pid > 0:
                        return (path, pid)
        return (None, 0)

    def _lock(self, job):
        filename, lock_pid = self._get_lock_file_pid()
        if lock_pid > 0:
            if not pid_exists(lock_pid):
                self.log.error('Ignoring Avocado-VT job lock file "%s" because'
                               ' PID %u does not exist... Please clean it up to'
                               ' avoid this message.', filename, lock_pid)
            else:
                msg = ('Avocado-VT job lock file "%s" acquired by PID %u. '
                       'Aborting...' % (filename, lock_pid))
                self._abort(msg, job)
        self._set_lock(job)

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
