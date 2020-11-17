import logging
import functools

from enum import Enum

from six import itervalues, iteritems, string_types

from avocado.utils import distro
from avocado.utils import path as utils_path

from virttest import virsh, migration, remote
from virttest import utils_iptables, utils_selinux

from virttest.libvirt_xml import vm_xml

from virttest.libvirt_vm import get_uri_with_transport as get_uri

from virttest.utils_conn import TLSConnection, TCPConnection, SSHConnection

from virttest.utils_test import libvirt

from virttest.utils_libvirt.libvirt_config import remove_key_for_modular_daemon


# Migration flags
VIR_MIGRATE_LIVE = 1
VIR_MIGRATE_PEER2PEER = 2
VIR_MIGRATE_TUNNELLED = 4
VIR_MIGRATE_COMPRESSED = 8
VIR_MIGRATE_AUTO_CONVERGE = 16
VIR_MIGRATE_POSTCOPY = 32
VIR_MIGRATE_TLS = 64
VIR_MIGRATE_PERSIST_DEST = 128
VIR_MIGRATE_UNDEFINE_SOURCE = 256


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
    logging.info("Entering phase: %s", phase.name)
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
    :param tunnelled: whether to do tunnelled migration, default to False
    :param compressed: whether to do compressed migration, default to False
    :param auto_converge: whether to do auto_converge migration,
         default to False
    :parma postcopy: whether to do postcopy migration, default to False
    :param native_tls: whether to do encrypted migration, default to False
    :param persistdest: whether to define vm on dest host during migration,
         default to False
    :param undefinesource: whether to undefine vm on src host during migration,
         default to False
    :param migrate_thread_timeout: migration thread timeout, default to 900s
    :param migrate_vm_back: whether to migrate vm back to src
    :param migrate_main_vm: main vm for migration,
         default to "avocado-vt-vm1"
    :param migrate_vms': additional vms for migration, default to ""
    :param storage_type: vm disk storage type
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
        self.tunnelled = params.get("tunnelled", False)
        self.compressed = params.get("compressed", False)
        self.auto_converge = params.get("auto_converge", False)
        self.postcopy = params.get("postcopy", False)
        self.native_tls = params.get("native_tls", False)
        self.persistdest = params.get("persistdest", False)
        self.undefinesource = params.get("undefinesource", False)
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
        logging.debug("Backup vm xml before migration")
        for vm in self.vms:
            backup = vm_xml.VMXML.new_from_inactive_dumpxml(vm.name)
            if not backup:
                self.test.error("Backing up xmlfile failed for vm %s",
                                vm.name)
            self.vm_xml_backup.append(backup)

        # Destroy vm on src host if it's alive
        logging.debug("Destroy vm on src host")
        for vm in self.vms:
            if vm.is_alive():
                vm.destroy()

        # Do migration pre-setup
        logging.debug("Do migration pre-setup")
        self.obj_migration.migrate_pre_setup(self.dest_uri, self.params)
        if self.migrate_vm_back == 'yes':
            logging.debug("Do migration pre-setup for migrate back")
            self.obj_migration.migrate_pre_setup(self.src_uri, self.params)

        # Setup libvirtd remote access env
        self._setup_libvirtd_remote_access()

        # Clean up vm on dest host
        logging.debug("Clean up vm on dest host before migration")
        for vm in self.vms:
            self.obj_migration.cleanup_dest_vm(vm, self.src_uri, self.dest_uri)

        # Setup qemu tls env for native encrypted migration
        if self.migrate_flags & VIR_MIGRATE_TLS:
            self._setup_qemu_tls()

        # Set vm disk in vm xml
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
            logging.debug("Start vm %s.", vm.name)
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
        1.Set selinux state
        2.Record vm uptime
        3.For postcopy migration:
            1) Set migration speed to low value
            2) Monitor postcopy event
        4.Do live migration
        5.Check migration result: succeed or fail with expected error
        6.For postcopy migration: check postcopy event
        7.Do post migration check: check vm state, uptime, network
        """
        # Set selinux state before migration
        # NOTE: if selinux state is set too early, it may be changed
        # in other methods unexpectedly, so set it just before migration
        logging.debug("Set selinux to enforcing before migration")
        utils_selinux.set_status(self.selinux_state)
        # TODO: Set selinux on migrate_dest_host

        # Check vm uptime before migration
        logging.debug("Check vm uptime before migration")
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
            logging.debug("Monitor the event for postcopy migration")
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
        logging.debug("Start to do migration")
        thread_timeout = self.migrate_thread_timeout
        self.obj_migration.do_migration(self.vms, self.src_uri,
                                        self.dest_uri, "orderly",
                                        options=self.virsh_migrate_options,
                                        thread_timeout=thread_timeout,
                                        ignore_status=True,
                                        virsh_uri=self.src_uri,
                                        func=func, shell=True)

        logging.info("Check migration result: succeed or"
                     " fail with expected error")
        self.obj_migration.check_result(self.obj_migration.ret, self.params)

        # Check "suspended post-copy" event after postcopy migration
        if self.migrate_flags & VIR_MIGRATE_POSTCOPY:
            logging.debug("Check event after postcopy migration")
            virsh_session.send_ctrl("^c")
            events_output = virsh_session.get_stripped_output()
            logging.debug("Events_output are %s", events_output)
            pattern = "Suspended Post-copy"
            if pattern not in events_output:
                self.test.error("Migration didn't switch to postcopy mode")

        logging.debug("Do post migration check after migrate to dest")
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
        logging.debug("Check vm uptime before migrate back")
        self.uptime = {}
        for vm in self.vms:
            self.uptime[vm.name] = vm.uptime(connect_uri=vm.connect_uri)

        # Migrate vm back to src host
        logging.debug("Start to migrate vm back to src host")
        self.obj_migration.do_migration(self.vms, self.dest_uri,
                                        self.src_uri_full, "orderly",
                                        options=self.virsh_migrate_options,
                                        thread_timeout=self.migrate_thread_timeout,
                                        ignore_status=True,
                                        virsh_uri=self.dest_uri,
                                        shell=True)

        logging.info("Check migration result: succeed or"
                     " fail with expected error")
        self.obj_migration.check_result(self.obj_migration.ret, self.params)

        # Set vm connect_uri to self.src_uri if migration back succeeds
        if self.obj_migration.ret.exit_status == 0:
            for vm in self.vms:
                vm.connect_uri = self.src_uri

        logging.debug("Do post migration check after migrate back to src")
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

        logging.info("Generate extra virsh migrate options")

        options = self.virsh_migrate_options
        extra_options = ""

        if self.tunnelled and "--tunnelled" not in options:
            extra_options += " --tunnelled"
        if self.compressed and "--compressed" not in options:
            extra_options += " --compressed"
        if self.auto_converge and "--auto-converge" not in options:
            extra_options += " --auto-converge"
        if self.postcopy and "--postcopy" not in options:
            extra_options += " --postcopy"
        if self.native_tls and "--tls" not in options:
            extra_options += " --tls"
        if self.persistdest and "--persistent" not in options:
            extra_options += " --persistent"
        if self.undefinesource and "--undefinesource" not in options:
            extra_options += " --undefinesource"

        logging.debug("Extra migrate options is: %s", extra_options)
        return extra_options

    def _migrate_flags(self):
        """
        Generate migrate flags

        :return migrate flag
        """

        logging.info("Generate migrate flags")

        flags = 0

        if "--live" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_LIVE
        if "--p2p" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_PEER2PEER
        if "--tunnelled" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_TUNNELLED
        if "--compressed" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_COMPRESSED
        if "--auto-converge" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_AUTO_CONVERGE
        if "--postcopy" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_POSTCOPY
        if "--tls" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_TLS
        if "--persistent" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_PERSIST_DEST
        if "--undefinesource" in self.virsh_migrate_options:
            flags |= VIR_MIGRATE_UNDEFINE_SOURCE

        logging.debug("Migrate flags is: %s", flags)
        return flags

    def _setup_for_modular_daemon(self):
        """
        Setup env for modular daemon
        """

        logging.info("Setup env for modular daemon")
        self._set_libvirt_conf_for_modular_daemon()

    def _set_libvirt_conf_for_modular_daemon(self):
        """
        Set /etc/libvirt/libvirt.conf for modular daemon
        """

        if self.migrate_desturi_proto == "ssh":
            logging.info("Set libvirt.conf for modular daemon if \
                    migrate_desturi_proto is ssh")
            params = {}
            logging.info("Setup src libvirt.conf for modular daemon")
            conf_obj = remove_key_for_modular_daemon(params)
            self.local_conf_objs.append(conf_obj)
            if self.migrate_vm_back == "yes":
                logging.info("Setup dest libvirt.conf for modular daemon")
                remote_dict = dict(self.remote_dict)
                remote_dict.update(file_path="/etc/libvirt/libvirt.conf")
                conf_obj = remove_key_for_modular_daemon(params, remote_dict)
                self.remote_conf_objs.append(conf_obj)

    def _set_vm_disk(self, cache="none"):
        """
        Set vm disk in vm xml, only support nfs storage for now

        :param cache: vm disk cache mode
        """
        logging.debug("Prepare shared disk in vm xml for live migration")
        if self.storage_type:
            if self.storage_type == 'nfs':
                logging.debug("Prepare nfs backed disk in vm xml")
                for vm in self.vms:
                    libvirt.update_vm_disk_source(vm.name,
                                                  self.nfs_mount_dir)
                    libvirt.update_vm_disk_driver_cache(vm.name,
                                                        driver_cache=cache)
            else:
                # TODO:other storage types
                self.test.cancel("Only nfs storage is supported for now")

    def _setup_libvirtd_remote_access(self):
        """
        Setup libvirtd remote access env for migration
        """
        logging.debug("Setup libvirtd remote access env")
        protocol = self.migrate_desturi_proto
        self._setup_remote_connection_base(protocol, reverse=False)
        if self.migrate_vm_back == 'yes':
            logging.debug("Setup libvirtd remote access env\
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
        logging.debug("Setup qemu tls env")
        tls_args = {'custom_pki_path': '/etc/pki/qemu',
                    'qemu_tls': 'yes'}
        self._setup_remote_connection_base(protocol='tls', add_args=tls_args)
        if self.migrate_vm_back == 'yes':
            logging.debug("Setup qemu tls env for reverse migration")
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

        logging.debug("Setup remote connection env")
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

        logging.debug("Enable libvirtd remote port in firewalld on dst host")
        _open_libvirtd_port_in_iptables(self.migrate_dest_host, cleanup)
        if self.migrate_vm_back == 'yes':
            logging.debug("Enable libvirtd remote port in firewalld\
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
            logging.debug("Using iptables for replacement")
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
        logging.debug("Start to clean up env")
        # Shutdown vms
        for vm in self.vms:
            vm.destroy()

        # Recover source vm defination (just in case).
        logging.info("Recover vm defination on source")
        for backup in self.vm_xml_backup:
            backup.define()

        # Clean up ssh, tcp, tls test env
        if self.objs_list and len(self.objs_list) > 0:
            logging.debug("Clean up test env: ssh, tcp, tls, etc")
            self.objs_list.reverse()
            for obj in self.objs_list:
                obj.__del__()

        # Cleanup migrate_pre_setup
        logging.debug("Clean up migration setup on dest host")
        self.obj_migration.migrate_pre_setup(self.dest_uri, self.params,
                                             cleanup=True)
        if self.migrate_vm_back == 'yes':
            logging.debug("Clean up migration setup on src host")
            self.obj_migration.migrate_pre_setup(self.src_uri, self.params,
                                                 cleanup=True)

        # Restore conf files
        logging.debug("Restore conf files")
        for conf_obj in self.local_conf_objs:
            conf_obj.restore()
        for conf_obj in self.remote_conf_objs:
            del conf_obj

        # Disable opened ports in firewalld
        for port in self.opened_ports_local:
            logging.debug("Disable port %s in firewalld on local host", port)
            self.open_port_in_iptables(port, cleanup=True)
        for port in self.opened_ports_remote:
            logging.debug("Disable port %s in firewalld on remote host", port)
            self.open_port_in_iptables(port,
                                       server_dict=self.remote_dict,
                                       session=self.remote_session,
                                       cleanup=True)


def vm_session_handler(func):
    """
    Decorator method to handle sesssion for vm

    :param func: func to be decorated, it must has VM object as first paramter
    """
    @functools.wraps(func)
    def manage_session(vm, *args, **kwargs):
        """
        Wrapper method of the decorator

        :param vm: VM object
        """
        logging.debug("vm's connect_uri is: %s", vm.connect_uri)
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
