"""
High-level migration test utility functions.

This module includes framework and some public functions.
"""

import errno
import fcntl
import logging
import os
import socket
import threading
import time
import re
import six
try:
    import pickle as cPickle
except ImportError:
    import cPickle

from aexpect import remote

from avocado.core import exceptions
from avocado.utils import crypto
from avocado.utils import data_factory
from avocado.utils import path as utils_path
from avocado.utils import process
from avocado.utils.data_structures import DataSize

from virttest import data_dir
from virttest import storage
from virttest import utils_test
from virttest import utils_misc
from virttest import env_process
from virttest import error_context as error


try:
    import aexpect
except ImportError:
    from virttest import aexpect


def guest_active(vm):
    o = vm.monitor.info("status")
    if isinstance(o, six.string_types):
        return "status: running" in o
    else:
        if "status" in o:
            return o.get("status") == "running"
        else:
            return o.get("running")


def get_nic_vendor(params, cmd):
    """
    Get host link layer
    :param params: Dictionary with the test parameters.
    :param cmd: Command string
    """
    utils_path.find_command(cmd)

    expected_nic_vendor = params.get("expected_nic_vendor",
                                     "IB InfiniBand")
    pattern = "(?<=Link layer: ).*"
    output = process.run(cmd).stdout_text
    try:
        nic_vendor = re.findall(pattern, output)[0]
    except IndexError:
        raise exceptions.TestError("Cannot get the link layer.")
    if nic_vendor not in expected_nic_vendor.split():
        raise exceptions.TestError("The Link layer is not correct, "
                                   "expected is '%s'" % expected_nic_vendor)


def migrate(vm, env=None, mig_timeout=3600, mig_protocol="tcp",
            mig_cancel=False, offline=False, stable_check=False,
            clean=False, save_path=None, dest_host='localhost', mig_port=None):
    """
    Migrate a VM locally and re-register it in the environment.

    :param vm: The VM to migrate.
    :param env: The environment dictionary.  If omitted, the migrated VM will
            not be registered.
    :param mig_timeout: timeout value for migration.
    :param mig_protocol: migration protocol
    :param mig_cancel: Test migrate_cancel or not when protocol is tcp.
    :param dest_host: Destination host (defaults to 'localhost').
    :param mig_port: Port that will be used for migration.
    :return: The post-migration VM, in case of same host migration, True in
            case of multi-host migration.
    """
    def mig_finished():
        if dest_vm.is_dead():
            raise exceptions.TestFail("Dest VM died during migration.")
        if not offline and vm.is_dead():
            raise exceptions.TestFail("Source VM died during migration")
        try:
            o = vm.monitor.info("migrate")
            if isinstance(o, six.string_types):
                return "status: active" not in o
            else:
                return o.get("status") != "active"
        except Exception:
            pass

    def mig_succeeded():
        o = vm.monitor.info("migrate")
        if isinstance(o, six.string_types):
            return "status: completed" in o
        else:
            return o.get("status") == "completed"

    def mig_failed():
        o = vm.monitor.info("migrate")
        if isinstance(o, six.string_types):
            return "status: failed" in o
        else:
            return o.get("status") == "failed"

    def mig_cancelled():
        o = vm.monitor.info("migrate")
        if isinstance(o, six.string_types):
            return ("Migration status: cancelled" in o or
                    "Migration status: canceled" in o)
        else:
            return (o.get("status") == "cancelled" or
                    o.get("status") == "canceled")

    def wait_for_migration():
        if not utils_misc.wait_for(mig_finished, mig_timeout, 2, 2,
                                   "Waiting for migration to finish"):
            raise exceptions.TestFail("Timeout expired while waiting for migration "
                                      "to finish")

    if dest_host == 'localhost':
        dest_vm = vm.clone()

    if (dest_host == 'localhost') and stable_check:
        # Pause the dest vm after creation
        _ = dest_vm.params.get('extra_params', '') + ' -S'
        dest_vm.params['extra_params'] = _

    if dest_host == 'localhost':
        dest_vm.create(migration_mode=mig_protocol, mac_source=vm)

    try:
        try:
            if mig_protocol in ["tcp", "rdma", "x-rdma"]:
                if dest_host == 'localhost':
                    uri = mig_protocol + ":0:%d" % dest_vm.migration_port
                else:
                    uri = mig_protocol + ':%s:%d' % (dest_host, mig_port)
            elif mig_protocol == "unix":
                uri = "unix:%s" % dest_vm.migration_file
            elif mig_protocol == "exec":
                uri = '"exec:nc localhost %s"' % dest_vm.migration_port

            if offline:
                vm.pause()
            vm.monitor.migrate(uri)

            if mig_cancel:
                time.sleep(2)
                vm.monitor.cmd("migrate_cancel")
                if not utils_misc.wait_for(mig_cancelled, 60, 2, 2,
                                           "Waiting for migration "
                                           "cancellation"):
                    raise exceptions.TestFail("Failed to cancel migration")
                if offline:
                    vm.resume()
                if dest_host == 'localhost':
                    dest_vm.destroy(gracefully=False)
                return vm
            else:
                wait_for_migration()
                if (dest_host == 'localhost') and stable_check:
                    save_path = None or data_dir.get_tmp_dir()
                    save1 = os.path.join(save_path, "src")
                    save2 = os.path.join(save_path, "dst")

                    vm.save_to_file(save1)
                    dest_vm.save_to_file(save2)

                    # Fail if we see deltas
                    md5_save1 = crypto.hash_file(save1)
                    md5_save2 = crypto.hash_file(save2)
                    if md5_save1 != md5_save2:
                        raise exceptions.TestFail("Mismatch of VM state before "
                                                  "and after migration")

                if (dest_host == 'localhost') and offline:
                    dest_vm.resume()
        except Exception:
            if dest_host == 'localhost':
                dest_vm.destroy()
            raise

    finally:
        if (dest_host == 'localhost') and stable_check and clean:
            logging.debug("Cleaning the state files")
            if os.path.isfile(save1):
                os.remove(save1)
            if os.path.isfile(save2):
                os.remove(save2)

    # Report migration status
    if mig_succeeded():
        logging.info("Migration finished successfully")
    elif mig_failed():
        raise exceptions.TestFail("Migration failed")
    else:
        status = vm.monitor.info("migrate")
        raise exceptions.TestFail("Migration ended with unknown status: %s" %
                                  status)

    if dest_host == 'localhost':
        if dest_vm.monitor.verify_status("paused"):
            logging.debug("Destination VM is paused, resuming it")
            dest_vm.resume()

    # Kill the source VM
    vm.destroy(gracefully=False)

    # Replace the source VM with the new cloned VM
    if (dest_host == 'localhost') and (env is not None):
        env.register_vm(vm.name, dest_vm)

    # Return the new cloned VM
    if dest_host == 'localhost':
        return dest_vm
    else:
        return vm


class MigrationData(object):

    def __init__(self, params, srchost, dsthost, vms_name, params_append):
        """
        Class that contains data needed for one migration.
        """
        self.params = params.copy()
        self.params.update(params_append)

        self.source = False
        if params.get("hostid") == srchost:
            self.source = True

        self.destination = False
        if params.get("hostid") == dsthost:
            self.destination = True

        self.src = srchost
        self.dst = dsthost
        self.hosts = [srchost, dsthost]
        self.mig_id = {'src': srchost, 'dst': dsthost, "vms": vms_name}
        self.vms_name = vms_name
        self.vms = []
        self.vm_ports = None

    def is_src(self):
        """
        :return: True if host is source.
        """
        return self.source

    def is_dst(self):
        """
        :return: True if host is destination.
        """
        return self.destination


class MultihostMigration(object):

    """
    Class that provides a framework for multi-host migration.

    Migration can be run both synchronously and asynchronously.
    To specify what is going to happen during the multi-host
    migration, it is necessary to reimplement the method
    migration_scenario. It is possible to start multiple migrations
    in separate threads, since self.migrate is thread safe.

    Only one test using multihost migration framework should be
    started on one machine otherwise it is necessary to solve the
    problem with listen server port.

    Multihost migration starts SyncListenServer through which
    all messages are transferred, since the multiple hosts can
    be in different states.

    Class SyncData is used to transfer data over network or
    synchronize the migration process. Synchronization sessions
    are recognized by session_id.

    It is important to note that, in order to have multi-host
    migration, one needs shared guest image storage. The simplest
    case is when the guest images are on an NFS server.

    Example:

    ::

        class TestMultihostMigration(utils_misc.MultihostMigration):
            def __init__(self, test, params, env):
                super(testMultihostMigration, self).__init__(test, params, env)

            def migration_scenario(self):
                srchost = self.params.get("hosts")[0]
                dsthost = self.params.get("hosts")[1]

                def worker(mig_data):
                    vm = env.get_vm("vm1")
                    session = vm.wait_for_login(timeout=self.login_timeout)
                    session.sendline("nohup dd if=/dev/zero of=/dev/null &")
                    session.cmd("killall -0 dd")

                def check_worker(mig_data):
                    vm = env.get_vm("vm1")
                    session = vm.wait_for_login(timeout=self.login_timeout)
                    session.cmd("killall -9 dd")

                # Almost synchronized migration, waiting to end it.
                # Work is started only on first VM.
                self.migrate_wait(["vm1", "vm2"], srchost, dsthost,
                                  worker, check_worker)

                # Migration started in different threads.
                # It allows to start multiple migrations simultaneously.
                mig1 = self.migrate(["vm1"], srchost, dsthost,
                                    worker, check_worker)
                mig2 = self.migrate(["vm2"], srchost, dsthost)
                mig2.join()
                mig1.join()

        mig = TestMultihostMigration(test, params, env)
        mig.run()
    """

    def __init__(self, test, params, env, preprocess_env=True):
        from autotest.client.shared.syncdata import SyncListenServer
        self.test = test
        self.params = params
        self.env = env
        self.hosts = params.get("hosts")
        self.hostid = params.get('hostid', "")
        self.comm_port = int(params.get("comm_port", 13234))
        vms_count = len(params["vms"].split())

        self.login_timeout = int(params.get("login_timeout", 360))
        self.disk_prepare_timeout = int(params.get("disk_prepare_timeout",
                                                   160 * vms_count))
        self.finish_timeout = int(params.get("finish_timeout",
                                             120 * vms_count))

        self.new_params = None

        if params.get("clone_master") == "yes":
            self.clone_master = True
        else:
            self.clone_master = False

        self.mig_protocol = params.get("mig_protocol")
        self.mig_timeout = int(params.get("mig_timeout"))
        # Port used to communicate info between source and destination
        self.regain_ip_cmd = params.get("regain_ip_cmd", None)
        self.not_login_after_mig = params.get("not_login_after_mig", None)

        self.vm_lock = threading.Lock()

        self.sync_server = None
        if self.clone_master:
            self.sync_server = SyncListenServer()

        if preprocess_env:
            self.preprocess_env()
            self._hosts_barrier(self.hosts, self.hosts, 'disk_prepared',
                                self.disk_prepare_timeout)

    def migration_scenario(self):
        """
        Multi Host migration_scenario is started from method run where the
        exceptions are checked. It is not necessary to take care of
        cleaning up after test crash or finish.
        """
        raise NotImplementedError

    def post_migration(self, vm, cancel_delay, mig_offline, dsthost, vm_ports,
                       not_wait_for_migration, fd, mig_data):
        pass

    def migrate_vms_src(self, mig_data):
        """
        Migrate vms source.

        :param mig_Data: Data for migration.

        For change way how machine migrates is necessary
        re implement this method.
        """
        def mig_wrapper(vm, cancel_delay, dsthost, vm_ports,
                        not_wait_for_migration, mig_offline, mig_data,
                        migrate_capabilities):
            vm.migrate(protocol=self.mig_protocol, cancel_delay=cancel_delay,
                       offline=mig_offline, dest_host=dsthost,
                       remote_port=vm_ports[vm.name],
                       not_wait_for_migration=not_wait_for_migration,
                       migrate_capabilities=migrate_capabilities)

            self.post_migration(vm, cancel_delay, mig_offline, dsthost,
                                vm_ports, not_wait_for_migration, None,
                                mig_data)

        logging.info("Start migrating now...")
        cancel_delay = mig_data.params.get("cancel_delay")
        if cancel_delay is not None:
            cancel_delay = int(cancel_delay)
        not_wait_for_migration = mig_data.params.get("not_wait_for_migration")
        if not_wait_for_migration == "yes":
            not_wait_for_migration = True
        mig_offline = mig_data.params.get("mig_offline")
        if mig_offline == "yes":
            mig_offline = True
        else:
            mig_offline = False

        migrate_capabilities = {'xbzrle': mig_data.params.get("xbzrle", "off"),
                                'rdma-pin-all': mig_data.params.get("rdma-pin-all", "off"),
                                'auto-converge': mig_data.params.get("auto-converge", "off"),
                                'zero-blocks': mig_data.params.get("zero-blocks", "off"),
                                'events': mig_data.params.get("events", "off"),
                                }

        multi_mig = []
        for vm in mig_data.vms:
            multi_mig.append((mig_wrapper, (vm, cancel_delay, mig_data.dst,
                                            mig_data.vm_ports,
                                            not_wait_for_migration,
                                            mig_offline, mig_data,
                                            migrate_capabilities)))
        utils_misc.parallel(multi_mig)

    def migrate_vms_dest(self, mig_data):
        """
        Migrate vms destination. This function is started on dest host during
        migration.

        :param mig_Data: Data for migration.
        """
        pass

    def __del__(self):
        if self.sync_server:
            self.sync_server.close()

    def master_id(self):
        return self.hosts[0]

    def _hosts_barrier(self, hosts, session_id, tag, timeout):
        from autotest.client.shared.syncdata import SyncData
        logging.debug("Barrier timeout: %d tags: %s" % (timeout, tag))
        tags = SyncData(self.master_id(), self.hostid, hosts,
                        "%s,%s,barrier" % (str(session_id), tag),
                        self.sync_server).sync(tag, timeout)
        logging.debug("Barrier tag %s" % (tags))

    def preprocess_env(self):
        """
        Prepare env to start vms.
        """
        storage.preprocess_images(self.test.bindir, self.params, self.env)

    def _check_vms_source(self, mig_data):
        from autotest.client.shared.syncdata import SyncData
        start_mig_tout = mig_data.params.get("start_migration_timeout", None)
        if start_mig_tout is None:
            for vm in mig_data.vms:
                vm.wait_for_login(timeout=self.login_timeout)

        if mig_data.params.get("host_mig_offline") != "yes":
            sync = SyncData(self.master_id(), self.hostid, mig_data.hosts,
                            mig_data.mig_id, self.sync_server)
            mig_data.vm_ports = sync.sync(timeout=240)[mig_data.dst]
            logging.info("Received from destination the migration port %s",
                         str(mig_data.vm_ports))

    def _check_vms_dest(self, mig_data):
        from autotest.client.shared.syncdata import SyncData
        mig_data.vm_ports = {}
        for vm in mig_data.vms:
            logging.info("Communicating to source migration port %s",
                         vm.migration_port)
            mig_data.vm_ports[vm.name] = vm.migration_port

        if mig_data.params.get("host_mig_offline") != "yes":
            SyncData(self.master_id(), self.hostid,
                     mig_data.hosts, mig_data.mig_id,
                     self.sync_server).sync(mig_data.vm_ports, timeout=240)

    def _prepare_params(self, mig_data):
        """
        Prepare separate params for vm migration.

        :param vms_name: List of vms.
        """
        new_params = mig_data.params.copy()
        new_params["vms"] = " ".join(mig_data.vms_name)
        return new_params

    def _check_vms(self, mig_data):
        """
        Check if vms are started correctly.

        :param vms: list of vms.
        :param source: Must be True if is source machine.
        """
        if mig_data.is_src():
            self._check_vms_source(mig_data)
        else:
            self._check_vms_dest(mig_data)

    def _quick_check_vms(self, mig_data):
        """
        Check if vms are started correctly.

        :param vms: list of vms.
        :param source: Must be True if is source machine.
        """
        logging.info("Try check vms %s" % (mig_data.vms_name))
        for vm in mig_data.vms_name:
            if self.env.get_vm(vm) not in mig_data.vms:
                mig_data.vms.append(self.env.get_vm(vm))
        for vm in mig_data.vms:
            logging.info("Check vm %s on host %s" % (vm.name, self.hostid))
            vm.verify_alive()

    def prepare_for_migration(self, mig_data, migration_mode):
        """
        Prepare destination of migration for migration.

        :param mig_data: Class with data necessary for migration.
        :param migration_mode: Migration mode for prepare machine.
        """
        from autotest.client.shared.syncdata import SyncData
        new_params = self._prepare_params(mig_data)

        new_params['migration_mode'] = migration_mode
        new_params['start_vm'] = 'yes'

        if self.params.get("migration_sync_vms", "no") == "yes":
            if mig_data.is_src():
                self.vm_lock.acquire()
                env_process.process(self.test, new_params, self.env,
                                    env_process.preprocess_image,
                                    env_process.preprocess_vm)
                self.vm_lock.release()
                self._quick_check_vms(mig_data)

                # Send vms configuration to dst host.
                vms = cPickle.dumps([self.env.get_vm(vm_name)
                                     for vm_name in mig_data.vms_name])

                self.env.get_vm(mig_data.vms_name[0]).monitor.info("qtree")
                SyncData(self.master_id(), self.hostid,
                         mig_data.hosts, mig_data.mig_id,
                         self.sync_server).sync(vms, timeout=240)
            elif mig_data.is_dst():
                # Load vms configuration from src host.
                vms = cPickle.loads(SyncData(self.master_id(), self.hostid,
                                             mig_data.hosts, mig_data.mig_id,
                                             self.sync_server).sync(timeout=240)[mig_data.src])
                for vm in vms:
                    # Save config to env. Used for create machine.
                    # When reuse_previous_config params is set don't check
                    # machine.
                    vm.address_cache = self.env.get("address_cache")
                    self.env.register_vm(vm.name, vm)

                self.vm_lock.acquire()
                env_process.process(self.test, new_params, self.env,
                                    env_process.preprocess_image,
                                    env_process.preprocess_vm)
                vms[0].monitor.info("qtree")
                self.vm_lock.release()
                self._quick_check_vms(mig_data)
        else:
            self.vm_lock.acquire()
            env_process.process(self.test, new_params, self.env,
                                env_process.preprocess_image,
                                env_process.preprocess_vm)
            self.vm_lock.release()
            self._quick_check_vms(mig_data)

        self._check_vms(mig_data)

    def migrate_vms(self, mig_data):
        """
        Migrate vms.
        """
        if mig_data.is_src():
            self.migrate_vms_src(mig_data)
        else:
            self.migrate_vms_dest(mig_data)

    def check_vms_dst(self, mig_data):
        """
        Check vms after migrate.

        :param mig_data: object with migration data.
        """
        for vm in mig_data.vms:
            vm.resume()
            if not guest_active(vm):
                raise exceptions.TestFail("Guest not active after migration")

        logging.info("Migrated guest appears to be running")

        logging.info("Logging into migrated guest after migration...")
        for vm in mig_data.vms:
            if self.regain_ip_cmd is not None:
                session_serial = vm.wait_for_serial_login(
                    timeout=self.login_timeout)
                # There is sometime happen that system sends some message on
                # serial console and IP renew command block test. Because
                # there must be added "sleep" in IP renew command.
                session_serial.cmd(self.regain_ip_cmd)

            if not self.not_login_after_mig:
                vm.wait_for_login(timeout=self.login_timeout)

    def check_vms_src(self, mig_data):
        """
        Check vms after migrate.

        :param mig_data: object with migration data.
        """
        pass

    def postprocess_env(self):
        """
        Kill vms and delete cloned images.
        """
        pass

    def before_migration(self, mig_data):
        """
        Do something right before migration.

        :param mig_data: object with migration data.
        """
        pass

    def migrate(self, vms_name, srchost, dsthost, start_work=None,
                check_work=None, params_append=None):
        """
        Migrate machine from srchost to dsthost. It executes start_work on
        source machine before migration and executes check_work on dsthost
        after migration.

        Migration execution progress:

        ::

            source host                   |   dest host
            --------------------------------------------------------
               prepare guest on both sides of migration
                - start machine and check if machine works
                - synchronize transfer data needed for migration
            --------------------------------------------------------
            start work on source guests   |   wait for migration
            --------------------------------------------------------
                         migrate guest to dest host.
                  wait on finish migration synchronization
            --------------------------------------------------------
                                          |   check work on vms
            --------------------------------------------------------
                        wait for sync on finish migration

        :param vms_name: List of vms.
        :param srchost: src host id.
        :param dsthost: dst host id.
        :param start_work: Function started before migration.
        :param check_work: Function started after migration.
        :param params_append: Append params to self.params only for migration.
        """
        def migrate_wrap(vms_name, srchost, dsthost, start_work=None,
                         check_work=None, params_append=None):
            logging.info("Starting migrate vms %s from host %s to %s" %
                         (vms_name, srchost, dsthost))
            pause = self.params.get("paused_after_start_vm")
            mig_error = None
            mig_data = MigrationData(self.params, srchost, dsthost,
                                     vms_name, params_append)
            cancel_delay = self.params.get("cancel_delay", None)
            host_offline_migration = self.params.get("host_mig_offline")

            try:
                try:
                    if mig_data.is_src():
                        self.prepare_for_migration(mig_data, None)
                    elif self.hostid == dsthost:
                        if host_offline_migration != "yes":
                            self.prepare_for_migration(
                                mig_data, self.mig_protocol)
                    else:
                        return

                    if mig_data.is_src():
                        if start_work:
                            if pause != "yes":
                                start_work(mig_data)
                            else:
                                raise exceptions.TestSkipError("Can't start "
                                                               "work if vm is "
                                                               "paused.")

                    # Starts VM and waits timeout before migration.
                    if pause == "yes" and mig_data.is_src():
                        for vm in mig_data.vms:
                            vm.resume()
                        wait = self.params.get("start_migration_timeout", 0)
                        logging.debug("Wait for migration %s seconds." %
                                      (wait))
                        time.sleep(int(wait))

                    self.before_migration(mig_data)

                    self.migrate_vms(mig_data)

                    timeout = 60
                    if cancel_delay is None:
                        if host_offline_migration == "yes":
                            self._hosts_barrier(self.hosts,
                                                mig_data.mig_id,
                                                'wait_for_offline_mig',
                                                self.finish_timeout)
                            if mig_data.is_dst():
                                self.prepare_for_migration(
                                    mig_data, self.mig_protocol)
                            self._hosts_barrier(self.hosts,
                                                mig_data.mig_id,
                                                'wait2_for_offline_mig',
                                                self.finish_timeout)

                        if (not mig_data.is_src()):
                            timeout = self.mig_timeout
                        self._hosts_barrier(mig_data.hosts, mig_data.mig_id,
                                            'mig_finished', timeout)

                        if mig_data.is_dst():
                            self.check_vms_dst(mig_data)
                            if check_work:
                                check_work(mig_data)
                        else:
                            self.check_vms_src(mig_data)
                            if check_work:
                                check_work(mig_data)
                except Exception:
                    mig_error = True
                    raise
            finally:
                if mig_error and cancel_delay is not None:
                    self._hosts_barrier(self.hosts,
                                        mig_data.mig_id,
                                        'test_finihed',
                                        self.finish_timeout)
                elif mig_error:
                    raise exceptions.TestFail(mig_error)

        def wait_wrap(vms_name, srchost, dsthost):
            mig_data = MigrationData(self.params, srchost, dsthost, vms_name,
                                     None)
            timeout = (self.login_timeout + self.mig_timeout +
                       self.finish_timeout)

            self._hosts_barrier(self.hosts, mig_data.mig_id,
                                'test_finihed', timeout)

        if (self.hostid in [srchost, dsthost]):
            mig_thread = utils_misc.InterruptedThread(migrate_wrap, (vms_name,
                                                                     srchost,
                                                                     dsthost,
                                                                     start_work,
                                                                     check_work,
                                                                     params_append))
        else:
            mig_thread = utils_misc.InterruptedThread(wait_wrap, (vms_name,
                                                                  srchost,
                                                                  dsthost))
        mig_thread.start()
        return mig_thread

    def migrate_wait(self, vms_name, srchost, dsthost, start_work=None,
                     check_work=None, params_append=None):
        """
        Migrate machine from srchost to dsthost and wait for finish.
        It executes start_work on source machine before migration and executes
        check_work on dsthost after migration.

        :param vms_name: List of vms.
        :param srchost: src host id.
        :param dsthost: dst host id.
        :param start_work: Function which is started before migration.
        :param check_work: Function which is started after
                           done of migration.
        """
        self.migrate(vms_name, srchost, dsthost, start_work, check_work,
                     params_append).join()

    def cleanup(self):
        """
        Cleanup env after test.
        """
        if self.clone_master:
            self.sync_server.close()
            self.postprocess_env()

    def run(self):
        """
        Start multihost migration scenario.
        After scenario is finished or if scenario crashed it calls postprocess
        machines and cleanup env.
        """
        try:
            self.migration_scenario()

            self._hosts_barrier(self.hosts, self.hosts, 'all_test_finished',
                                self.finish_timeout)
        finally:
            self.cleanup()


class MultihostMigrationFd(MultihostMigration):

    def __init__(self, test, params, env, preprocess_env=True):
        super(MultihostMigrationFd, self).__init__(test, params, env,
                                                   preprocess_env)

    def migrate_vms_src(self, mig_data):
        """
        Migrate vms source.

        :param mig_Data: Data for migration.

        For change way how machine migrates is necessary
        re implement this method.
        """
        def mig_wrapper(vm, cancel_delay, mig_offline, dsthost, vm_ports,
                        not_wait_for_migration, fd):
            vm.migrate(cancel_delay=cancel_delay, offline=mig_offline,
                       dest_host=dsthost,
                       not_wait_for_migration=not_wait_for_migration,
                       protocol=self.mig_protocol,
                       fd_src=fd)

            self.post_migration(vm, cancel_delay, mig_offline, dsthost,
                                vm_ports, not_wait_for_migration, fd, mig_data)

        logging.info("Start migrating now...")
        cancel_delay = mig_data.params.get("cancel_delay")
        if cancel_delay is not None:
            cancel_delay = int(cancel_delay)
        not_wait_for_migration = mig_data.params.get("not_wait_for_migration")
        if not_wait_for_migration == "yes":
            not_wait_for_migration = True
        mig_offline = mig_data.params.get("mig_offline")
        if mig_offline == "yes":
            mig_offline = True
        else:
            mig_offline = False

        multi_mig = []
        for vm in mig_data.vms:
            fd = vm.params.get("migration_fd")
            multi_mig.append((mig_wrapper, (vm, cancel_delay, mig_offline,
                                            mig_data.dst, mig_data.vm_ports,
                                            not_wait_for_migration,
                                            fd)))
        utils_misc.parallel(multi_mig)

    def _check_vms_source(self, mig_data):
        start_mig_tout = mig_data.params.get("start_migration_timeout", None)
        if start_mig_tout is None:
            for vm in mig_data.vms:
                vm.wait_for_login(timeout=self.login_timeout)
        self._hosts_barrier(mig_data.hosts, mig_data.mig_id,
                            'prepare_VMS', 60)

    def _check_vms_dest(self, mig_data):
        self._hosts_barrier(mig_data.hosts, mig_data.mig_id,
                            'prepare_VMS', 120)
        for vm in mig_data.vms:
            fd = vm.params.get("migration_fd")
            os.close(fd)

    def _connect_to_server(self, host, port, timeout=60):
        """
        Connect to network server.
        """
        endtime = time.time() + timeout
        sock = None
        while endtime > time.time():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect((host, port))
                break
            except socket.error as err:
                code = err.errno
                if (code != errno.ECONNREFUSED):
                    raise
                time.sleep(1)

        return sock

    def _create_server(self, port, timeout=60):
        """
        Create network server.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.bind(('', port))
        sock.listen(1)
        return sock

    def migrate_wait(self, vms_name, srchost, dsthost, start_work=None,
                     check_work=None, params_append=None):
        from autotest.client.shared.syncdata import SyncData
        vms_count = len(vms_name)
        mig_ports = []

        if self.params.get("hostid") == srchost:
            last_port = 5199
            for _ in range(vms_count):
                last_port = utils_misc.find_free_port(last_port + 1, 5899)
                mig_ports.append(last_port)

        sync = SyncData(self.master_id(), self.hostid,
                        self.params.get("hosts"),
                        {'src': srchost, 'dst': dsthost,
                         'port': "ports"}, self.sync_server)

        mig_ports = sync.sync(mig_ports, timeout=120)
        mig_ports = mig_ports[srchost]
        logging.debug("Migration port %s" % (mig_ports))

        if self.params.get("hostid") != srchost:
            sockets = []
            for mig_port in mig_ports:
                sockets.append(self._connect_to_server(srchost, mig_port))
            try:
                fds = {}
                for s, vm_name in list(zip(sockets, vms_name)):
                    fds["migration_fd_%s" % vm_name] = s.fileno()
                logging.debug("File descriptors %s used for"
                              " migration." % (fds))

                super_cls = super(MultihostMigrationFd, self)
                super_cls.migrate_wait(vms_name, srchost, dsthost,
                                       start_work=start_work,
                                       params_append=fds)
            finally:
                for s in sockets:
                    s.close()
        else:
            sockets = []
            for mig_port in mig_ports:
                sockets.append(self._create_server(mig_port))
            try:
                conns = []
                for s in sockets:
                    conns.append(s.accept()[0])
                fds = {}
                for conn, vm_name in list(zip(conns, vms_name)):
                    fds["migration_fd_%s" % vm_name] = conn.fileno()
                logging.debug("File descriptors %s used for"
                              " migration." % (fds))

                # Prohibits descriptor inheritance.
                for fd in list(fds.values()):
                    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
                    flags |= fcntl.FD_CLOEXEC
                    fcntl.fcntl(fd, fcntl.F_SETFD, flags)

                super_cls = super(MultihostMigrationFd, self)
                super_cls.migrate_wait(vms_name, srchost, dsthost,
                                       start_work=start_work,
                                       params_append=fds)
                for conn in conns:
                    conn.close()
            finally:
                for s in sockets:
                    s.close()


class MultihostMigrationExec(MultihostMigration):

    def __init__(self, test, params, env, preprocess_env=True):
        super(MultihostMigrationExec, self).__init__(test, params, env,
                                                     preprocess_env)

    def post_migration(self, vm, cancel_delay, mig_offline, dsthost,
                       mig_exec_cmd, not_wait_for_migration, fd,
                       mig_data):
        if mig_data.params.get("host_mig_offline") == "yes":
            src_tmp = vm.params.get("migration_sfiles_path")
            dst_tmp = vm.params.get("migration_dfiles_path")
            username = vm.params.get("username")
            password = vm.params.get("password")
            remote.scp_to_remote(dsthost, "22", username, password,
                                 src_tmp, dst_tmp)

    def migrate_vms_src(self, mig_data):
        """
        Migrate vms source.

        :param mig_Data: Data for migration.

        For change way how machine migrates is necessary
        re implement this method.
        """
        def mig_wrapper(vm, cancel_delay, mig_offline, dsthost, mig_exec_cmd,
                        not_wait_for_migration, mig_data):
            vm.migrate(cancel_delay=cancel_delay,
                       offline=mig_offline,
                       dest_host=dsthost,
                       not_wait_for_migration=not_wait_for_migration,
                       protocol=self.mig_protocol,
                       migration_exec_cmd_src=mig_exec_cmd)

            self.post_migration(vm, cancel_delay, mig_offline,
                                dsthost, mig_exec_cmd,
                                not_wait_for_migration, None, mig_data)

        logging.info("Start migrating now...")
        cancel_delay = mig_data.params.get("cancel_delay")
        if cancel_delay is not None:
            cancel_delay = int(cancel_delay)
        not_wait_for_migration = mig_data.params.get("not_wait_for_migration")
        if not_wait_for_migration == "yes":
            not_wait_for_migration = True
        mig_offline = mig_data.params.get("mig_offline")
        if mig_offline == "yes":
            mig_offline = True
        else:
            mig_offline = False

        multi_mig = []
        for vm in mig_data.vms:
            mig_exec_cmd = vm.params.get("migration_exec_cmd_src")
            multi_mig.append((mig_wrapper, (vm, cancel_delay,
                                            mig_offline,
                                            mig_data.dst,
                                            mig_exec_cmd,
                                            not_wait_for_migration,
                                            mig_data)))
        utils_misc.parallel(multi_mig)

    def _check_vms_source(self, mig_data):
        start_mig_tout = mig_data.params.get("start_migration_timeout", None)
        if start_mig_tout is None:
            for vm in mig_data.vms:
                vm.wait_for_login(timeout=self.login_timeout)

        if mig_data.params.get("host_mig_offline") != "yes":
            self._hosts_barrier(mig_data.hosts, mig_data.mig_id,
                                'prepare_VMS', 60)

    def _check_vms_dest(self, mig_data):
        if mig_data.params.get("host_mig_offline") != "yes":
            self._hosts_barrier(mig_data.hosts, mig_data.mig_id,
                                'prepare_VMS', 120)

    def migrate_wait(self, vms_name, srchost, dsthost, start_work=None,
                     check_work=None, params_append=None):
        from autotest.client.shared.syncdata import SyncData
        vms_count = len(vms_name)
        mig_ports = []

        host_offline_migration = self.params.get("host_mig_offline")

        sync = SyncData(self.master_id(), self.hostid,
                        self.params.get("hosts"),
                        {'src': srchost, 'dst': dsthost,
                         'port': "ports"}, self.sync_server)

        mig_params = {}

        if host_offline_migration != "yes":
            if self.params.get("hostid") == dsthost:
                last_port = 5199
                for _ in range(vms_count):
                    last_port = utils_misc.find_free_port(last_port + 1, 5899)
                    mig_ports.append(last_port)

            mig_ports = sync.sync(mig_ports, timeout=120)
            mig_ports = mig_ports[dsthost]
            logging.debug("Migration port %s" % (mig_ports))
            mig_cmds = {}
            for mig_port, vm_name in list(zip(mig_ports, vms_name)):
                mig_dst_cmd = "nc -l %s %s" % (dsthost, mig_port)
                mig_src_cmd = "nc %s %s" % (dsthost, mig_port)
                mig_params["migration_exec_cmd_src_%s" %
                           (vm_name)] = mig_src_cmd
                mig_params["migration_exec_cmd_dst_%s" %
                           (vm_name)] = mig_dst_cmd
        else:
            # Generate filenames for migration.
            mig_fnam = {}
            for vm_name in vms_name:
                while True:
                    fnam = ("mig_" + data_factory.generate_random_string(6) +
                            "." + vm_name)
                    fpath = os.path.join(self.test.tmpdir, fnam)
                    if (fnam not in list(mig_fnam.values()) and
                            not os.path.exists(fnam)):
                        mig_fnam[vm_name] = fpath
                        break
            mig_fs = sync.sync(mig_fnam, timeout=120)
            mig_cmds = {}
            # Prepare cmd and files.
            if self.params.get("hostid") == srchost:
                mig_src_cmd = "gzip -c > %s"
                for vm_name in vms_name:
                    mig_params["migration_sfiles_path_%s" % (vm_name)] = (
                        mig_fs[srchost][vm_name])
                    mig_params["migration_dfiles_path_%s" % (vm_name)] = (
                        mig_fs[dsthost][vm_name])

                    mig_params["migration_exec_cmd_src_%s" % (vm_name)] = (
                        mig_src_cmd % mig_fs[srchost][vm_name])

            if self.params.get("hostid") == dsthost:
                mig_dst_cmd = "gzip -c -d %s"
                for vm_name in vms_name:
                    mig_params["migration_exec_cmd_dst_%s" % (vm_name)] = (
                        mig_dst_cmd % mig_fs[dsthost][vm_name])

        logging.debug("Exec commands %s", mig_cmds)

        super_cls = super(MultihostMigrationExec, self)
        super_cls.migrate_wait(vms_name, srchost, dsthost,
                               start_work=start_work,
                               params_append=mig_params)


class MultihostMigrationRdma(MultihostMigration):
    """
    It is important to note that, in order to have multi-host
    migration with RDMA, need setup the follow steps on src and
    dst host:
    1. Install some packages: libmlx, infiniband, rdma
    2. Create configuration for rdma network card, example:

        # cat /etc/sysconfig/network-scripts/ifcfg-ib0
        DEVICE=ib0
        TYPE=InfiniBand
        ONBOOT=yes
        NM_CONTROLLED=no
        BOOTPROTO=static
        BROADCAST=192.168.0.255
        IPADDR=192.168.0.21
        NETMASK=255.255.255.0

    3. Restart related services: network, opensm, rdma
    """

    def __init__(self, test, params, env, preprocess_env=True):
        check_nic_vendor_cmd = "ibstat"
        get_nic_vendor(params, check_nic_vendor_cmd)

        super(MultihostMigrationRdma, self).__init__(test, params, env,
                                                     preprocess_env)

    def migrate_vms_src(self, mig_data):
        """
        Migrate vms source.

        :param mig_Data: Data for migration.

        For change way how machine migrates is necessary
        re implement this method.
        """
        def mig_wrapper(vm, cancel_delay, dsthost, vm_ports,
                        not_wait_for_migration, mig_offline, mig_data):
            vm.migrate(cancel_delay=cancel_delay, offline=mig_offline,
                       dest_host=dsthost, remote_port=vm_ports[vm.name],
                       not_wait_for_migration=not_wait_for_migration,
                       protocol=self.mig_protocol)

            self.post_migration(vm, cancel_delay, mig_offline, dsthost,
                                vm_ports, not_wait_for_migration, None,
                                mig_data)

        logging.info("Start migrating now...")
        # Use of RDMA during migration requires pinning and registering memory
        # with the hardware.
        enable_rdma_pin_all = mig_data.params.get("enable_rdma_pin_all",
                                                  "migrate_set_capability rdma-pin-all on")
        cancel_delay = mig_data.params.get("cancel_delay")
        if cancel_delay is not None:
            cancel_delay = int(cancel_delay)
        not_wait_for_migration = mig_data.params.get("not_wait_for_migration")
        if not_wait_for_migration == "yes":
            not_wait_for_migration = True
        mig_offline = mig_data.params.get("mig_offline")
        if mig_offline == "yes":
            mig_offline = True
        else:
            mig_offline = False

        multi_mig = []
        for vm in mig_data.vms:
            vm.monitor.human_monitor_cmd(enable_rdma_pin_all)
            multi_mig.append((mig_wrapper, (vm, cancel_delay, mig_data.dst,
                                            mig_data.vm_ports,
                                            not_wait_for_migration,
                                            mig_offline, mig_data)))
        utils_misc.parallel(multi_mig)


class MigrationBase(object):

    """Class that provides some general functions for multi-host migration."""

    def __setup__(self, test, params, env, srchost, dsthost):

        """initialize some public params
        """

        self.test = test
        self.params = params
        self.env = env
        self.srchost = srchost
        self.dsthost = dsthost
        self.vms = params.objects("vms")
        self.vm = self.vms[0]
        self.is_src = params["hostid"] == self.srchost
        self.pre_sub_test = params.get("pre_sub_test")
        self.post_sub_test = params.get("post_sub_test")
        self.login_before_pre_tests = params.get("login_before_pre_tests",
                                                 "no")
        self.mig_bg_command = params.get("migration_bg_command",
                                         "cd /tmp; nohup ping localhost &")
        self.mig_bg_check_command = params.get("migration_bg_check_command",
                                               "pgrep ping")
        self.mig_bg_kill_command = params.get("migration_bg_kill_command",
                                              "pkill -9 ping")
        self.migration_timeout = int(params.get("migration_timeout",
                                                "1500"))
        self.login_timeout = 480
        self.stop_migrate = False
        self.migrate_count = int(params.get("migrate_count", 1))
        self.id = {"src": self.srchost,
                   "dst": self.dsthost,
                   "type": "file_transfer"}
        self.capabilitys = params.objects("capabilitys")
        self.capabilitys_state = params.objects("capabilitys_state")
        for i in range(0, len(self.capabilitys_state)):
            if self.capabilitys_state[i].strip() == "enable":
                self.capabilitys_state[i] = True
            else:
                self.capabilitys_state[i] = False
        self.parameters = params.objects("parameters")
        self.parameters_value = params.objects("parameters_value")
        self.cache_size = params.objects("cache_size")
        self.kill_bg_stress_cmd = params.get("kill_bg_stress_cmd",
                                             "killall -9 stress")
        self.bg_stress_test = params.get("bg_stress_test")
        self.check_running_cmd = params.get("check_running_cmd")
        self.max_speed = params.get("max_migration_speed", "1000")
        self.max_speed = DataSize('%sM' % self.max_speed).b
        self.need_set_speed = params.get("need_set_speed", "yes") == "yes"
        self.WAIT_SHORT = 15

    @error.context_aware
    def run_pre_sub_test(self):

        """
        run sub test on src before migration
        """

        if self.is_src:
            if self.pre_sub_test:
                if self.login_before_pre_tests == "yes":
                    vm = self.env.get_vm(self.params["main_vm"])
                    vm.wait_for_login(timeout=self.login_timeout)
                error.context("Run sub test '%s' before migration on src"
                              % self.pre_sub_test, logging.info)
                utils_test.run_virt_sub_test(self.test, self.params,
                                             self.env, self.pre_sub_test)

    @error.context_aware
    def run_post_sub_test(self):

        """
        run sub test on dst after migration
        """

        if not self.is_src:
            if self.post_sub_test:
                error.context("Run sub test '%s' after migration on dst"
                              % self.post_sub_test, logging.info)
                utils_test.run_virt_sub_test(self.test, self.params,
                                             self.env, self.post_sub_test)

    def prepare_vm(self, vm_name):

        """
        Prepare, start vm and return vm.
        :param vm_name: vm name to be started.
        :return: Started VM.
        """

        self.vm_lock = threading.Lock()
        new_params = self.params.copy()
        new_params['migration_mode'] = None
        new_params['start_vm'] = 'yes'
        self.vm_lock.acquire()
        env_process.process(self.test, new_params, self.env,
                            env_process.preprocess_image,
                            env_process.preprocess_vm)
        self.vm_lock.release()
        vm = self.env.get_vm(vm_name)
        vm.wait_for_login(timeout=self.login_timeout)
        return vm

    def start_worker(self):

        """
        run background command on src before migration
        """

        if self.is_src:
            logging.info("Try to login guest before migration test.")
            vm = self.env.get_vm(self.params["main_vm"])
            session = vm.wait_for_login(timeout=self.login_timeout)
            logging.debug("Sending command: '%s'" % self.mig_bg_command)
            s, o = session.cmd_status_output(self.mig_bg_command)
            if s != 0:
                raise exceptions.TestError("Failed to run bg cmd in guest,"
                                           " Output is '%s'." % o)
            time.sleep(5)

    def check_worker(self):

        """
        check background command on dst after migration
        """

        if not self.is_src:
            logging.info("Try to login guest after migration test.")
            vm = self.env.get_vm(self.params["main_vm"])
            serial_login = self.params.get("serial_login")
            if serial_login == "yes":
                session = vm.wait_for_serial_login(timeout=self.login_timeout)
            else:
                session = vm.wait_for_login(timeout=self.login_timeout)
            logging.info("Check the background command in the guest.")
            s, o = session.cmd_status_output(self.mig_bg_check_command)
            if s:
                raise exceptions.TestFail("Background command not found,"
                                          " Output is '%s'." % o)
            logging.info("Kill the background command in the guest.")
            session.sendline(self.mig_bg_kill_command)
            session.close()

    def ping_pong_migrate(self, mig_type, sync, start_work=None,
                          check_work=None):

        """
        ping pong migration test

        :param mig_type: class MultihostMigration
        :param sync: class SyncData
        :param start_work: run sub test on src before migration
        :param check_work: run sub test on dst after migration
        """

        while True:
            if self.stop_migrate:
                break
            logging.info("ping pong migration...")
            mig_type(self.test, self.params, self.env).migrate_wait(
                [self.vm], self.srchost, self.dsthost,
                start_work=start_work, check_work=check_work)
            sync.sync(True, timeout=self.login_timeout)
            vm = self.env.get_vm(self.params["main_vm"])
            if vm.is_dead():
                self.stop_migrate = True
            elif self.migrate_count-1 == 0:
                self.stop_migrate = True
            else:
                self.dsthost, self.srchost = self.srchost, self.dsthost
                self.is_src = not self.is_src
                start_work = None

    @error.context_aware
    def get_migration_info(self, vm):

        """
        get info after migration, focus on if keys in returned disc.

        :param vm: vm object
        """

        error.context("Get 'xbzrle-cache/status/setup-time/downtime/"
                      "total-time/ram' info after migration.",
                      logging.info)
        xbzrle_cache = vm.monitor.info("migrate").get("xbzrle-cache")
        status = vm.monitor.info("migrate").get("status")
        setup_time = vm.monitor.info("migrate").get("setup-time")
        downtime = vm.monitor.info("migrate").get("downtime")
        total_time = vm.monitor.info("migrate").get("total-time")
        ram = vm.monitor.info("migrate").get("ram")
        logging.info("Migration info:\nxbzrle-cache: %s\nstatus: %s\n"
                     "setup-time: %s\ndowntime: %s\ntotal-time: "
                     "%s\nram: %s" % (xbzrle_cache, status, setup_time,
                                      downtime, total_time, ram))

    @error.context_aware
    def get_migration_capability(self, index=0):

        """
        Get the state of migrate-capability.

        :param index: the index of capabilitys list.
        """

        if self.is_src:
            for i in range(index, len(self.capabilitys)):
                error.context("Get capability '%s' state."
                              % self.capabilitys[i], logging.info)
                vm = self.env.get_vm(self.params["main_vm"])
                self.state = vm.monitor.get_migrate_capability(
                    self.capabilitys[i])
                if self.state != self.capabilitys_state[i]:
                    raise exceptions.TestFail(
                        "The expected '%s' state: '%s',"
                        " Actual result: '%s'." % (
                            self.capabilitys[i],
                            self.capabilitys_state[i],
                            self.state))

    @error.context_aware
    def set_migration_capability(self, state, capability):

        """
        Set the capability of migrate to state.

        :param state: Bool value of capability.
        :param capability: capability which need to set.
        """

        if self.is_src:
            error.context("Set '%s' state to '%s'." % (capability, state),
                          logging.info)
            vm = self.env.get_vm(self.params["main_vm"])
            vm.monitor.set_migrate_capability(state, capability)

    @error.context_aware
    def get_migration_cache_size(self, index=0):

        """
        Get the xbzrle cache size.

        :param index: the index of cache_size list
        """

        if self.is_src:
            error.context("Try to get cache size.", logging.info)
            vm = self.env.get_vm(self.params["main_vm"])
            cache_size = vm.monitor.get_migrate_cache_size()
            error.context("Get cache size: %s" % cache_size, logging.info)
            if cache_size != int(self.cache_size[index]):
                raise exceptions.TestFail(
                    "The expected cache size: %s,"
                    " Actual result: %s." % (self.cache_size[index],
                                             cache_size))

    @error.context_aware
    def set_migration_cache_size(self, value):

        """
        Set the cache size of migrate to value.

        :param value: the cache size to set.
        """

        if self.is_src:
            error.context("Set cache size to %s." % value, logging.info)
            vm = self.env.get_vm(self.params["main_vm"])
            vm.monitor.set_migrate_cache_size(value)

    @error.context_aware
    def get_migration_parameter(self, index=0):

        """
        Get the value of parameter.

        :param index: the index of parameters list.
        """

        if self.is_src:
            for i in range(index, len(self.parameters)):
                error.context("Get parameter '%s' value."
                              % self.parameters[i], logging.info)
                vm = self.env.get_vm(self.params["main_vm"])
                self.value = vm.monitor.get_migrate_parameter(
                    self.parameters[i])
                if int(self.value) != int(self.parameters_value[i]):
                    raise exceptions.TestFail(
                        "The expected '%s' value: '%s',"
                        " Actual result: '%s'." % (
                            self.parameters[i],
                            self.parameters_value[i],
                            self.value))

    @error.context_aware
    def set_migration_parameter(self, index=0):

        """
        Set the value of parameter.

        :param index: the index of parameters/parameters_value list.
        """

        if self.is_src:
            for i in range(index, len(self.parameters)):
                error.context("Set '%s' value to '%s'." % (
                    self.parameters[i],
                    self.parameters_value[i]), logging.info)
                vm = self.env.get_vm(self.params["main_vm"])
                vm.monitor.set_migrate_parameter(self.parameters[i],
                                                 int(self.parameters_value[i]))

    @error.context_aware
    def set_migration_speed(self, value):

        """
        Set maximum speed (in bytes/sec) for migrations.

        :param value: Speed in bytes/sec
        """

        if self.is_src:
            error.context("Set migration speed to %s." % value, logging.info)
            vm = self.env.get_vm(self.params["main_vm"])
            vm.monitor.migrate_set_speed("%sB" % value)

    @error.context_aware
    def set_migration_downtime(self, value):

        """
        Set maximum tolerated downtime (in seconds) for migration.

        :param value: maximum downtime (in seconds)
        """

        if self.is_src:
            error.context("Set downtime to %s." % value, logging.info)
            vm = self.env.get_vm(self.params["main_vm"])
            vm.monitor.migrate_set_downtime(value)

    @error.context_aware
    def set_migration_cancel(self):

        """
        Cancel migration after it is beginning
        """

        if self.is_src:
            error.context("Cancel migration.", logging.info)
            vm = self.env.get_vm(self.params["main_vm"])
            vm.monitor.cmd("migrate_cancel")

    @error.context_aware
    def get_migration_cancelled(self):

        """
        check the migration cancelled
        """

        if self.is_src:
            vm = self.env.get_vm(self.params["main_vm"])
            o = vm.monitor.info("migrate")
            if isinstance(o, six.string_types):
                return ("Migration status: cancelled" in o or
                        "Migration status: canceled" in o)
            else:
                return (o.get("status") == "cancelled" or
                        o.get("status") == "canceled")

    @error.context_aware
    def clean_up(self, kill_bg_cmd, vm):

        """
        kill background cmd on dst after migration

        :param kill_bg_cmd: cmd for kill background test
        :param vm:  vm object
        """

        error.context("Kill the background test by '%s' in guest"
                      "." % kill_bg_cmd, logging.info)
        session = vm.wait_for_login(timeout=self.login_timeout)
        if session.cmd_status(self.check_running_cmd) != 0:
            logging.info("The background test in guest is finished, "
                         "no need to kill.")
        else:
            try:
                s, o = session.cmd_status_output(kill_bg_cmd)
                logging.info("The output after run kill command: %r" % o)
                if "No such process" in o or "not found" in o \
                        or "no running instance" in o:
                    if session.cmd_status(self.check_running_cmd) != 0:
                        logging.info("The background test in guest is "
                                     "finished before kill it.")
                elif s:
                    raise exceptions.TestFail("Failed to kill the background"
                                              " test in guest.")
            except (aexpect.ShellStatusError, aexpect.ShellTimeoutError):
                pass
        session.close()

    @error.context_aware
    def start_stress(self):

        """
        start stress test on src before migration
        """

        logging.info("Try to login guest before migration test.")
        vm = self.env.get_vm(self.params["main_vm"])
        session = vm.wait_for_login(timeout=self.login_timeout)
        error.context("Do stress test before migration.", logging.info)
        bg = utils_misc.InterruptedThread(
            utils_test.run_virt_sub_test,
            args=(self.test, self.params, self.env,),
            kwargs={"sub_type": self.bg_stress_test})
        bg.start()
        time.sleep(self.WAIT_SHORT)

        def check_running():
            return session.cmd_status(self.check_running_cmd) == 0

        if self.check_running_cmd:
            if not utils_misc.wait_for(check_running, timeout=360):
                raise exceptions.TestFail("Failed to start %s in guest." %
                                          self.bg_stress_test)

    @error.context_aware
    def install_stressapptest(self):

        """
        install stressapptest
        """

        vm = self.env.get_vm(self.params["main_vm"])
        session = vm.wait_for_login(timeout=self.login_timeout)
        app_repo = "git clone https://github.com/stressapptest/" \
                   "stressapptest.git"
        stressapptest_insatll_cmd = "rm -rf stressapptest " \
                                    "&& %s" \
                                    " && cd stressapptest " \
                                    "&& ./configure " \
                                    "&& make " \
                                    "&& make install" % app_repo
        stressapptest_insatll_cmd = \
            self.params.get("stressapptest_insatll_cmd",
                            stressapptest_insatll_cmd)
        error.context("Install stressapptest.", logging.info)
        s, o = session.cmd_status_output(stressapptest_insatll_cmd)
        session.close()
        if s:
            raise exceptions.TestError("Failed to install stressapptest "
                                       "in guest: '%s'" % o)
