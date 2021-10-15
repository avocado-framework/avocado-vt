import time
import threading
import types
import logging
import re
import signal

from avocado.utils import process
from avocado.utils import path as utils_path
from avocado.utils import distro
from avocado.core import exceptions

from virttest import libvirt_version
from virttest import remote
from virttest import virsh
from virttest import utils_disk
from virttest import utils_misc
from virttest import test_setup
from virttest import utils_net
from virttest import utils_iptables
from virttest import utils_test
from virttest.utils_test import libvirt


LOG = logging.getLogger('avocado.' + __name__)


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
        # The return values for those functions invoked during migration
        # The format is: <func_object, func_return>
        self.func_ret = {}

    def post_migration_check(self, vms, params, uptime=None, uri=None):
        """
        Validating migration by performing checks in this method
        * check vm state after migration
        * uptime of the migrated vm > uptime of vm before migration
        * ping vm from target host
            by setting "check_network_accessibility_after_mig" to "yes"
        * As default, check system disk on the migrated vm
        * check disk operations on the migrated VM
            by setting "check_disk_after_mig" to "yes"

        :param vms: VM objects of migrating vms
        :param uptime: uptime dict of vms before migration
        :param uri: target virsh uri
        :return: updated dict of uptime
        """
        vm_state = params.get("virsh_migrated_state", "running")
        for vm in vms:
            if not libvirt.check_vm_state(vm.name, vm_state, uri=uri):
                raise exceptions.TestFail("Migrated VMs failed to be in %s "
                                          "state at destination" % vm_state)
            LOG.info("Guest state is '%s' at destination is as expected",
                     vm_state)
            if "offline" not in params.get("migrate_options", params.get("virsh_migrate_options", "")):
                if uptime:
                    vm_uptime = vm.uptime(connect_uri=uri)
                    LOG.info("uptime of migrated VM %s: %s", vm.name, vm_uptime)
                    if vm_uptime < uptime[vm.name]:
                        raise exceptions.TestFail("vm went for a reboot during "
                                                  "migration")

                    # update vm uptime to check when migrating back
                    uptime[vm.name] = vm_uptime
                    vm.verify_dmesg(connect_uri=uri)
                if params.get("check_network_accessibility_after_mig", "no") == "yes":
                    ping_count = int(params.get("ping_count", 10))
                    self.ping_vm(vm, params, uri=uri, ping_count=ping_count)
                if params.get("simple_disk_check_after_mig", 'yes') == "yes":
                    backup_uri, vm.connect_uri = vm.connect_uri, uri
                    vm.create_serial_console()
                    vm_session_after_mig = vm.wait_for_serial_login(timeout=360)
                    vm_session_after_mig.cmd("echo libvirt_simple_disk_check >> /tmp/libvirt_simple_disk_check")
                    vm_session_after_mig.close()
                    vm.connect_uri = backup_uri
                if params.get("check_disk_after_mig", "no") == "yes":
                    disk_kname = params.get("check_disk_kname_after_mig", "vdb")
                    backup_uri, vm.connect_uri = vm.connect_uri, uri
                    vm.create_serial_console()
                    vm_session_after_mig = vm.wait_for_serial_login(timeout=360)
                    utils_disk.linux_disk_check(vm_session_after_mig, disk_kname)
                    vm_session_after_mig.close()
                    vm.connect_uri = backup_uri
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
            LOG.info("Check VM network connectivity after migrating")
        else:
            LOG.info("Check VM network connectivity before migration")
            if not vm.is_alive():
                vm.start()
            vm.wait_for_login()
            vm_ip[vm.name] = vm.get_address()
            params["vm_ip_dict"] = vm_ip
        s_ping, o_ping = utils_net.ping(vm_ip[vm.name], count=ping_count,
                                        timeout=ping_timeout,
                                        output_func=LOG.debug,
                                        session=server_session)
        LOG.info(o_ping)
        if uri and uri != 'qemu:///system':
            vm.connect_uri = uri_backup
            if server_session:
                server_session.close()
        if s_ping != 0:
            if uri:
                if "offline" in params.get("migrate_options", ""):
                    LOG.info("Offline Migration: %s will not responded to "
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
                LOG.debug("Migration to %s returns failed exit status %d",
                          desturi, self.ret.exit_status)
                is_error = True
        except process.CmdError as detail:
            LOG.error("Migration to %s failed:\n%s", desturi, detail)
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
            LOG.debug("Using iptables for replacement")
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
                     options=None, thread_timeout=60, ignore_status=False,
                     func=None, multi_funcs=None, virsh_opt="", extra_opts="",
                     **args):
        """
        Migrate vms.

        :param vms: migrated vms.
        :param srcuri: local uri, used when migrate vm from remote to local
        :param desturi: remote uri, used when migrate vm from local to remote
        :param migration_type: do orderly for simultaneous migration
        :param options: migration options
        :param thread_timeout: time out seconds for the migration thread running
        :param ignore_status: determine if an exception is raised for errors
        :param func: the function executed during migration thread is running
        :param multi_funcs: list of functions executed during migration
                     thread is running. The func and multi_funcs should not be
                     provided at same time. For example,
                     multi_funcs = [{"func": <function check_established at 0x7f5833687510>,
                                     "after_event": "iteration: '1'",
                                     "before_event": "Suspended Migrated",
                                     "before_pause": "yes", "func_param": params},
                                    {"func": <function domjobabort at 0x7f5835cd08c8>,
                                     "before_pause": "no"}
                                   ]
        :param args: dictionary used by func,
                     'func_param' is mandatory for func parameter.
                     If no real func_param, none is requested.
                     'shell' is optional, where shell=True(bool) can be used
                     for process.run
        """

        def _run_collect_event_cmd():
            """
            To execute virsh event command to collect the domain events

            :return: VirshSession to retrieve the events
            """
            cmd = "event --loop --all"
            virsh_event_session = virsh.VirshSession(virsh_exec=virsh.VIRSH_EXEC,
                                                     auto_close=True,
                                                     uri=srcuri)
            virsh_event_session.sendline(cmd)
            LOG.debug("Begin to collect domain events...")
            return virsh_event_session

        def _need_collect_events(funcs_to_run):
            """
            Check if there is a need to run a command to collect domain events.
            This function will return True as long as one of functions to run
            has at least after_event or before_event defined.

            :param funcs_to_run: the functions to be run. It can be a list
                                 or a single function. When it is a list, its
                                 element must be a dict.
                For example,
                funcs_to_run = [{"func": <function check_established at 0x7f5833687510>,
                                 "after_event": "iteration: '1'",
                                 "before_event": "Suspended Migrated",
                                 "before_pause": "yes", "func_name": params},
                                {"func": <function domjobabort at 0x7f5835cd08c8>,
                                 "before_pause": "no"}
                               ]
            :return: boolean, True to collect events, otherwise False
            :raises: exceptions.TestError when the parameter is invalid
            """
            if not funcs_to_run:
                return False
            if isinstance(funcs_to_run, list):
                for one_func in funcs_to_run:
                    if isinstance(one_func, dict):
                        after_event = one_func.get('after_event')
                        before_event = one_func.get('before_event')
                        if any([after_event, before_event]):
                            return True
                    else:
                        raise exceptions.TestError("Only a dict element is "
                                                   "supported in funcs_to_run")
            elif isinstance(funcs_to_run, (types.FunctionType, types.MethodType)):
                return False
            return False

        def _run_simple_func(vm, one_func):
            """
            Run single function

            :param vm: the VM object
            :param one_func: the function object to execute
            """
            if one_func == process.run:
                try:
                    one_func(args['func_params'], shell=args['shell'])
                except KeyError:
                    one_func(args['func_params'])
            elif one_func == virsh.migrate_postcopy:
                one_func(vm.name, uri=srcuri, debug=True)
            else:
                if 'func_params' in args:
                    LOG.debug("Run function {} with parameters".format(one_func))
                    one_func(args['func_params'])
                else:
                    LOG.debug("Run function {}".format(one_func))
                    one_func()

        def _run_complex_func(vm, one_func, virsh_event_session=None):
            """
            Run a function based on a dict definition

            :param vm: the VM object
            :param one_func: the function to be executed
            :param virsh_event_session: VirshSession to collect domain events
            :raises: exceptions.TestError if any error happens
            """

            LOG.debug("Handle function invoking:%s", one_func)
            before_vm_pause = 'yes' == one_func.get('before_pause', 'no')
            after_event = one_func.get('after_event')
            before_event = one_func.get('before_event')
            func = one_func.get('func')
            if after_event and not virsh_event_session:
                raise exceptions.TestError("virsh session for collecting domain "
                                           "events is not provided")

            if after_event:
                LOG.debug("Below events are received:"
                          "%s", virsh_event_session.get_stripped_output())
                if not utils_misc.wait_for(
                        lambda: re.findall(after_event,
                                           virsh_event_session.get_stripped_output()), 30):
                    raise exceptions.TestError("Unable to find "
                                               "event {}".format(after_event))
                LOG.debug("Receive the event '{}'".format(after_event))
            # If 'before_event' is provided, then 'after_event' must be provided
            if before_event and re.findall(before_event,
                                           virsh_event_session.get_stripped_output()):
                raise exceptions.TestError("The function '{}' should "
                                           "be run before the event "
                                           "'{}', but the event has "
                                           "been received".format(func,
                                                                  before_event))
            # Check if VM state is paused
            if before_vm_pause and libvirt.check_vm_state(vm.name,
                                                          'paused',
                                                          uri=desturi):
                raise exceptions.TestError("The function '{}' should "
                                           "be run before VM is paused, "
                                           "but VM is already "
                                           "paused".format(func))

            func_param = one_func.get("func_param")
            if func_param:
                #one_param_dict = args['multi_func_params'][func]
                LOG.debug("Run function {} with "
                          "parameters '{}'".format(func, func_param))
                self.func_ret.update({func: func(func_param)})
            else:
                LOG.debug("Run function {}".format(func))
                self.func_ret.update({func: func()})

        def _run_funcs(vm, funcs_to_run, before_pause, virsh_event_session=None):
            """
            Execute the functions during migration

            :param vm: the VM object
            :param funcs_to_run: the function or list of functions
            :param before_pause: True to run functions before guest is
                                 paused on source host, otherwise, False
            :param virsh_event_session: VirshSession to collect domain events
            :raises: exceptions.TestError if any test error happens
            """
            for one_func in funcs_to_run:
                if isinstance(one_func, (types.FunctionType, types.MethodType)):
                    if not before_pause:
                        _run_simple_func(vm, one_func)
                    else:
                        LOG.error("Only support to run the function "
                                  "after guest is paused")
                elif isinstance(one_func, dict):
                    before_vm_pause = 'yes' == one_func.get('before_pause', 'no')
                    if before_vm_pause == before_pause:
                        _run_complex_func(vm, one_func, virsh_event_session)
                else:
                    raise exceptions.TestError("Only dict, FunctionType "
                                               "and MethodType are supported. "
                                               "No function will be run")

        @virsh.EventTracker.wait_event
        def _do_orderly_migration(vm_name, vm, srcuri, desturi, options=None,
                                  thread_timeout=60, ignore_status=False,
                                  func=None, multi_funcs=None, virsh_opt="",
                                  extra_opts="", **args):

            virsh_event_session = None
            if _need_collect_events(multi_funcs):
                virsh_event_session = _run_collect_event_cmd()

            migration_thread = threading.Thread(target=self.thread_func_migration,
                                                args=(vm, desturi, options,
                                                      ignore_status, virsh_opt,
                                                      extra_opts))
            migration_thread.start()
            eclipse_time = 0
            stime = int(time.time())
            funcs_to_run = [func] if func else multi_funcs

            if funcs_to_run:
                # Execute command once the migration is started
                migrate_start_state = args.get("migrate_start_state", "paused")

                # Wait for migration to start
                migrate_options = ""
                if options:
                    migrate_options = str(options)
                if extra_opts:
                    migrate_options += " %s" % extra_opts

                _run_funcs(vm, funcs_to_run, before_pause=True,
                           virsh_event_session=virsh_event_session)

                migration_started = self.wait_for_migration_start(
                    vm, state=migrate_start_state,
                    uri=desturi,
                    migrate_options=migrate_options.strip())

                if migration_started:
                    LOG.info("Migration started for %s", vm.name)
                    time.sleep(3)  # To avoid executing the command lines before starting migration
                    _run_funcs(vm, funcs_to_run, before_pause=False,
                               virsh_event_session=virsh_event_session)
                else:
                    LOG.error("Migration failed to start for %s", vm.name)
            eclipse_time = int(time.time()) - stime
            LOG.debug("start_time:%d, eclipse_time:%d", stime, eclipse_time)
            if eclipse_time < thread_timeout:
                migration_thread.join(thread_timeout - eclipse_time)
            if migration_thread.is_alive():
                LOG.error("Migrate %s timeout.", migration_thread)
                self.RET_LOCK.acquire()
                self.RET_MIGRATION = False
                self.RET_LOCK.release()

        for vm in vms:
            vm.connect_uri = args.get("virsh_uri", "qemu:///system")
        if migration_type == "orderly":
            for vm in vms:
                if func and multi_funcs:
                    raise exceptions.TestError("Only one parameter between "
                                               "func and multi_funcs is "
                                               "supported at a time")
                _do_orderly_migration(vm.name, vm, srcuri, desturi,
                                      options=options,
                                      thread_timeout=thread_timeout,
                                      ignore_status=ignore_status,
                                      func=func,
                                      multi_funcs=multi_funcs,
                                      virsh_opt=virsh_opt,
                                      extra_opts=extra_opts,
                                      **args)
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
                if thread1.is_alive() or thread1.is_alive():
                    LOG.error("Cross migrate timeout.")
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
                if thread.is_alive():
                    LOG.error("Migrate %s timeout.", thread)
                    self.RET_LOCK.acquire()
                    self.RET_MIGRATION = False
                    self.RET_LOCK.release()
        if not self.RET_MIGRATION and not ignore_status:
            raise exceptions.TestFail()

        LOG.info("Checking migration result...")
        self.check_result(self.ret, args)

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

    def cleanup_vm(self, vm, desturi):
        """
        Cleanup migrated vm on remote host and local host

        :param vm: vm object
        :param desturi: uri for remote access
        """
        try:
            self.cleanup_dest_vm(vm, vm.connect_uri, desturi)
        except Exception as err:
            LOG.error(err)
        if vm.is_alive():
            vm.destroy(gracefully=False)

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

    def update_virsh_migrate_extra_args(self, params):
        """
        Update extra arguments for the function executed during migration

        :param params: the parameters used
        :return: the updated extra arguments
        """
        func_params_exists = "yes" == params.get(
            "action_during_mig_params_exists", "no")
        wait_for_event = eval(params.get("wait_for_event", "False"))
        event_type = params.get("event_type", None)
        event_timeout = eval(params.get("event_timeout", "7"))

        extra_args = {}
        if func_params_exists:
            if params.get("action_during_mig_params"):
                extra_args.update({'func_params': eval(
                    params.get("action_during_mig_params"))})
            else:
                extra_args.update({'func_params': params})

        # Update parameters for postcopy migration
        extra_args.update({'wait_for_event': wait_for_event})
        extra_args.update({'event_type': event_type})
        extra_args.update({'event_timeout': event_timeout})

        extra_args.update({'status_error': params.get("status_error", "no")})
        extra_args.update({'err_msg': params.get("err_msg")})
        return extra_args

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

        LOG.info("Migration out: %s", result.stdout_text.strip())
        LOG.info("Migration error: %s", result.stderr_text.strip())

        if status_error:  # Migration should fail
            if err_msg:   # Special error messages are expected
                if not re.search(err_msg, result.stderr_text.strip()):
                    raise exceptions.TestFail("Can not find the expected "
                                              "patterns '%s' in output '%s'"
                                              % (err_msg,
                                                 result.stderr_text.strip()))
                else:
                    LOG.debug("It is the expected error message")
            else:
                if int(result.exit_status) != 0:
                    LOG.debug("Migration failure is expected result")
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
            LOG.info("Succeed to cancel migration: [%s].", pid.strip())
        else:
            raise exceptions.TestError("Fail to cancel migration: [%s]"
                                       % pid.strip())

    def set_migratepostcopy(self, vm_name, uri=None):
        """
        Switch to postcopy during migration.

        :param vm_name: vm's name
        :param uri: target virsh uri
        :raise: test.error when command fails
        """
        cmd = "event --loop --all"
        virsh_event_session = virsh.VirshSession(virsh_exec=virsh.VIRSH_EXEC,
                                                 auto_close=True,
                                                 uri=uri)
        virsh_event_session.sendline(cmd)

        if not utils_misc.wait_for(
           lambda: not virsh.migrate_postcopy(vm_name, uri=uri,
                                              debug=True).exit_status, 10):
            raise exceptions.TestError("Failed to set migration postcopy.")

        exp_str = "Suspended Post-copy"
        if not utils_misc.wait_for(
           lambda: re.findall(exp_str,
                              virsh_event_session.get_stripped_output()), 30):
            raise exceptions.TestError("Unalbe to find event {}"
                                       .format(exp_str))

    def control_migrate_speed(self, vm_name, to_speed=1, mode="precopy"):
        """
        Set migration speed to control the migration duration

        :param vm_name: vm name
        :param to_speed: the speed value in Mbps to be set for migration
        :param mode: one of ['postcopy', 'precopy', 'both']
        """
        def _set_speed(extra_option=''):
            """
            Inner function to set migration speed

            :param extra_option: str, it might include '--postcopy' or not
            """
            virsh_args = {"ignore_status": False}
            old_speed = virsh.migrate_getspeed(vm_name,
                                               extra=extra_option,
                                               **virsh_args)
            LOG.debug("Current %s migration speed is %s "
                      "MiB/s\n", extra_option, old_speed.stdout_text.strip())
            LOG.debug("Set %s migration speed to %d "
                      "MiB/s\n", extra_option, to_speed)
            virsh.migrate_setspeed(vm_name, to_speed,
                                   extra=extra_option,
                                   **virsh_args)

        if mode not in ['postcopy', 'precopy', 'both']:
            raise exceptions.TestError("'mode' only supports "
                                       "'postcopy', 'precopy', 'both'")
        warning_msg = "libvirt version should be larger than or equal to " \
                      "'5.0.0' when setting postcopy migration speed."

        if not libvirt_version.version_compare(5, 0, 0):
            if mode == 'both':
                LOG.warning("%s Only precopy speed is set.", warning_msg)
                mode = 'precopy'
            if mode == 'postcopy':
                LOG.warning("%s Skipping", warning_msg)
                return
        if mode == 'both':
            _set_speed()
            _set_speed(extra_option='--postcopy')
        elif mode == 'postcopy':
            _set_speed(extra_option='--postcopy')
        else:
            _set_speed()

    def run_stress_in_vm(self, vm, params):
        """
        Load stress in VM.

        :param vm: VM object
        :param params: Test dict params
        :raise: exceptions.TestError if it fails to run stress tool
        """
        stress_package = params.get("stress_package", "stress")
        try:
            vm_stress = utils_test.VMStress(vm, stress_package, params)
            vm_stress.load_stress_tool()
        except utils_test.StressError as info:
            raise exceptions.TestError(info)
