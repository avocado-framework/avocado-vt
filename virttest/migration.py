import time
import threading
import logging
import re
import signal

from avocado.utils import process
from avocado.utils import path as utils_path
from avocado.utils import distro
from avocado.core import exceptions

from virttest import remote
from virttest import virsh
from virttest import utils_misc
from virttest import test_setup
from virttest import utils_net
from virttest import utils_iptables
from virttest.utils_test import libvirt


# Migration Relative functions##############
class MigrationTest(object):

    """Class for migration tests"""

    def __init__(self):
        # To get result in thread, using member parameters
        # Result of virsh migrate command
        # True means command executed successfully
        self.RET_MIGRATION = True
        # A lock for threads
        self.RET_LOCK = threading.RLock()
        # The time spent when migrating vms
        # format: vm_name -> time(seconds)
        self.mig_time = {}
        # The CmdResult returned from virsh migrate command
        self.ret = None

    def post_migration_check(self, vms, params, uptime, uri=None):
        """
        Validating migration by performing checks in this method
        * uptime of the migrated vm > uptime of vm before migration
        * ping vm from target host
        * check vm state after migration

        :param vms: VM objects of migrating vms
        :param uptime: uptime dict of vms before migration
        :param uri: target virsh uri
        :return: updated dict of uptime
        """
        vm_state = params.get("virsh_migrated_state", "running")
        ping_count = int(params.get("ping_count", 10))
        for vm in vms:
            if not libvirt.check_vm_state(vm.name, vm_state, uri=uri):
                raise exceptions.TestFail("Migrated VMs failed to be in %s "
                                          "state at destination" % vm_state)
            logging.info("Guest state is '%s' at destination is as expected",
                         vm_state)
            if "offline" not in params.get("migrate_options"):
                vm_uptime = vm.uptime(connect_uri=uri)
                logging.info("uptime of migrated VM %s: %s", vm.name,
                             vm_uptime)
                if vm_uptime < uptime[vm.name]:
                    raise exceptions.TestFail("vm went for a reboot during "
                                              "migration")
                self.ping_vm(vm, params, uri=uri, ping_count=ping_count)
                # update vm uptime to check when migrating back
                uptime[vm.name] = vm_uptime
                vm.verify_dmesg(connect_uri=uri)
        return uptime

    def ping_vm(self, vm, params, uri=None, ping_count=10,
                ping_timeout=60):
        """
        Method used to ping the VM before and after migration

        :param vm: VM object
        :param params: Test dict params
        :param uri: connect uri
        :param ping_count: count of icmp packet
        :param ping_timeout: Timeout for the ping command
        """
        vm_ip = params.get("vm_ip_dict", {})
        server_session = None
        func = exceptions.TestError
        if uri and uri != "qemu:///system":
            func = exceptions.TestFail
            uri_backup = vm.connect_uri
            vm.connect_uri = uri
            server_session = test_setup.remote_session(params)
            # after migration VM would take some time to respond and to
            # avoid the race of framework querying IP address before VM
            # starts responding, provide timeout for 240 seconds to retry
            # and raise if VM fails to respond
            vm_ip[vm.name] = vm.get_address(session=server_session,
                                            timeout=240)
            logging.info("Check VM network connectivity after migrating")
        else:
            logging.info("Check VM network connectivity before migration")
            if not vm.is_alive():
                vm.start()
            vm.wait_for_login()
            vm_ip[vm.name] = vm.get_address()
            params["vm_ip_dict"] = vm_ip
        s_ping, o_ping = utils_net.ping(vm_ip[vm.name], count=ping_count,
                                        timeout=ping_timeout,
                                        output_func=logging.debug,
                                        session=server_session)
        logging.info(o_ping)
        if uri and uri != 'qemu:///system':
            vm.connect_uri = uri_backup
            if server_session:
                server_session.close()
        if s_ping != 0:
            if uri:
                if "offline" in params.get("migrate_options"):
                    logging.info("Offline Migration: %s will not responded to "
                                 "ping as expected", vm.name)
                    return
            func("%s did not respond after %d sec." % (vm.name, ping_timeout))

    def thread_func_migration(self, vm, desturi, options=None,
                              ignore_status=False, virsh_opt="",
                              extra_opts=""):
        """
        Thread for virsh migrate command.

        :param vm: A libvirt vm instance(local or remote).
        :param desturi: Remote host uri.
        :param options: The options for migration command.
        :param ignore_status: True, means no CmdError will be caught
                              for the failure.
                              False, means an CmdError will be caught
                              for the failure.
        """
        # Migrate the domain.
        is_error = False

        try:
            if options is None:
                options = "--live --timeout=60"
            stime = int(time.time())
            self.ret = vm.migrate(desturi, option=options,
                                  ignore_status=ignore_status,
                                  debug=True, virsh_opt=virsh_opt,
                                  extra=extra_opts)
            etime = int(time.time())
            self.mig_time[vm.name] = etime - stime
            if self.ret.exit_status != 0:
                logging.debug("Migration to %s returns failed exit status %d",
                              desturi, self.ret.exit_status)
                is_error = True
        except process.CmdError as detail:
            logging.error("Migration to %s failed:\n%s", desturi, detail)
            is_error = True
        finally:
            if is_error is True:
                self.RET_LOCK.acquire()
                self.RET_MIGRATION = False
                self.RET_LOCK.release()

    def migrate_pre_setup(self, desturi, params,
                          cleanup=False,
                          ports='49152:49216'):
        """
        # Setup before migration,
        # 1. To enable migration ports using iptables
        # 2. Turn off SMT for power8 machine in remote machine to migrate

        :param desturi: uri of destination machine to which VM gets migrated
        :param params: Test params dict
        :param cleanup: if True revert back to default setting, used to cleanup
        :param ports: ports used for allowing migration
        """
        use_firewall_cmd = distro.detect().name != "Ubuntu"
        iptables_func = utils_iptables.Iptables.setup_or_cleanup_iptables_rules
        try:
            utils_path.find_command("firewall-cmd")
        except utils_path.CmdNotFoundError:
            logging.debug("Using iptables for replacement")
            use_firewall_cmd = False

        if use_firewall_cmd:
            port_to_add = ports
            if ":" in ports:
                port_to_add = "%s-%s" % (ports.split(":")[0], ports.split(":")[1])
        else:
            rule = ["INPUT -p tcp -m tcp --dport %s -j ACCEPT" % ports]

        try:
            dest_ip = re.search(r'//.*/', desturi,
                                re.I).group(0).strip('/').strip()
            source_ip = params.get("migrate_source_host", "").strip()
            source_cn = params.get("migrate_source_host_cn", "").strip()
            # check whether migrate back to source machine or not
            if ((desturi == "qemu:///system") or (dest_ip == source_ip) or (dest_ip == source_cn)):
                if use_firewall_cmd:
                    firewall_cmd = utils_iptables.Firewall_cmd()
                    if cleanup:
                        firewall_cmd.remove_port(port_to_add, 'tcp', permanent=True)
                    else:
                        firewall_cmd.add_port(port_to_add, 'tcp', permanent=True)
                    # open migration ports in local machine using firewall_cmd
                else:
                    # open migration ports in local machine using iptables
                    iptables_func(rule, cleanup=cleanup)
                # SMT for Power8 machine is turned off for local machine during
                # test setup
            else:
                server_ip = params.get("server_ip", params.get("remote_ip"))
                server_user = params.get("server_user", params.get("remote_user"))
                server_pwd = params.get("server_pwd", params.get("remote_pwd"))
                server_session = remote.wait_for_login('ssh', server_ip, '22',
                                                       server_user, server_pwd,
                                                       r"[\#\$]\s*$")
                if use_firewall_cmd:
                    firewall_cmd = utils_iptables.Firewall_cmd(server_session)
                    # open migration ports in remote machine using firewall_cmd
                    if cleanup:
                        firewall_cmd.remove_port(port_to_add, 'tcp', permanent=True)
                    else:
                        firewall_cmd.add_port(port_to_add, 'tcp', permanent=True)
                else:
                    # open migration ports in remote machine using iptables
                    iptables_func(rule, params=params, cleanup=cleanup)
                cmd = "grep cpu /proc/cpuinfo | awk '{print $3}' | head -n 1"
                # Check if remote machine is Power8, if so check for smt state
                # and turn off if it is on.
                cmd_output = server_session.cmd_status_output(cmd)
                server_session.close()
                if (cmd_output[0] == 0):
                    cmd_output = cmd_output[1].strip().upper()
                    if "POWER8" in cmd_output:
                        test_setup.switch_smt(state="off", params=params)
                else:
                    raise exceptions.TestError("Failed to get cpuinfo of remote "
                                               "server", cmd_output[1])
        except AttributeError:
            # Negative scenarios will have invalid desturi for which test should
            # continue
            pass

    def do_migration(self, vms, srcuri, desturi, migration_type,
                     options=None, thread_timeout=60,
                     ignore_status=False, func=None, virsh_opt="",
                     extra_opts="", **args):
        """
        Migrate vms.

        :param vms: migrated vms.
        :param srcuri: local uri, used when migrate vm from remote to local
        :param descuri: remote uri, used when migrate vm from local to remote
        :param migration_type: do orderly for simultaneous migration
        :param options: migration options
        :param thread_timeout: time out seconds for the migration thread running
        :param ignore_status: determine if an exception is raised for errors
        :param func: the function executed during migration thread is running
        :param args: dictionary used by func,
                     'func_param' is mandatory if no real func_param, none is
                     requested.
                     'shell' is optional, where shell=True(bool) can be used
                     for process.run

        """
        for vm in vms:
            vm.connect_uri = args.get("virsh_uri", "qemu:///system")
        if migration_type == "orderly":
            for vm in vms:
                migration_thread = threading.Thread(target=self.thread_func_migration,
                                                    args=(vm, desturi, options,
                                                          ignore_status, virsh_opt,
                                                          extra_opts))
                migration_thread.start()
                eclipse_time = 0
                stime = int(time.time())
                if func:
                    # Execute command once the migration is started
                    migrate_start_state = args.get("migrate_start_state", "paused")

                    # Wait for migration to start
                    migrate_options = ""
                    if options:
                        migrate_options = str(options)
                    if extra_opts:
                        migrate_options += " %s" % extra_opts

                    migration_started = self.wait_for_migration_start(vm, state=migrate_start_state,
                                                                      uri=desturi,
                                                                      migrate_options=migrate_options.strip())

                    if migration_started:
                        logging.info("Migration started for %s", vm.name)
                        if func == process.run:
                            try:
                                func(args['func_params'], shell=args['shell'])
                            except KeyError:
                                func(args['func_params'])
                        elif func == virsh.migrate_postcopy:
                            time.sleep(3)  # To avoid of starting postcopy before starting migration
                            func(vm.name, uri=srcuri, debug=True)
                        else:
                            if 'func_params' in args:
                                func(args['func_params'])
                            else:
                                func()
                    else:
                        logging.error("Migration failed to start for %s",
                                      vm.name)
                eclipse_time = int(time.time()) - stime
                logging.debug("start_time:%d, eclipse_time:%d", stime, eclipse_time)
                if eclipse_time < thread_timeout:
                    migration_thread.join(thread_timeout - eclipse_time)
                if migration_thread.isAlive():
                    logging.error("Migrate %s timeout.", migration_thread)
                    self.RET_LOCK.acquire()
                    self.RET_MIGRATION = False
                    self.RET_LOCK.release()
        elif migration_type == "cross":
            # Migrate a vm to remote first,
            # then migrate another to remote with the first vm back
            vm_remote = vms.pop()
            self.thread_func_migration(vm_remote, desturi)
            for vm in vms:
                thread1 = threading.Thread(target=self.thread_func_migration,
                                           args=(vm_remote, srcuri, options))
                thread2 = threading.Thread(target=self.thread_func_migration,
                                           args=(vm, desturi, options))
                thread1.start()
                thread2.start()
                thread1.join(thread_timeout)
                thread2.join(thread_timeout)
                vm_remote = vm
                if thread1.isAlive() or thread1.isAlive():
                    logging.error("Cross migrate timeout.")
                    self.RET_LOCK.acquire()
                    self.RET_MIGRATION = False
                    self.RET_LOCK.release()
            # Add popped vm back to list
            vms.append(vm_remote)
        elif migration_type == "simultaneous":
            migration_threads = []
            for vm in vms:
                migration_threads.append(threading.Thread(
                                         target=self.thread_func_migration,
                                         args=(vm, desturi, options)))
            # let all migration going first
            for thread in migration_threads:
                thread.start()

            # listen threads until they end
            for thread in migration_threads:
                thread.join(thread_timeout)
                if thread.isAlive():
                    logging.error("Migrate %s timeout.", thread)
                    self.RET_LOCK.acquire()
                    self.RET_MIGRATION = False
                    self.RET_LOCK.release()
        if not self.RET_MIGRATION and not ignore_status:
            raise exceptions.TestFail()

    def cleanup_dest_vm(self, vm, srcuri, desturi):
        """
        Cleanup migrated vm on remote host.
        """
        vm.connect_uri = desturi
        if vm.exists():
            if vm.is_persistent():
                vm.undefine()
            if vm.is_alive():
                # If vm on remote host is unaccessible
                # graceful shutdown may cause confused
                vm.destroy(gracefully=False)
        # Set connect uri back to local uri
        vm.connect_uri = srcuri

    def wait_for_migration_start(self, vm, state='paused', uri=None,
                                 migrate_options='', timeout=60):
        """
        checks whether migration is started or not

        :param vm: VM object
        :param state: expected VM state in destination host
        :param uri: connect uri
        :param timeout: time in seconds to wait for migration to start
        :param migrate_options: virsh migrate options

        :return: True if migration is started False otherwise
        """
        def check_state():
            try:
                return libvirt.check_vm_state(dest_vm_name, state, uri=uri)
            except Exception:
                return False

        # Set dest_vm_name to be used in wait_for_migration_start() in case
        # --dname is specified in virsh options
        dest_vm_name = ""
        if migrate_options.count("--dname"):
            migrate_options_list = migrate_options.split()
            dest_vm_name = migrate_options_list[migrate_options_list.index("--dname") + 1]
        else:
            dest_vm_name = vm.name

        return utils_misc.wait_for(check_state, timeout)

    def check_parameters(self, params):
        """
        Make sure all of parameters are assigned a valid value

        :param params: the parameters to be checked

        :raise: test.cancel if invalid value exists
        """
        migrate_dest_host = params.get("migrate_dest_host")
        migrate_dest_pwd = params.get("migrate_dest_pwd")
        migrate_source_host = params.get("migrate_source_host")
        migrate_source_pwd = params.get("migrate_source_pwd")

        args_list = [migrate_dest_host,
                     migrate_dest_pwd, migrate_source_host,
                     migrate_source_pwd]

        for arg in args_list:
            if arg and arg.count("EXAMPLE"):
                raise exceptions.TestCancel("Please assign a value for %s!" % arg)

    def check_result(self, result, params):
        """
        Check if the migration result is as expected

        :param result: the output of migration
        :param params: the parameters dict
        :raise: test.fail if test is failed
        """
        status_error = "yes" == params.get("status_error", "no")
        err_msg = params.get("err_msg")
        if not result:
            raise exceptions.TestError("No migration result is returned.")

        logging.info("Migration out: %s", result.stdout_text.strip())
        logging.info("Migration error: %s", result.stderr_text.strip())

        if status_error:  # Migration should fail
            if err_msg:   # Special error messages are expected
                if not re.search(err_msg, result.stderr_text.strip()):
                    raise exceptions.TestFail("Can not find the expected "
                                              "patterns '%s' in output '%s'"
                                              % (err_msg,
                                                 result.stderr_text.strip()))
                else:
                    logging.debug("It is the expected error message")
            else:
                if int(result.exit_status) != 0:
                    logging.debug("Migration failure is expected result")
                else:
                    raise exceptions.TestFail("Migration success is unexpected result")
        else:
            if int(result.exit_status) != 0:
                raise exceptions.TestFail(result.stderr_text.strip())

    def do_cancel(self, sig=signal.SIGKILL):
        """
        Kill process during migration.

        :param sig: The signal to send
        :raise: test.error when kill fails
        """
        def _get_pid():
            cmd = "ps aux |grep 'virsh .*migrate' |grep -v grep |awk '{print $2}'"
            pid = process.run(cmd, shell=True).stdout_text
            return pid

        pid = utils_misc.wait_for(_get_pid, 30)
        if utils_misc.safe_kill(pid, sig):
            logging.info("Succeed to cancel migration: [%s].", pid.strip())
        else:
            raise exceptions.TestError("Fail to cancel migration: [%s]"
                                       % pid.strip())
