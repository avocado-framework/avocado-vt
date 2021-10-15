import logging
import functools
import os

from enum import Enum

from six import itervalues, iteritems, string_types

from avocado.utils import distro
from avocado.utils import path as utils_path

from virttest import virsh, migration, remote
from virttest import libvirt_version
from virttest import utils_iptables, utils_selinux, utils_misc

from virttest.libvirt_xml import vm_xml

from virttest.libvirt_vm import get_uri_with_transport as get_uri

from virttest.utils_conn import TLSConnection, TCPConnection, SSHConnection

from virttest.utils_test import libvirt

from virttest.utils_libvirt import libvirt_disk

from virttest.utils_libvirt.libvirt_config import remove_key_for_modular_daemon


# Migration flags
VIR_MIGRATE_LIVE = (1 << 0)
VIR_MIGRATE_PEER2PEER = (1 << 1)
VIR_MIGRATE_TUNNELLED = (1 << 2)
VIR_MIGRATE_COMPRESSED = (1 << 3)
VIR_MIGRATE_AUTO_CONVERGE = (1 << 4)
VIR_MIGRATE_POSTCOPY = (1 << 5)
VIR_MIGRATE_TLS = (1 << 6)
VIR_MIGRATE_PERSIST_DEST = (1 << 7)
VIR_MIGRATE_UNDEFINE_SOURCE = (1 << 8)
VIR_MIGRATE_PAUSED = (1 << 9)
VIR_MIGRATE_NON_SHARED_DISK = (1 << 10)
VIR_MIGRATE_NON_SHARED_INC = (1 << 11)
VIR_MIGRATE_ABORT_ON_ERROR = (1 << 12)
VIR_MIGRATE_PARALLEL = (1 << 13)
VIR_MIGRATE_PERSIST_DEST_XML = (1 << 14)
VIR_MIGRATE_DEST_XML = (1 << 15)

LOG = logging.getLogger('avocado.' + __name__)


# Phase of the migration test
class phase(Enum):
    SETUP = 1
    PRE_START_VM = 2
    START_VM = 3
    POST_START_VM = 4
    MIGRATE = 5
    POST_MIGRATE = 6
    MIGRATE_BACK = 7
    POST_MIGRATE_BACK = 8


CURRENT_PHASE = None


def set_phase(phase):
    """
    Set migration test phase

    :param phase: Enum value, phase to be set
    """
    global CURRENT_PHASE
    LOG.info("Entering phase: %s", phase.name)
    CURRENT_PHASE = phase


class Error(Exception):
    """
    Base error for migration test
    """

    def __str__(self):
        return ('Error in phase %s:\n' % CURRENT_PHASE.name)


class MigrationTemplate(object):
    """
    Migration template class for cross feature testing

    :param uri_type: hypervisor usr type, default to "qemu_system"
    :param migrate_desturi_proto: protocol in desturi, default to "tcp"
    :param virsh_migrate_options: virsh options for migration,
         default to "--p2p --live"
    :param persistdest: whether to add extra migrate option "--persistent",
         bool type, default to False
    :param undefinesource: whether to add extra migrate option "--undefinesource"
         bool type, default to False
    :param suspend: whether to add extra migrate option "--suspend"
         bool type, default to False
    :param copy_storage_all: whether to add extra migrate option "--copy-storage-all"
         bool type, default to False
    :param copy_storage_inc: whether to add extra migrate option "--copy-storage-inc"
         bool type, default to False
    :param compressed: whether to add extra migrate option "--compressed"
         bool type, default to False
    :param compressed_methods: extra migrate option "--comp-methods"
         string type, comma separated, e.g. "mt,xbzrle"
    :param compressed_mt_level: extra migrate option "--comp-mt-level"
         int type
    :param compressed_mt_threads: extra migrate option "--comp-mt-threads"
         int type
    :param compressed_mt_dthreads: extra migrate option "--comp-mt-dthreads"
         int type
    :param compressed_xbzrle: extra migrate option "--comp-xbzrle-cache"
         int type, unit in byte
    :param abort_on_error: whether to add extra migrate option "--abort-on-error",
         bool type, default to False
    :param auto_converge: whether to add extra migrate option "--auto-converge"
         bool type, default to False
    :param auto_converge_initial: extra migrate option "--auto-converge-initial"
         int type
    :param auto_converge_inc: extra migrate option "--auto-converge-increment"
         int type
    :param postcopy: whether to do postcopy migration,
         bool type, default to False
    :param native_tls: whether to add extra migrate option "--tls",
         bool type, default to False
    :param parallel: whether to add extra migrate option "--parallel",
         bool type, default to False
    :param parallel_conn: extra migrate option "--parallel-connections",
         int type
    :param migrateuri: extra migrate option "--migrateuri",
         string type
    :param listenaddress: extra migrate option "--listen-address",
         string type
    :param dest_xml: whether to add extra migrate option "--xml",
         bool type, default to False
    :param dest_persist_xml: whether to add extra migrate option "--persistent-xml"
         bool type, default to False
    :param migrate_thread_timeout: migration thread timeout, default to 900s
    :param migrate_vm_back: whether to migrate vm back to src
    :param migrate_main_vm: main vm for migration,
         default to "avocado-vt-vm1"
    :param migrate_vms': additional vms for migration, default to ""
    :param storage_type: vm disk storage type, currently supported type:
         1) nfs
         2) None(it means storage_type isn't set, vm disk source won't be changed)
    :param nfs_mount_dir: mount dir if storage type is nfs
    :param local_ip: local host ip address
    :param remote_ip: remote host ip address
    :param remote_user: username used to login remote host
    :param remote_pwd: password used to log in remote host
    :param migrate_source_host_cn: migrate source host's hostname
    :param migrate_source_host: migrate source host's ip address
         Note: migrate source host should be local host
    :param migrate_source_pwd: password used to login migrate source host
    :param migrate_dest_host_cn: migrate dest host's hostname
    :param migrate_dest_host: migrate dest host's ip address
    :param migrate_dest_pwd: password used to login migrate dest host

    Example:
      ::
      class MigrationWithVTPM(MigrationTemplate):
          def _install_swtpm_on_host(self):
              pass
          def _check_tpm(self):
              pass
          def _pre_start_vm(self):
              self._install_swtpm_on_host()
          def _post_start_vm(self):
              self._check_tpm(self)
          def _post_migrate(self):
              self._check_tpm(self)
          def _post_migrate_back(self):
              self._check_tpm(self)
      migrationobj = MigrationWithVTPM(test, params, env)
      try:
          migrationobj.runtest()
      finally:
          migraitonobj.cleanup()

    """

    def __init__(self, test, env, params, *args, **dargs):
        """
        Init params and other necessary variables
        """
        for k, v in iteritems(dict(*args, **dargs)):
            params[k] = v
        self.params = params
        self.test = test
        self.env = env

        # Check whether there are unset parameters
        for v in list(itervalues(self.params)):
            if isinstance(v, string_types) and v.count("EXAMPLE"):
                self.test.cancel("Please set real value for %s" % v)

        # Initiate the params
        self.uri_type = params.get("uri_type", "qemu_system")
        self.migrate_desturi_proto = params.get("migrate_desturi_proto", "tcp")
        self.virsh_migrate_options = params.get("virsh_migrate_options",
                                                "--live --p2p")
        self.persistdest = params.get("persistdest")
        self.undefinesource = params.get("undefinesource")
        self.suspend = params.get("suspend")
        self.copy_storage_all = params.get("copy_storage_all")
        self.copy_storage_inc = params.get("copy_storage_inc")
        self.compressed = params.get("compressed")
        self.compressed_methods = params.get("compressed_methods")
        self.compressed_mt_level = params.get("compressed_mt_level")
        self.compressed_mt_threads = params.get("compressed_mt_threads")
        self.compressed_mt_dthreads = params.get("compressed_mt_dthreads")
        self.compressed_xbzrle_cache = params.get("compressed_xbzrle_cache")
        self.abort_on_error = params.get("abort_on_error")
        self.auto_converge = params.get("auto_converge")
        self.auto_converge_initial = params.get("auto_converge_initial")
        self.auto_converge_inc = params.get("auto_converge_inc")
        self.postcopy = params.get("postcopy")
        self.native_tls = params.get("native_tls")
        self.parallel = params.get("parallel")
        self.parallel_conn = params.get("parallel_conn")
        self.migrateuri = params.get("migrateuri")
        self.listenaddress = params.get("listenaddress")
        self.dest_xml = params.get("dest_xml")
        self.dest_persist_xml = params.get("dest_persist_xml")

        self.migrate_thread_timeout = int(
                params.get("migrate_thread_timeout", "900")
                )
        self.migrate_vm_back = params.get("migrate_vm_back", "yes")
        self.migrate_main_vm_name = params.get("migrate_main_vm",
                                               "avocado-vt-vm1")
        self.migrate_vms_name = params.get("migrate_vms", "")
        self.storage_type = params.get("storage_type")
        self.nfs_mount_dir = params.get("nfs_mount_dir")
        self.local_ip = params.get("local_ip")
        self.remote_ip = params.get('remote_ip')
        self.remote_user = params.get('remote_user')
        self.remote_pwd = params.get('remote_pwd')
        self.migrate_source_host_cn = params.get("migrate_source_host_cn")
        self.migrate_source_host = params.get("migrate_source_host")
        self.migrate_source_pwd = params.get('migrate_source_pwd')
        self.migrate_dest_host_cn = params.get("migrate_dest_host_cn")
        self.migrate_dest_host = params.get("migrate_dest_host")
        self.migrate_dest_pwd = params.get('migrate_dest_pwd')
        self.selinux_state = params.get("selinux_state", "enforcing")

        # Set libvirtd remote access port
        self.remote_port = None
        remote_port_dict = {'tls': '16514', 'tcp': '16509'}
        self.remote_port = remote_port_dict.get(self.migrate_desturi_proto)

        # Set migration src and dest uri
        self.dest_uri = get_uri(self.uri_type,
                                self.migrate_desturi_proto,
                                (self.migrate_dest_host_cn
                                    if self.migrate_dest_host_cn
                                    else self.migrate_dest_host)
                                )
        self.src_uri = get_uri(self.uri_type)
        self.src_uri_full = get_uri(self.uri_type,
                                    self.migrate_desturi_proto,
                                    (self.migrate_source_host_cn
                                        if self.migrate_source_host_cn
                                        else self.migrate_source_host)
                                    )

        # Set virsh migrate options
        self.virsh_migrate_options += self._extra_migrate_options()

        # Set migrate flags
        self.migrate_flags = self._migrate_flags()

        # Remote dict
        self.remote_dict = {'server_ip': self.remote_ip,
                            'server_user': self.remote_user,
                            'server_pwd': self.remote_pwd}

        # Create a session to remote host
        self.remote_session = remote.wait_for_login('ssh', self.remote_ip,
                                                    '22', self.remote_user,
                                                    self.remote_pwd,
                                                    r"[\#\$]\s*$")
        # Get vm objects
        self.vms = []
        self.main_vm = env.get_vm(self.migrate_main_vm_name.strip())
        if not self.main_vm:
            self.test.error("Can't get vm object for vm: %s",
                            self.migrate_main_vm_name)
        self.vms.append(self.main_vm)
        for vm_name in self.migrate_vms_name.split():
            if vm_name != self.migrate_main_vm_name.strip():
                vm = env.get_vm(vm_name)
                if not vm:
                    self.test.error("Can't get vm object for vm: %s", vm_name)
                self.vms.append(vm)

        # Get a migration object
        self.obj_migration = migration.MigrationTest()

        # Variable: vm xml backup for vms recovery
        self.vm_xml_backup = []

        # Variable: conf files objects to be restored in cleanup()
        self.local_conf_objs = []
        self.remote_conf_objs = []

        # Variable: objects(ssh, tls and tcp, etc) to be cleaned up in cleanup()
        self.objs_list = []

        # Variable: enabled firewalld port lists on local host
        self.opened_ports_local = []

        # Variable: enabled firewalld port lists on remote host
        self.opened_ports_remote = []

    def runtest(self):
        """
        Run test with following processes:
        1. _setup_common():
            Common setup for migration test.
        2. _pre_start_vm():
            Operations before vm starts according to your test requirements.
            Subclasses must implement this method.
        3. _start_vm():
            Start vm and wait for it to fully boot up
        4. _post_start_vm():
            Operations after vm starts according your test requirements.
            Subclasses must implement this method.
        5. _migrate():
            Do migration and check migration result
        6. _post_migrate():
            Operations after migration according to your test requirements
            Subclasses must implement this method.
        7. _migrate_back():
            Migrate vm back and check migration result if migrate_vm_back='yes'
        8. _post_migrate_back():
            Operations after migration back according to your test requirements
            Subclasses must implement this method.
        """

        set_phase(phase.SETUP)
        self._setup_common()
        set_phase(phase.PRE_START_VM)
        self._pre_start_vm()
        set_phase(phase.START_VM)
        self._start_vm()
        set_phase(phase.POST_START_VM)
        self._post_start_vm()
        set_phase(phase.MIGRATE)
        self._migrate()
        set_phase(phase.POST_MIGRATE)
        self._post_migrate()
        if self.migrate_vm_back == "yes":
            set_phase(phase.MIGRATE_BACK)
            self._migrate_back()
            set_phase(phase.POST_MIGRATE_BACK)
            self._post_migrate_back()

    def _setup_common(self):
        """
        Common setup for migration test
        e.g. backup vm xml, cleanup vm, set shared disk in vmxml,
             setup host env, etc
        """

        # Setup for modular daemon
        self._setup_for_modular_daemon()

        # Back up vm xml for recovery
        LOG.debug("Backup vm xml before migration")
        for vm in self.vms:
            backup = vm_xml.VMXML.new_from_inactive_dumpxml(vm.name)
            if not backup:
                self.test.error("Backing up xmlfile failed for vm %s",
                                vm.name)
            self.vm_xml_backup.append(backup)

        # Destroy vm on src host if it's alive
        LOG.debug("Destroy vm on src host")
        for vm in self.vms:
            if vm.is_alive():
                vm.destroy()

        # Do migration pre-setup
        LOG.debug("Do migration pre-setup")
        self.obj_migration.migrate_pre_setup(self.dest_uri, self.params)
        if self.migrate_vm_back == 'yes':
            LOG.debug("Do migration pre-setup for migrate back")
            self.obj_migration.migrate_pre_setup(self.src_uri, self.params)

        # Setup libvirtd remote access env
        self._setup_libvirtd_remote_access()

        # Clean up vm on dest host
        LOG.debug("Clean up vm on dest host before migration")
        for vm in self.vms:
            self.obj_migration.cleanup_dest_vm(vm, self.src_uri, self.dest_uri)

        # Setup qemu tls env for native encrypted migration
        if self.migrate_flags & VIR_MIGRATE_TLS:
            self._setup_qemu_tls()

        # Set vm disk in vm xml
        if self.storage_type:
            self._set_vm_disk()

    def _pre_start_vm(self):
        """
        Operations before vm starts according to your test requirement
        e.g. set vm xml, env setup of your feature, etc
        """
        raise NotImplementedError

    def _start_vm(self):
        """
        Start vm and wait for it to fully boot up
        """

        for vm in self.vms:
            LOG.debug("Start vm %s.", vm.name)
            vm.start()

        # Make sure vm fully boots up
        for vm in self.vms:
            vm.wait_for_login(serial=True).close()

    def _post_start_vm(self):
        """
        Operations after vm starts according your test requirements,
        e.g.hotplug device, check vm xml, check device in vm, etc
        """
        raise NotImplementedError

    def _migrate(self):
        """
        0.Create disk image on dest host
        1.Set --xml and --persistent-xml in migrate options
        2.Set selinux state
        3.Record vm uptime
        4.For postcopy migration:
            1) Set migration speed to low value
            2) Monitor postcopy event
        5.Do live migration
        6.Check migration result: succeed or fail with expected error
        7.For postcopy migration: check postcopy event
        8.Do post migration check: check vm state, uptime, network
        """
        # Create disk image on dest host if --copy-storage-all/inc is used
        if self.migrate_flags & (VIR_MIGRATE_NON_SHARED_DISK | VIR_MIGRATE_NON_SHARED_INC):
            self._create_disk_image_on_dest()

        # Set xml file path for --xml and --persistent-xml in migrate options
        self._update_xmlfile_path_in_migrate_options()

        # Set selinux state before migration
        # NOTE: if selinux state is set too early, it may be changed
        # in other methods unexpectedly, so set it just before migration
        LOG.debug("Set selinux to enforcing before migration")
        utils_selinux.set_status(self.selinux_state)
        # TODO: Set selinux on migrate_dest_host

        # Check vm uptime before migration
        LOG.debug("Check vm uptime before migration")
        self.uptime = {}
        for vm in self.vms:
            self.uptime[vm.name] = vm.uptime(connect_uri=vm.connect_uri)

        # Do postcopy/precopy related operations/setting
        if self.migrate_flags & VIR_MIGRATE_POSTCOPY:
            # Set migration speed to low value in case it finished too early
            # before postcopy mode starts
            for vm in self.vms:
                virsh.migrate_setspeed(vm.name, 1, uri=vm.connect_uri)

            # Monitor event "Suspended Post-copy" for postcopy migration
            LOG.debug("Monitor the event for postcopy migration")
            virsh_session = virsh.VirshSession(virsh_exec=virsh.VIRSH_EXEC,
                                               auto_close=True)
            self.objs_list.append(virsh_session)
            cmd = "event %s --loop --all --timestamp" % self.main_vm.name
            virsh_session.sendline(cmd)

            # Set func to be executed during postcopy migration
            func = virsh.migrate_postcopy
        else:
            # Set func to be executed during precopy migration
            func = None

        # Start to do migration
        LOG.debug("Start to do migration")
        thread_timeout = self.migrate_thread_timeout
        self.obj_migration.do_migration(self.vms, self.src_uri,
                                        self.dest_uri, "orderly",
                                        options=self.virsh_migrate_options,
                                        thread_timeout=thread_timeout,
                                        ignore_status=True,
                                        virsh_uri=self.src_uri,
                                        func=func, shell=True)

        LOG.info("Check migration result: succeed or fail with expected error")
        self.obj_migration.check_result(self.obj_migration.ret, self.params)

        # Check "suspended post-copy" event after postcopy migration
        if self.migrate_flags & VIR_MIGRATE_POSTCOPY:
            LOG.debug("Check event after postcopy migration")
            virsh_session.send_ctrl("^c")
            events_output = virsh_session.get_stripped_output()
            LOG.debug("Events_output are %s", events_output)
            pattern = "Suspended Post-copy"
            if pattern not in events_output:
                self.test.error("Migration didn't switch to postcopy mode")

        LOG.debug("Do post migration check after migrate to dest")
        self.params["migrate_options"] = self.virsh_migrate_options
        self.obj_migration.post_migration_check(self.vms, self.params,
                                                self.uptime, uri=self.dest_uri)

    def _post_migrate(self):
        """
        Operations after migration according to your test requirements
        e.g. check domain xml, check device in vm, etc
        """
        raise NotImplementedError

    def _migrate_back(self):
        """
        1.Record vm uptime
        2.Migrate vm back to src host
        3.Check migration result: succeed or fail with expected error
        4.Do post migration check: check vm state, uptime, network
        """
        # Check vm uptime before migration back
        LOG.debug("Check vm uptime before migrate back")
        self.uptime = {}
        for vm in self.vms:
            self.uptime[vm.name] = vm.uptime(connect_uri=vm.connect_uri)

        # Migrate vm back to src host
        LOG.debug("Start to migrate vm back to src host")
        self.obj_migration.do_migration(self.vms, self.dest_uri,
                                        self.src_uri_full, "orderly",
                                        options=self.virsh_migrate_options,
                                        thread_timeout=self.migrate_thread_timeout,
                                        ignore_status=True,
                                        virsh_uri=self.dest_uri,
                                        shell=True)

        LOG.info("Check migration result: succeed or fail with expected error")
        self.obj_migration.check_result(self.obj_migration.ret, self.params)

        # Set vm connect_uri to self.src_uri if migration back succeeds
        if self.obj_migration.ret.exit_status == 0:
            for vm in self.vms:
                vm.connect_uri = self.src_uri

        LOG.debug("Do post migration check after migrate back to src")
        self.obj_migration.post_migration_check(self.vms, self.params,
                                                self.uptime, uri=self.src_uri)

    def _post_migrate_back(self):
        """
        Operations after migration according to your requirements
        e.g. check domain xml, check device in vm, etc
        """
        raise NotImplementedError

    def _extra_migrate_options(self):
        """
        Generate extra virsh migrate options

        :return extra migrate options, string type
        """

        LOG.info("Generate extra virsh migrate options")

        options = self.virsh_migrate_options
        extra_options = ""

        if self.persistdest and "--persistent" not in options:
            extra_options += " --persistent"
        if self.undefinesource and "--undefinesource" not in options:
            extra_options += " --undefinesource"
        if self.suspend and "--suspend" not in options:
            extra_options += " --suspend"
        if self.copy_storage_all and "--copy-storage-all" not in options:
            extra_options += " --copy-storage-all"
        if self.copy_storage_inc and "--copy-storage-inc" not in options:
            extra_options += " --copy-storage-inc"
        if self.compressed and "--compressed" not in options:
            extra_options += " --compressed"
        if self.compressed_methods and "--comp-methods" not in options:
            extra_options += " --comp-methods %s" % self.compressed_methods
        if self.compressed_mt_level and "--comp-mt-level" not in options:
            extra_options += " --comp-mt-level %s" % self.compressed_mt_level
        if self.compressed_mt_threads and "--comp-mt-threads" not in options:
            extra_options += " --comp-mt-threads %s" % self.compressed_mt_threads
        if self.compressed_mt_dthreads and "--comp-mt-dthreads" not in options:
            extra_options += " --comp-mt-dthreads %s" % self.compressed_mt_dthreads
        if self.compressed_xbzrle_cache and "--comp-xbzrle-cache" not in options:
            extra_options += " --comp-xbzrle-cache %s" % self.compressed_xbzrle_cache
        if self.abort_on_error and "--abort-on-error" not in options:
            extra_options += " --abort-on-error"
        if self.auto_converge and "--auto-converge" not in options:
            extra_options += " --auto-converge"
        if self.auto_converge_initial and "--auto-converge-initial" not in options:
            extra_options += " --auto-converge-initial %s" % self.auto_converge_initial
        if self.auto_converge_inc and "--auto-converge-increment" not in options:
            extra_options += " --auto-converge-increment %s" % self.auto_converge_inc
        if self.postcopy and "--postcopy" not in options:
            extra_options += " --postcopy"
        if self.native_tls and "--tls" not in options:
            extra_options += " --tls"
        if self.parallel and "--parallel" not in options:
            extra_options += " --parallel"
        if self.parallel_conn and "--parallel-connections" not in options:
            extra_options += " --parallel-connections %s" % self.parallel_conn
        if self.migrateuri and "--migrateuri" not in options:
            extra_options += " --migrateuri %s" % self.migrateuri
        if self.listenaddress and "--listen-address" not in options:
            extra_options += " --listen-address %s" % self.listenaddress
        if self.dest_xml and "--xml" not in options:
            extra_options += " --xml DEST_XML"
        if self.dest_persist_xml and "--persistent-xml" not in options:
            extra_options += " --persistent-xml DEST_PERSIST_XML"

        LOG.debug("Extra migrate options is: %s", extra_options)
        return extra_options

    def _update_xmlfile_path_in_migrate_options(self):
        """
        Generate and replace the xml file path for --xml and/or --persistent-xml

        """
        LOG.info("Generate and replace xml file path for --xml and/or --persistent-xml")

        new_options = self.virsh_migrate_options

        if self.migrate_flags & VIR_MIGRATE_DEST_XML:
            vmxml_path = vm_xml.VMXML.new_from_dumpxml(self.main_vm.name,
                                                       "--security-info --migratable")
            new_options = new_options.replace("DEST_XML", vmxml_path)

        if self.migrate_flags & VIR_MIGRATE_PERSIST_DEST_XML:
            vmxml_path = vm_xml.VMXML.new_from_dumpxml(self.main_vm.name,
                                                       "--security-info --migratable")
            new_options = new_options.replace("DEST_PERSIST_XML", vmxml_path)

        self.virsh_migrate_options = new_options

    def _migrate_flags(self):
        """
        Generate migrate flags

        :return migrate flag
        """

        LOG.info("Generate migrate flags")

        flags = 0

        if "--live" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_LIVE
        if "--p2p" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_PEER2PEER
        if "--persistent" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_PERSIST_DEST
        if "--undefinesource" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_UNDEFINE_SOURCE
        if "--suspend" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_PAUSED
        if "--copy-storage-all" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_NON_SHARED_DISK
        if "--copy-storage-inc" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_NON_SHARED_INC
        if "--compressed" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_COMPRESSED
        if "--abort-on-error" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_ABORT_ON_ERROR
        if "--auto-converge" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_AUTO_CONVERGE
        if "--postcopy" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_POSTCOPY
        if "--tls" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_TLS
        if "--parallel" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_PARALLEL
        if self.dest_xml:
            flags |= VIR_MIGRATE_DEST_XML
        if self.dest_persist_xml:
            flags |= VIR_MIGRATE_PERSIST_DEST_XML

        LOG.debug("Migrate flags is: %s", flags)
        return flags

    def _setup_for_modular_daemon(self):
        """
        Setup env for modular daemon
        """

        LOG.info("Setup env for modular daemon")
        self._set_libvirt_conf_for_modular_daemon()

    def _set_libvirt_conf_for_modular_daemon(self):
        """
        Set /etc/libvirt/libvirt.conf for modular daemon
        """

        if self.migrate_desturi_proto == "ssh":
            LOG.info("Set libvirt.conf for modular daemon if \
                    migrate_desturi_proto is ssh")
            params = {}
            LOG.info("Setup src libvirt.conf for modular daemon")
            conf_obj = remove_key_for_modular_daemon(params)
            self.local_conf_objs.append(conf_obj)
            if self.migrate_vm_back == "yes":
                LOG.info("Setup dest libvirt.conf for modular daemon")
                remote_dict = dict(self.remote_dict)
                remote_dict.update(file_path="/etc/libvirt/libvirt.conf")
                conf_obj = remove_key_for_modular_daemon(params, remote_dict)
                self.remote_conf_objs.append(conf_obj)

    def _set_vm_disk(self, cache="none"):
        """
        Set vm disk in vm xml, only support nfs storage for now

        :param cache: vm disk cache mode
        """
        LOG.debug("Prepare shared disk in vm xml for live migration")
        if self.storage_type == 'nfs':
            LOG.debug("Prepare nfs backed disk in vm xml")
            for vm in self.vms:
                libvirt.update_vm_disk_source(vm.name,
                                              self.nfs_mount_dir)
                libvirt.update_vm_disk_driver_cache(vm.name,
                                                    driver_cache=cache)
        else:
            # TODO:other storage types
            self.test.cancel("Only nfs storage is supported for now")

    def _create_disk_image_on_dest(self):
        """
        Create disk image on dest host before migration
        Used for live vm migration with disk copy

        Note:
        This method doesn't handle the backing chain setup. So you need to setup
        the disk image backing chain by yourself if --copy-storage-inc is used

        """
        LOG.debug("Create disk image on dest host before migration")
        all_vm_disks = self.main_vm.get_blk_devices()
        for disk in list(itervalues(all_vm_disks)):
            disk_type = disk.get("type")
            disk_path = disk.get("source")
            image_info = utils_misc.get_image_info(disk_path)
            disk_size = image_info.get("vsize")
            disk_format = image_info.get("format")
            utils_misc.make_dirs(os.path.dirname(disk_path),
                                 self.remote_session)
            libvirt_disk.create_disk(disk_type, path=disk_path,
                                     size=disk_size, disk_format=disk_format,
                                     session=self.remote_session)

    def _setup_libvirtd_remote_access(self):
        """
        Setup libvirtd remote access env for migration
        """
        LOG.debug("Setup libvirtd remote access env")
        protocol = self.migrate_desturi_proto
        self._setup_remote_connection_base(protocol, reverse=False)
        if self.migrate_vm_back == 'yes':
            LOG.debug("Setup libvirtd remote access env\
                          for reverse migration")
            tls_args = {}
            if protocol == 'tls':
                tls_args = {'ca_cakey_path': '/etc/pki/CA/',
                            'scp_new_cacert': 'no'}
            self._setup_remote_connection_base(protocol=protocol,
                                               reverse=True,
                                               add_args=tls_args)

        # Enable libvirtd remote access port in firewalld
        if self.remote_port:
            self.open_libvirtd_port_in_iptables()

    def _setup_qemu_tls(self):
        """
        Set up native encryption migration env
        """
        LOG.debug("Setup qemu tls env")
        tls_args = {'custom_pki_path': '/etc/pki/qemu',
                    'qemu_tls': 'yes'}
        self._setup_remote_connection_base(protocol='tls', add_args=tls_args)
        if self.migrate_vm_back == 'yes':
            LOG.debug("Setup qemu tls env for reverse migration")
            tls_args.update(ca_cakey_path=tls_args.get('custom_pki_path'))
            tls_args.update(scp_new_cacert='no')
            self._setup_remote_connection_base(protocol='tls',
                                               reverse=True,
                                               add_args=tls_args)

    def _setup_remote_connection_base(self, protocol='ssh', reverse=False,
                                      add_args={}):
        """
        Base function for setting up remote connection

        :param protocol: Protocol used for remote connection(ssh, tcp, tls)
        :param reverse: False for connection from src to dest
                        True for reverse connection
        :param add_args: Dict of additional args for Connection obj
        """
        if reverse:
            conn_args = {'client_ip': self.migrate_dest_host,
                         'client_cn': self.migrate_dest_host_cn,
                         'client_pwd': self.migrate_dest_pwd,
                         'server_ip': self.migrate_source_host,
                         'server_cn': self.migrate_source_host_cn,
                         'server_pwd': self.migrate_source_pwd}
        else:
            conn_args = {'server_ip': self.migrate_dest_host,
                         'server_cn': self.migrate_dest_host_cn,
                         'server_pwd': self.migrate_dest_pwd,
                         'client_ip': self.migrate_source_host,
                         'client_cn': self.migrate_source_host_cn,
                         'client_pwd': self.migrate_source_pwd}
        conn_args.update(add_args)

        protocol_to_class = {'tls': TLSConnection,
                             'tcp': TCPConnection,
                             'ssh': SSHConnection}

        LOG.debug("Setup remote connection env")
        conn_obj = protocol_to_class[protocol](conn_args)
        conn_obj.conn_setup()
        conn_obj.auto_recover = True
        self.objs_list.append(conn_obj)

    def open_libvirtd_port_in_iptables(self, cleanup=False):
        """
        Enable libvirtd remote access port in iptables

        :param cleanup: False to enable port, True to disable port
        """

        def _open_libvirtd_port_in_iptables(server_ip, cleanup):
            """
            Enable libvirtd remote access port in iptables on specified server

            :param server_ip: The ip address of server
            """
            server_dict = None
            session = None
            if server_ip == self.remote_ip:
                server_dict = self.remote_dict
                session = self.remote_session
            self.open_port_in_iptables(self.remote_port,
                                       server_dict=server_dict,
                                       session=session, cleanup=cleanup)

        LOG.debug("Enable libvirtd remote port in firewalld on dst host")
        _open_libvirtd_port_in_iptables(self.migrate_dest_host, cleanup)
        if self.migrate_vm_back == 'yes':
            LOG.debug("Enable libvirtd remote port in firewalld\
                           on src host")
            _open_libvirtd_port_in_iptables(self.migrate_source_host, cleanup)

    def open_port_in_iptables(self, port, protocol='tcp', server_dict=None,
                              session=None, cleanup=False):
        """
        Open port in iptables

        :param ports: port to be opened, these formats are supported for now:
                      1)4567 2)4567-4587 3)4567:4587
        :param protocl: protocol to be opened: 'tcp'|'udp'|'sctp'|'dccp'
        :param server_dict: dict to create server session:
                            {server_ip, server_user, server_pwd}
        :param session: session of server to open ports on, None to local host
        :param cleanup: True to cleanup instead of opening port
        """
        # Check whether firewall-cmd is available
        use_firewall_cmd = distro.detect().name != "Ubuntu"
        iptables_func = utils_iptables.Iptables.setup_or_cleanup_iptables_rules
        try:
            utils_path.find_command("firewall-cmd")
        except utils_path.CmdNotFoundError:
            LOG.debug("Using iptables for replacement")
            use_firewall_cmd = False

        if use_firewall_cmd:
            firewall_cmd = utils_iptables.Firewall_cmd(session)

            if ":" in port:
                port = "%s-%s" % (port.split(":")[0], port.split(":")[1])

            # open ports using firewall_cmd
            if cleanup:
                firewall_cmd.remove_port(port, protocol, permanent=True)
            else:
                firewall_cmd.add_port(port, protocol, permanent=True)
        else:
            if "-" in port:
                port = "%s:%s" % (port.split("-")[0], port.split("-")[1])

            # open migration ports in remote machine using iptables
            rule = ["INPUT -p %s -m %s --dport %s -j ACCEPT" % (protocol,
                                                                protocol,
                                                                port)]
            iptables_func(rule, params=server_dict, cleanup=cleanup)

        if not cleanup:
            if session:
                self.opened_ports_remote.append(port)
            else:
                self.opened_ports_local.append(port)

    def cleanup(self):
        """
        Cleanup env
        """
        LOG.info("Start to clean up env")

        undef_opts = "--managed-save --snapshots-metadata"
        if libvirt_version.version_compare(7, 5, 0):
            undef_opts += " --checkpoints-metadata"

        # Destroy vms on src host(if vm is migrated back)\
        # or dest host(if vm is not migrated back)
        LOG.info("Remove vms on src or dest host")
        for vm in self.vms:
            try:
                vm.remove(undef_opts=undef_opts)
            except Exception as detail:
                LOG.warning("Failed to remove vm %s, detail: %s",
                            vm.name, detail)
                continue
            LOG.debug("Vm %s is removed", vm.name)

        # Need to undefine vms on src host(if vm is not migrated back)
        LOG.info("Undefine vms on src host")
        for backup in self.vm_xml_backup:
            try:
                backup.undefine(options=undef_opts)
            except Exception as detail:
                LOG.warning("Failed to undefine vm %s, detail: %s",
                            backup.vm_name, detail)
                continue
            LOG.debug("Vm %s is undefined", backup.vm_name)

        # Recover vm definition on src host
        LOG.info("Recover vm definition on source")
        for backup in self.vm_xml_backup:
            try:
                backup.define()
            except Exception as detail:
                LOG.warning("Failed to define vm %s, detail: %s",
                            backup.vm_name, detail)
                continue
            LOG.debug("Vm %s is restored", backup.vm_name)

        # Clean up ssh, tcp, tls test env
        if self.objs_list and len(self.objs_list) > 0:
            LOG.debug("Clean up test env: ssh, tcp, tls, etc")
            self.objs_list.reverse()
            for obj in self.objs_list:
                obj.__del__()

        # Cleanup migrate_pre_setup
        LOG.debug("Clean up migration setup on dest host")
        self.obj_migration.migrate_pre_setup(self.dest_uri, self.params,
                                             cleanup=True)
        if self.migrate_vm_back == 'yes':
            LOG.debug("Clean up migration setup on src host")
            self.obj_migration.migrate_pre_setup(self.src_uri, self.params,
                                                 cleanup=True)

        # Restore conf files
        LOG.debug("Restore conf files")
        for conf_obj in self.local_conf_objs:
            conf_obj.restore()
        for conf_obj in self.remote_conf_objs:
            del conf_obj

        # Disable opened ports in firewalld
        for port in self.opened_ports_local:
            LOG.debug("Disable port %s in firewalld on local host", port)
            self.open_port_in_iptables(port, cleanup=True)
        for port in self.opened_ports_remote:
            LOG.debug("Disable port %s in firewalld on remote host", port)
            self.open_port_in_iptables(port,
                                       server_dict=self.remote_dict,
                                       session=self.remote_session,
                                       cleanup=True)


def vm_session_handler(func):
    """
    Decorator method to handle session for vm

    :param func: func to be decorated, it must has VM object as first parameter
    """
    @functools.wraps(func)
    def manage_session(vm, *args, **kwargs):
        """
        Wrapper method of the decorator

        :param vm: VM object
        """
        LOG.debug("vm's connect_uri is: %s", vm.connect_uri)
        try:
            if vm.connect_uri == "qemu:///system":
                vm.session = vm.wait_for_login(serial=True)
            else:
                vm.session = vm.wait_for_serial_login()
            return func(vm, *args, **kwargs)
        finally:
            if vm.session:
                vm.session.close()
    return manage_session
