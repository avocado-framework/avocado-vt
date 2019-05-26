#!/usr/bin/python

import os
import tempfile
import unittest
import sys
import threading
import time

from avocado.utils import process


# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, 'virttest')):
    sys.path.append(basedir)

from virttest.unittest_utils import mock
from virttest import utils_misc
from virttest import cartesian_config
from virttest import build_helper


class TestUtilsMisc(unittest.TestCase):

    def test_cpu_vendor_intel(self):
        cpu_info = """processor : 0
vendor_id       : GenuineIntel
cpu family      : 6
model           : 58
model name      : Intel(R) Core(TM) i7-3770 CPU @ 3.40GHz
"""
        vendor = utils_misc.get_cpu_vendor(cpu_info, False)
        self.assertEqual(vendor, 'GenuineIntel')

    def test_cpu_vendor_amd(self):
        cpu_info = """processor : 3
vendor_id       : AuthenticAMD
cpu family      : 21
model           : 16
model name      : AMD A10-5800K APU with Radeon(tm) HD Graphics
"""
        vendor = utils_misc.get_cpu_vendor(cpu_info, False)
        self.assertEqual(vendor, 'AuthenticAMD')

    def test_vendor_unknown(self):
        cpu_info = "this is an unknown cpu"
        vendor = utils_misc.get_cpu_vendor(cpu_info, False)
        self.assertEqual(vendor, 'unknown')

    def test_get_archive_tarball_name(self):
        tarball_name = utils_misc.get_archive_tarball_name('/tmp',
                                                           'tmp-archive',
                                                           'bz2')
        self.assertEqual(tarball_name, 'tmp-archive.tar.bz2')

    def test_get_archive_tarball_name_absolute(self):
        tarball_name = utils_misc.get_archive_tarball_name('/tmp',
                                                           '/var/tmp/tmp',
                                                           'bz2')
        self.assertEqual(tarball_name, '/var/tmp/tmp.tar.bz2')

    def test_get_archive_tarball_name_from_dir(self):
        tarball_name = utils_misc.get_archive_tarball_name('/tmp',
                                                           None,
                                                           'bz2')
        self.assertEqual(tarball_name, 'tmp.tar.bz2')

    def test_git_repo_param_helper(self):
        config = """git_repo_foo_uri = git://git.foo.org/foo.git
git_repo_foo_branch = next
git_repo_foo_lbranch = local
git_repo_foo_commit = bc732ad8b2ed8be52160b893735417b43a1e91a8
"""
        config_parser = cartesian_config.Parser()
        config_parser.parse_string(config)
        params = next(config_parser.get_dicts())

        h = build_helper.GitRepoParamHelper(params, 'foo', '/tmp/foo')
        self.assertEqual(h.name, 'foo')
        self.assertEqual(h.branch, 'next')
        self.assertEqual(h.lbranch, 'local')
        self.assertEqual(h.commit, 'bc732ad8b2ed8be52160b893735417b43a1e91a8')

    def test_normalize_data_size(self):
        n1 = utils_misc.normalize_data_size("12M")
        n2 = utils_misc.normalize_data_size("1024M", "G")
        n3 = utils_misc.normalize_data_size("1024M", "T")
        n4 = utils_misc.normalize_data_size("1000M", "G", 1000)
        n5 = utils_misc.normalize_data_size("1T", "G", 1000)
        n6 = utils_misc.normalize_data_size("1T", "M")
        self.assertEqual(n1, "12.0")
        self.assertEqual(n2, "1.0")
        self.assertEqual(n3, "0.0009765625")
        self.assertEqual(n4, "1.0")
        self.assertEqual(n5, "1000.0")
        self.assertEqual(n6, "1048576.0")


class FakeCmd(object):

    def __init__(self, cmd):
        self.fake_cmds = [
            {"cmd": "numactl --hardware",
             "stdout": """
available: 1 nodes (0)
node 0 cpus: 0 1 2 3 4 5 6 7
node 0 size: 18431 MB
node 0 free: 17186 MB
node distances:
node   0
  0:  10
"""},
            {"cmd": "ps -eLf | awk '{print $4}'",
             "stdout": """
1230
1231
1232
1233
1234
1235
1236
1237
"""},
            {"cmd": "taskset -cp 0 1230", "stdout": ""},
            {"cmd": "taskset -cp 1 1231", "stdout": ""},
            {"cmd": "taskset -cp 2 1232", "stdout": ""},
            {"cmd": "taskset -cp 3 1233", "stdout": ""},
            {"cmd": "taskset -cp 4 1234", "stdout": ""},
            {"cmd": "taskset -cp 5 1235", "stdout": ""},
            {"cmd": "taskset -cp 6 1236", "stdout": ""},
            {"cmd": "taskset -cp 7 1237", "stdout": ""},

        ]

        self.stdout = self.get_stdout(cmd)

    def get_stdout(self, cmd):
        for fake_cmd in self.fake_cmds:
            if fake_cmd['cmd'] == cmd:
                return fake_cmd['stdout']
        raise ValueError("Could not locate locate '%s' on fake cmd db" % cmd)


def utils_run(cmd, shell=True):
    return FakeCmd(cmd)


all_nodes_contents = "0\n"
online_nodes_contents = "0\n"


class TestNumaNode(unittest.TestCase):

    def setUp(self):
        self.god = mock.mock_god(ut=self)
        self.god.stub_with(process, 'run', utils_run)
        all_nodes = tempfile.NamedTemporaryFile(delete=False)
        all_nodes.write(all_nodes_contents)
        all_nodes.close()
        online_nodes = tempfile.NamedTemporaryFile(delete=False)
        online_nodes.write(online_nodes_contents)
        online_nodes.close()
        self.all_nodes_path = all_nodes.name
        self.online_nodes_path = online_nodes.name
        self.numa_node = utils_misc.NumaNode(-1,
                                             self.all_nodes_path,
                                             self.online_nodes_path)

    def test_get_node_cpus(self):
        self.assertEqual(self.numa_node.get_node_cpus(0), '0 1 2 3 4 5 6 7')

    def test_pin_cpu(self):
        self.assertEqual(self.numa_node.pin_cpu("1230"), "0")
        self.assertEqual(self.numa_node.dict["0"], ["1230"])

        self.assertEqual(self.numa_node.pin_cpu("1231"), "1")
        self.assertEqual(self.numa_node.dict["1"], ["1231"])

        self.assertEqual(self.numa_node.pin_cpu("1232"), "2")
        self.assertEqual(self.numa_node.dict["2"], ["1232"])

        self.assertEqual(self.numa_node.pin_cpu("1233"), "3")
        self.assertEqual(self.numa_node.dict["3"], ["1233"])

        self.assertEqual(self.numa_node.pin_cpu("1234"), "4")
        self.assertEqual(self.numa_node.dict["4"], ["1234"])

        self.assertEqual(self.numa_node.pin_cpu("1235"), "5")
        self.assertEqual(self.numa_node.dict["5"], ["1235"])

        self.assertEqual(self.numa_node.pin_cpu("1236"), "6")
        self.assertEqual(self.numa_node.dict["6"], ["1236"])

        self.assertEqual(self.numa_node.pin_cpu("1237"), "7")
        self.assertEqual(self.numa_node.dict["7"], ["1237"])

        self.assertTrue("free" not in list(self.numa_node.dict.values()))

    def test_free_cpu(self):
        self.assertEqual(self.numa_node.pin_cpu("1230"), "0")
        self.assertEqual(self.numa_node.dict["0"], ["1230"])

        self.assertEqual(self.numa_node.pin_cpu("1231"), "1")
        self.assertEqual(self.numa_node.dict["1"], ["1231"])

        self.numa_node.free_cpu("0")
        self.assertEqual(self.numa_node.dict["0"], [])
        self.assertEqual(self.numa_node.dict["1"], ["1231"])

    def test_bitlist_to_string(self):
        string = 'foo'
        bitlist = [0, 1, 1, 0, 0, 1, 1, 0, 0, 1,
                   1, 0, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1]
        self.assertEqual(utils_misc.string_to_bitlist(string), bitlist)

    def test_string_to_bitlist(self):
        bitlist = [0, 1, 1, 0, 0, 0, 1, 0, 0, 1,
                   1, 0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0]
        string = 'bar'
        self.assertEqual(utils_misc.bitlist_to_string(bitlist), string)

    def tearDown(self):
        self.god.unstub_all()
        os.unlink(self.all_nodes_path)
        os.unlink(self.online_nodes_path)


class TimeoutLockTest(unittest.TestCase):

    def setUp(self):
        self.exit_event = threading.Event()
        self.thread = None

    def _start_thread(self, f, wait_before_exit=False):
        """Start a thread with target f."""
        def task():
            try:
                f()
            finally:
                self.exit_event.wait()

        if wait_before_exit:
            self.exit_event.clear()
        else:
            self.exit_event.set()
        self.thread = threading.Thread(target=task)
        self.thread.start()

    def _wait_for_thread_finish(self):
        self.exit_event.set()
        self.thread.join()

    def test_reacquire(self):
        lock = utils_misc.TimeoutLock()
        lock.acquire()
        lock.acquire()
        lock.release()
        lock.acquire()
        lock.release()
        lock.release()

    def test_release_unacquired(self):
        lock = utils_misc.TimeoutLock()
        self.assertRaises(RuntimeError, lock.release)
        lock.acquire()
        lock.acquire()
        lock.release()
        lock.acquire()
        lock.release()
        lock.release()
        self.assertRaises(RuntimeError, lock.release)

    def test_timeout(self):
        def f():
            t1 = time.time()
            results.append(lock.acquire(timeout=0.5))
            t2 = time.time()
            results.append(t2 - t1)

        lock = utils_misc.TimeoutLock()
        lock.acquire()
        results = []
        self._start_thread(f)
        self._wait_for_thread_finish()
        self.assertFalse(results[0])
        self.assertTrue(results[1] >= 0.5)

    def test_acquire_during_timeout(self):
        def f():
            t1 = time.time()
            results.append(lock.acquire(timeout=20))
            t2 = time.time()
            results.append(t2 - t1)

        lock = utils_misc.TimeoutLock()
        lock.acquire()
        results = []
        self._start_thread(f)
        lock.release()
        self._wait_for_thread_finish()
        self.assertTrue(results[0])
        self.assertTrue(results[1] <= 20)

    def tearDown(self):
        if self.thread:
            self._wait_for_thread_finish()


if __name__ == '__main__':
    unittest.main()
