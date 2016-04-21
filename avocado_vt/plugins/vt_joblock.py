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

from ..test import VirtTest


class VTJobLock(JobPre, JobPost):

    name = 'vt-joblock'
    description = 'Avocado-VT Job Lock/Unlock'

    def __init__(self):
        self.log = logging.getLogger("avocado.app")
        self.has_vt_test = False
        self.lock_dir = settings.get_value(section="plugins.vtjoblock",
                                           key="dir",
                                           key_type=str,
                                           default='/tmp')
        self.show_lock = settings.get_value(section="plugins.vtjoblock",
                                            key="show_lock_location",
                                            key_type=bool,
                                            default=False)
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
            msg = ('Failed to create VT Job lock file. Exiting...')
            self._abort(msg, job)

        if self.show_lock:
            self.log.info("VT LOCK    : %s", self.lock_file)

    def _get_lock_file(self):
        if not os.path.isdir(self.lock_dir):
            return None

        try:
            files = os.listdir(self.lock_dir)
            if not files:
                return None
        except OSError as e:
            if e.errno == errno.ENOENT:
                return None

        pattern = re.compile(r'avocado-vt-joblock-[0-9a-f]{40}-[0-9]+'
                             '-[0-9a-z]{8}\.pid')
        for lock_file in files:
            if pattern.match(lock_file):
                path = os.path.join(self.lock_dir, lock_file)
                if os.path.isfile(path):
                    content = int(open(path, 'r').read())
                    if int(content) > 0:
                        return path
        return None

    def _get_lock_pid(self):
        lockfile = self._get_lock_file()
        if lockfile is None:
            return 0
        return int(open(lockfile, 'r').read())

    def _lock(self, job):
        lock_pid = self._get_lock_pid()
        if lock_pid > 0:
            msg = ("Avocado-VT job lock acquired by PID %u. "
                   "Aborting..." % lock_pid)
            self._abort(msg, job)
        self._set_lock(job)

    def _unlock(self):
        if self.lock_file:
            os.unlink(self.lock_file)

    def pre(self, job):
        self.has_vt_test = any(test_factory[0] is VirtTest
                               for test_factory in job.test_suite)

        if not self.has_vt_test:
            return
        self._lock(job)

    def post(self, job):
        if not self.has_vt_test:
            return
        self._unlock()
