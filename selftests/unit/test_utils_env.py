#!/usr/bin/python
import unittest
import time
import logging
import os
import threading
import sys

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, 'virttest')):
    sys.path.append(basedir)

from virttest import utils_env
from virttest import utils_params
from virttest import utils_misc


class FakeVm(object):

    def __init__(self, vm_name, params):
        self.name = vm_name
        self.params = params
        self.vm_type = self.params.get('vm_type')
        self.driver_type = self.params.get('driver_type')
        self.instance = ("%s-%s" % (
            time.strftime("%Y%m%d-%H%M%S"),
            utils_misc.generate_random_string(16)))

    def get_params(self):
        return self.params

    def is_alive(self):
        logging.info("Fake VM %s (instance %s)", self.name, self.instance)


class FakeSyncListenServer(object):

    def __init__(self, address='', port=123, tmpdir=None):
        self.instance = ("%s-%s" % (
            time.strftime("%Y%m%d-%H%M%S"),
            utils_misc.generate_random_string(16)))
        self.port = port

    def close(self):
        logging.info("Closing sync server (instance %s)", self.instance)


class TestEnv(unittest.TestCase):

    def setUp(self):
        self.envfilename = "/dev/shm/EnvUnittest" + self.id()

    def test_register_vm(self):
        """
        1) Create an env object.
        2) Create a VM and register it from env.
        3) Get the vm back from the env.
        4) Verify that the 2 objects are the same.
        """
        env = utils_env.Env(filename=self.envfilename)
        params = utils_params.Params({"main_vm": 'rhel7-migration'})
        vm1 = FakeVm(params['main_vm'], params)
        vm1.is_alive()
        env.register_vm(params['main_vm'], vm1)
        vm2 = env.get_vm(params['main_vm'])
        vm2.is_alive()
        assert vm1 == vm2

    def test_unregister_vm(self):
        """
        1) Create an env object.
        2) Register 2 vms to the env.
        3) Verify both vms are in the env.
        4) Remove one of those vms.
        5) Verify that the removed vm is no longer in env.
        """
        env = utils_env.Env(filename=self.envfilename)
        params = utils_params.Params({"main_vm": 'rhel7-migration'})
        vm1 = FakeVm(params['main_vm'], params)
        vm1.is_alive()
        vm2 = FakeVm('vm2', params)
        vm2.is_alive()
        env.register_vm(params['main_vm'], vm1)
        env.register_vm('vm2', vm2)
        assert vm1 in env.get_all_vms()
        assert vm2 in env.get_all_vms()
        env.unregister_vm('vm2')
        assert vm1 in env.get_all_vms()
        assert vm2 not in env.get_all_vms()

    def test_get_all_vms(self):
        """
        1) Create an env object.
        2) Create 2 vms and register them in the env.
        3) Create a SyncListenServer and register it in the env.
        4) Verify that the 2 vms are in the output of get_all_vms.
        5) Verify that the sync server is not in the output of get_all_vms.
        """
        env = utils_env.Env(filename=self.envfilename)
        params = utils_params.Params({"main_vm": 'rhel7-migration'})
        vm1 = FakeVm(params['main_vm'], params)
        vm1.is_alive()
        vm2 = FakeVm('vm2', params)
        vm2.is_alive()
        env.register_vm(params['main_vm'], vm1)
        env.register_vm('vm2', vm2)
        sync1 = FakeSyncListenServer(port=333)
        env.register_syncserver(333, sync1)
        assert vm1 in env.get_all_vms()
        assert vm2 in env.get_all_vms()
        assert sync1 not in env.get_all_vms()

    def test_register_syncserver(self):
        """
        1) Create an env file.
        2) Create a SyncListenServer object and register it in the env.
        3) Get that SyncListenServer with get_syncserver.
        4) Verify that both objects are the same.
        """
        env = utils_env.Env(filename=self.envfilename)
        sync1 = FakeSyncListenServer(port=333)
        env.register_syncserver(333, sync1)
        sync2 = env.get_syncserver(333)
        assert sync1 == sync2

    def test_unregister_syncserver(self):
        """
        Unregister a sync server.

        1) Create an env file.
        2) Create and register 2 SyncListenServers in the env.
        3) Get one of the SyncListenServers in the env.
        4) Unregister one of the SyncListenServers.
        5) Verify that the SyncListenServer unregistered can't be retrieved
           anymore with ``get_syncserver()``.

        """
        env = utils_env.Env(filename=self.envfilename)
        sync1 = FakeSyncListenServer(port=333)
        env.register_syncserver(333, sync1)
        sync2 = FakeSyncListenServer(port=444)
        env.register_syncserver(444, sync2)
        sync3 = env.get_syncserver(333)
        assert sync1 == sync3
        env.unregister_syncserver(444)
        sync4 = env.get_syncserver(444)
        assert sync4 is None

    def test_locking(self):
        """
        1) Create an env file.
        2) Create a thread that creates a dict as one of env's elements, and
           keeps updating it, using the env save_lock attribute.
        3) Try to save the environment.
        """
        termination_event = threading.Event()
        env = utils_env.Env(filename=self.envfilename)

        def update_env(env):
            @utils_env.lock_safe
            def _update_env(env, key, value):
                env["changing_dict"][key] = value

            if "changing_dict" not in env:
                env["changing_dict"] = {}
            while True:
                key = "%s" % utils_misc.generate_random_string(length=10)
                value = "%s" % utils_misc.generate_random_string(length=10)
                _update_env(env, key, value)
                if termination_event.isSet():
                    break

        changing_thread = threading.Thread(target=update_env,
                                           args=(env,))
        changing_thread.start()
        time.sleep(0.3)
        try:
            env.save()
        finally:
            termination_event.set()

if __name__ == '__main__':
    unittest.main()
