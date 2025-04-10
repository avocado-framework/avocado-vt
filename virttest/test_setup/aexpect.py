import aexpect

from virttest.test_setup.core import Setuper


class KillTailThreads(Setuper):
    def setup(self):
        pass

    def cleanup(self):
        # Kill all aexpect tail threads
        aexpect.kill_tail_threads()
