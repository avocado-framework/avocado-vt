"""
High-level QEMU test utility functions.

This module is meant to reduce code size by performing common test procedures.
Generally, code here should look like test code.

More specifically:
    - Functions in this module should raise exceptions if things go wrong
    - Functions in this module typically use functions and classes from
      lower-level modules (e.g. utils_misc, qemu_vm, aexpect).
    - Functions in this module should not be used by lower-level modules.
    - Functions in this module should be used in the right context.
      For example, a function should not be used where it may display
      misleading or inaccurate info or debug messages.

:copyright: 2008-2013 Red Hat Inc.
"""

import os
import re
import six
import time
import logging
from functools import reduce

from avocado.core import exceptions
from avocado.utils import path as utils_path
from avocado.utils import process
from avocado.utils import cpu as cpuutil

from virttest import error_context
from virttest import utils_misc
from virttest import qemu_monitor
from virttest.qemu_devices import qdevices
from virttest.staging import utils_memory


def guest_active(vm):
    o = vm.monitor.info("status")
    if isinstance(o, six.string_types):
        return "status: running" in o
    else:
        if "status" in o:
            return o.get("status") == "running"
        else:
            return o.get("running")


def get_numa_status(numa_node_info, qemu_pid, debug=True):
    """
    Get the qemu process memory use status and the cpu list in each node.

    :param numa_node_info: Host numa node information
    :type numa_node_info: NumaInfo object
    :param qemu_pid: process id of qemu
    :type numa_node_info: string
    :param debug: Print the debug info or not
    :type debug: bool
    :return: memory and cpu list in each node
    :rtype: tuple
    """
    node_list = numa_node_info.online_nodes
    qemu_memory = []
    qemu_cpu = []
    cpus = cpuutil.get_pid_cpus(qemu_pid)
    for node_id in node_list:
        qemu_memory_status = utils_memory.read_from_numa_maps(qemu_pid,
                                                              "N%d" % node_id)
        memory = sum([int(_) for _ in list(qemu_memory_status.values())])
        qemu_memory.append(memory)
        cpu = [_ for _ in cpus if _ in numa_node_info.nodes[node_id].cpus]
        qemu_cpu.append(cpu)
        if debug:
            logging.debug("qemu-kvm process using %s pages and cpu %s in "
                          "node %s" % (memory, " ".join(cpu), node_id))
    return (qemu_memory, qemu_cpu)


def pin_vm_threads(vm, node):
    """
    Pin VM threads to single cpu of a numa node

    :param vm: VM object
    :param node: NumaNode object
    """
    if len(vm.vcpu_threads) + len(vm.vhost_threads) < len(node.cpus):
        for i in vm.vcpu_threads:
            logging.info("pin vcpu thread(%s) to cpu(%s)" %
                         (i, node.pin_cpu(i)))
        for i in vm.vhost_threads:
            logging.info("pin vhost thread(%s) to cpu(%s)" %
                         (i, node.pin_cpu(i)))
    elif (len(vm.vcpu_threads) <= len(node.cpus) and
          len(vm.vhost_threads) <= len(node.cpus)):
        for i in vm.vcpu_threads:
            logging.info("pin vcpu thread(%s) to cpu(%s)" %
                         (i, node.pin_cpu(i)))
        for i in vm.vhost_threads:
            logging.info("pin vhost thread(%s) to extra cpu(%s)" %
                         (i, node.pin_cpu(i, extra=True)))
    else:
        logging.info("Skip pinning, no enough nodes")


def _check_driver_verifier(session, driver, verifier_flags=None, timeout=300):
    """
    Check driver verifier status

    :param session: VM session.
    :param driver: The driver need to query
    :param timeout: Timeout in seconds
    """
    logging.info("Check %s driver verifier status" % driver)
    query_cmd = "verifier /querysettings"
    output = session.cmd_output(query_cmd, timeout=timeout)
    status = driver in output
    if verifier_flags:
        status &= bool(re.findall(r"%s" % verifier_flags, output, re.I))
    return (status, output)


@error_context.context_aware
def setup_win_driver_verifier(session, driver, vm, timeout=300):
    """
    Enable driver verifier for windows guest.

    :param driver: The driver which needs enable the verifier.
    :param vm: VM object.
    :param timeout: Timeout in seconds.
    """

    win_verifier_flags = vm.params.get("windows_verifier_flags")
    verifier_status = _check_driver_verifier(session, driver,
                                             win_verifier_flags)[0]
    if not verifier_status:
        error_context.context("Enable %s driver verifier" % driver,
                              logging.info)
        if win_verifier_flags:
            verifier_setup_cmd = "verifier /flags %s /driver %s.sys" % (
                                 win_verifier_flags, driver)
        else:
            verifier_setup_cmd = "verifier /standard /driver %s.sys" % driver
        session.cmd(verifier_setup_cmd, timeout=timeout, ignore_all_errors=True)
        session = vm.reboot(session)
        verifier_status, output = _check_driver_verifier(session, driver,
                                                         win_verifier_flags)
        if not verifier_status:
            msg = "%s verifier is not enabled, details: %s" % (driver, output)
            raise exceptions.TestFail(msg)
    logging.info("%s verifier is enabled already" % driver)
    return session


def clear_win_driver_verifier(driver, vm, timeout=300):
    """
    Clear the driver verifier in windows guest.

    :param driver: The driver need to clear
    :param vm: VM object.
    :param timeout: Timeout in seconds.
    """
    session = vm.wait_for_login(timeout=timeout)
    try:
        verifier_status = _check_driver_verifier(session, driver)[1]
        if verifier_status:
            logging.info("Clear driver verifier")
            verifier_clear_cmd = "verifier /reset"
            session.cmd(verifier_clear_cmd,
                        timeout=timeout,
                        ignore_all_errors=True)
            session = vm.reboot(session)
    finally:
        session.close()


@error_context.context_aware
def windrv_verify_running(session, test, driver, timeout=300):
    """
    Check if driver is running for windows guest within a period time.

    :param session: VM session
    :param test: Kvm test object
    :param driver: The driver which needs to check.
    :param timeout: Timeout in seconds.
    """

    def _check_driver_stat():
        """
        Check if driver is in Running status.

        """
        output = session.cmd_output(driver_check_cmd, timeout=timeout)
        if "Running" in output:
            return True
        return False

    error_context.context("Check %s driver state." % driver, logging.info)
    driver_check_cmd = (r'wmic sysdriver where PathName="C:\\Windows\\System32'
                        r'\\drivers\\%s.sys" get State /value') % driver

    if not utils_misc.wait_for(_check_driver_stat, timeout, 0, 5):
        test.error("%s driver is not running" % driver)


@error_context.context_aware
def windrv_check_running_verifier(session, vm, test, driver, timeout=300):
    """
    Check whether the windows driver is running, then enable driver verifier.

    :param vm: the VM that use the driver.
    :param test: the KVM test object.
    :param driver: the driver concerned.
    :timeout: the timeout to use in this process, in seconds.
    """
    windrv_verify_running(session, test, driver, timeout)
    return setup_win_driver_verifier(session, driver, vm, timeout)


def setup_runlevel(params, session):
    """
    Setup the runlevel in guest.

    :param params: Dictionary with the test parameters.
    :param session: VM session.
    """
    cmd = "runlevel"
    ori_runlevel = "0"
    expect_runlevel = params.get("expect_runlevel", "3")

    # Note: All guest services may have not been started when
    #       the guest gets IP addr; the guest runlevel maybe
    #       is "unknown" whose exit status is 1 at that time,
    #       which will cause the cmd execution failed. Need some
    #       time here to wait for the guest services start.
    if utils_misc.wait_for(lambda: session.cmd_status(cmd) == 0, 15):
        ori_runlevel = session.cmd(cmd)

    ori_runlevel = ori_runlevel.split()[-1]
    if ori_runlevel == expect_runlevel:
        logging.info("Guest runlevel is already %s as expected" % ori_runlevel)
    else:
        session.cmd("init %s" % expect_runlevel)
        tmp_runlevel = session.cmd(cmd)
        tmp_runlevel = tmp_runlevel.split()[-1]
        if tmp_runlevel != expect_runlevel:
            logging.warn("Changing runlevel from %s to %s failed (%s)!",
                         ori_runlevel, expect_runlevel, tmp_runlevel)


class GuestSuspend(object):

    """
    Suspend guest, supports both Linux and Windows.

    """
    SUSPEND_TYPE_MEM = "mem"
    SUSPEND_TYPE_DISK = "disk"

    def __init__(self, test, params, vm):
        if not params or not vm:
            raise exceptions.TestError("Missing 'params' or 'vm' parameters")

        self._open_session_list = []
        self.test = test
        self.vm = vm
        self.params = params
        self.login_timeout = float(self.params.get("login_timeout", 360))
        self.services_up_timeout = float(self.params.get("services_up_timeout",
                                                         30))
        self.os_type = self.params.get("os_type")

    def _get_session(self):
        self.vm.verify_alive()
        session = self.vm.wait_for_login(timeout=self.login_timeout)
        return session

    def _session_cmd_close(self, session, cmd):
        try:
            return session.cmd_status_output(cmd)
        finally:
            try:
                session.close()
            except Exception:
                pass

    def _cleanup_open_session(self):
        try:
            for s in self._open_session_list:
                if s:
                    s.close()
        except Exception:
            pass

    @error_context.context_aware
    def setup_bg_program(self, **args):
        """
        Start up a program as a flag in guest.
        """
        suspend_bg_program_setup_cmd = args.get("suspend_bg_program_setup_cmd")

        error_context.context(
            "Run a background program as a flag", logging.info)
        session = self._get_session()
        self._open_session_list.append(session)

        logging.debug("Waiting all services in guest are fully started.")
        time.sleep(self.services_up_timeout)

        session.sendline(suspend_bg_program_setup_cmd)

    @error_context.context_aware
    def check_bg_program(self, **args):
        """
        Make sure the background program is running as expected
        """
        suspend_bg_program_chk_cmd = args.get("suspend_bg_program_chk_cmd")

        error_context.context(
            "Verify background program is running", logging.info)
        session = self._get_session()
        s, _ = self._session_cmd_close(session, suspend_bg_program_chk_cmd)
        if s:
            raise exceptions.TestFail(
                "Background program is dead. Suspend failed.")

    @error_context.context_aware
    def kill_bg_program(self, **args):
        error_context.context("Kill background program after resume")
        suspend_bg_program_kill_cmd = args.get("suspend_bg_program_kill_cmd")

        try:
            session = self._get_session()
            self._session_cmd_close(session, suspend_bg_program_kill_cmd)
        except Exception as e:
            logging.warn("Could not stop background program: '%s'", e)
            pass

    @error_context.context_aware
    def _check_guest_suspend_log(self, **args):
        error_context.context("Check whether guest supports suspend",
                              logging.info)
        suspend_support_chk_cmd = args.get("suspend_support_chk_cmd")

        session = self._get_session()
        s, o = self._session_cmd_close(session, suspend_support_chk_cmd)

        return s, o

    def verify_guest_support_suspend(self, **args):
        s, _ = self._check_guest_suspend_log(**args)
        if s:
            raise exceptions.TestError("Guest doesn't support suspend.")

    @error_context.context_aware
    def start_suspend(self, **args):
        suspend_start_cmd = args.get("suspend_start_cmd")
        error_context.context(
            "Start suspend [%s]" % (suspend_start_cmd), logging.info)

        session = self._get_session()
        self._open_session_list.append(session)

        # Suspend to disk
        session.sendline(suspend_start_cmd)

    @error_context.context_aware
    def verify_guest_down(self, **args):
        # Make sure the VM goes down
        error_context.context("Wait for guest goes down after suspend")
        suspend_timeout = 240 + int(self.params.get("smp")) * 60
        if not utils_misc.wait_for(self.vm.is_dead, suspend_timeout, 2, 2):
            raise exceptions.TestFail("VM refuses to go down. Suspend failed.")

    @error_context.context_aware
    def resume_guest_mem(self, **args):
        error_context.context("Resume suspended VM from memory")
        self.vm.monitor.system_wakeup()

    @error_context.context_aware
    def resume_guest_disk(self, **args):
        error_context.context("Resume suspended VM from disk")
        self.vm.create()

    @error_context.context_aware
    def verify_guest_up(self, **args):
        error_context.context("Verify guest system log", logging.info)
        suspend_log_chk_cmd = args.get("suspend_log_chk_cmd")

        session = self._get_session()
        s, o = self._session_cmd_close(session, suspend_log_chk_cmd)
        if s:
            raise exceptions.TestError(
                "Could not find suspend log. [%s]" % (o))

    @error_context.context_aware
    def action_before_suspend(self, **args):
        error_context.context("Actions before suspend")
        pass

    @error_context.context_aware
    def action_during_suspend(self, **args):
        error_context.context(
            "Sleep a while before resuming guest", logging.info)

        time.sleep(10)
        if self.os_type == "windows":
            # Due to WinXP/2003 won't suspend immediately after issue S3 cmd,
            # delay 10~60 secs here, maybe there's a bug in windows os.
            logging.info("WinXP/2003 need more time to suspend, sleep 50s.")
            time.sleep(50)

    @error_context.context_aware
    def action_after_suspend(self, **args):
        error_context.context("Actions after suspend")
        pass


class MemoryBaseTest(object):

    """
    Base class for memory functions.
    """

    UNIT = "M"

    def __init__(self, test, params, env):
        self.test = test
        self.env = env
        self.params = params
        self.sessions = {}

    def get_vm_mem(self, vm):
        """
        Count memory assigned to VM.

        :param vm: VM object
        :return: memory size in MB.
        """
        PC_DIMM = qdevices.Dimm
        # Default memory size in configuration is MB, so append
        # 'MB' in the end of 'mem' param.
        mem_str = "%sM" % vm.params.get("mem", "0")
        total_mem = self.normalize_mem_size(mem_str)
        pc_dimms = filter(lambda x: isinstance(x, PC_DIMM), vm.devices)
        obj_ids = map(lambda x: x.get_param('memdev'), pc_dimms)
        obj_devs = map(lambda x: vm.devices.get_by_qid(x)[0], obj_ids)
        obj_size = map(lambda x: x.get_param('size'), obj_devs)
        total_mem += sum(map(self.normalize_mem_size, obj_size))
        logging.info("Assigned %s%s " % (total_mem, self.UNIT) +
                     "memory to '%s'" % vm.name)
        return total_mem

    @classmethod
    def normalize_mem_size(cls, str_size):
        """
        Convert memory size unit

        :param str_size: memory size string, like: 1GB
        :return: memory size value in MB
        """
        args = (str_size, cls.UNIT, 1024)
        try:
            size = utils_misc.normalize_data_size(*args)
            return int(float(size))
        except ValueError as details:
            logging.debug("Convert memory size error('%s')" % details)
        return 0

    @classmethod
    def get_guest_total_mem(cls, vm):
        """
        Guest OS reported physical memory size in MB.

        :param vm: VM object.
        :return: physical memory report by guest OS in MB
        """
        if vm.params.get("os_type") == "windows":
            cmd = 'wmic ComputerSystem get TotalPhysicalMemory'
        else:
            cmd = "grep 'MemTotal:' /proc/meminfo"
        return vm.get_memory_size(cmd)

    @classmethod
    def get_guest_free_mem(cls, vm):
        """
        Guest OS reported free memory size in MB.

        :param vm: VM Object
        :return: free memory report by guest OS in MB
        """
        os_type = vm.params.get("os_type")
        timeout = float(vm.params.get("login_timeout", 600))
        try:
            session = vm.wait_for_login(timeout=timeout)
            return utils_misc.get_free_mem(session, os_type)
        finally:
            session.close()

    @classmethod
    def get_guest_used_mem(cls, vm):
        """
        Guest OS reported used memory size in MB.

        :param vm: VM Object
        :return: used memory report by guest OS in MB
        """
        os_type = vm.params.get("os_type")
        timeout = float(vm.params.get("login_timeout", 600))
        session = vm.wait_for_login(timeout=timeout)
        try:
            return utils_misc.get_used_mem(session, os_type)
        finally:
            session.close()

    def get_session(self, vm):
        """
        Get connection to VM.

        :param vm: VM object
        :return: return ShellSession object
        """
        key = vm.instance
        self.sessions.setdefault(key, [])
        for session in self.sessions.get(key):
            if session.is_responsive():
                return session
            session.close()
            self.sessions[key].remove(session)
        login_timeout = float(self.params.get("login_timeout", 600))
        session = vm.wait_for_login(timeout=login_timeout)
        self.sessions[key].append(session)
        return session

    def close_sessions(self):
        """
        Close opening session, better to call it in the end of test.
        """
        sessions = list(filter(None, list(self.sessions.values())))
        if sessions:
            sessions = list(filter(None, reduce(list.__add__, sessions)))
            list(map(lambda x: x.close(), sessions))
        self.sessions.clear()


class MemoryHotplugTest(MemoryBaseTest):

    """
    Class for memory hotplug/unplug test.
    """

    @error_context.context_aware
    def update_vm_after_hotplug(self, vm, dev):
        """
        Update VM params to ensure hotpluged devices exist in guest.

        :param vm: VM object
        :param dev: Qdevice object.
        """
        error_context.context("Update VM object after hotplug memory")
        dev_type, name = dev.get_qid().split('-')
        if isinstance(dev, qdevices.Memory):
            backend = self.params.object_params(name).get("backend_mem",
                                                          "memory-backend-ram")
            attrs = dev.__attributes__[backend][:]
        else:
            attrs = dev.__attributes__[:]
        params = self.params.copy_from_keys(attrs)
        for attr in attrs:
            val = dev.get_param(attr)
            if val:
                key = "_".join([attr, dev_type, name])
                params[key] = val
        mem_devs = vm.params.objects("mem_devs")
        if name not in mem_devs:
            mem_devs.append(name)
            params["mem_devs"] = " ".join(mem_devs)
        vm.params.update(params)
        if dev not in vm.devices:
            vm.devices.insert(dev)
        self.env.register_vm(vm.name, vm)

    @error_context.context_aware
    def update_vm_after_unplug(self, vm, dev):
        """
        Update VM params object after unplug memory devices.

        :param vm: VM object
        :param dev: Qdevice object
        """
        error_context.context("Update VM object after unplug memory")
        dev_type, name = dev.get_qid().split('-')
        mem_devs = vm.params.objects("mem_devs")
        if dev in vm.devices:
            vm.devices.remove(dev)
        if name in mem_devs:
            mem_devs.remove(name)
            vm.params["mem_devs"] = " ".join(mem_devs)
        self.env.register_vm(vm.name, vm)

    @error_context.context_aware
    def hotplug_memory(self, vm, name):
        """
        Hotplug dimm device with memory backend

        :param vm: VM object
        :param name: memory device name
        """
        devices = vm.devices.memory_define_by_params(self.params, name)
        for dev in devices:
            dev_type = "memory"
            if isinstance(dev, qdevices.Dimm):
                addr = self.get_mem_addr(vm, dev.get_qid())
                dev.set_param("addr", addr)
                dev_type = "pc-dimm"
            step = "Hotplug %s '%s' to VM" % (dev_type, dev.get_qid())
            error_context.context(step, logging.info)
            _, ver_out = vm.devices.simple_hotplug(dev, vm.monitor)
            if ver_out is False:
                raise exceptions.TestFail("Verify hotplug memory failed")
            self.update_vm_after_hotplug(vm, dev)
        return devices

    @error_context.context_aware
    def unplug_memory(self, vm, name):
        """
        Unplug memory device
        step 1, unplug dimm device
        step 2, unplug memory object

        :param vm: VM object
        :param name: memory device name
        """
        devices = []
        qid_dimm = "dimm-%s" % name
        qid_mem = "mem-%s" % name
        try:
            dimm = vm.devices.get_by_qid(qid_dimm)[0]
        except IndexError:
            logging.warn("'%s' is not used by any dimm" % qid_mem)
        else:
            step = "Unplug pc-dimm '%s'" % qid_dimm
            error_context.context(step, logging.info)
            _, ver_out = vm.devices.simple_unplug(dimm, vm.monitor)
            if ver_out is False:
                raise exceptions.TestFail("Verify unplug memory failed")
            devices.append(dimm)
            self.update_vm_after_unplug(vm, dimm)

        step = "Unplug memory object '%s'" % qid_mem
        error_context.context(step, logging.info)
        try:
            mem = vm.devices.get_by_qid(qid_mem)[0]
        except IndexError:
            output = vm.monitor.query("memory-devices")
            logging.debug("Memory devices: %s" % output)
            msg = "Memory object '%s' not exists" % qid_mem
            raise exceptions.TestError(msg)
        error_context.context(step, logging.info)
        vm.devices.simple_unplug(mem, vm.monitor)
        devices.append(mem)
        self.update_vm_after_unplug(vm, mem)
        return devices

    @error_context.context_aware
    def get_mem_addr(self, vm, qid):
        """
        Get guest memory address from qemu monitor

        :param vm: VM object
        :param qid: memory device qid
        """
        error_context.context("Get hotpluged memory address", logging.info)
        if not isinstance(vm.monitor, qemu_monitor.QMPMonitor):
            raise NotImplementedError
        for info in vm.monitor.info("memory-devices"):
            if str(info['data']['id']) == qid:
                address = info['data']['addr']
                logging.info("Memory address: %s" % address)
                return address

    @error_context.context_aware
    def check_memory(self, vm=None):
        """
        Check is guest memory is really match assgined to VM.

        :param vm: VM object, get VM object from env if vm is None.
        """
        error_context.context("Verify memory info", logging.info)
        if not vm:
            vm = self.env.get_vm(self.params["main_vm"])
        vm.verify_alive()
        threshold = float(self.params.get("threshold", 0.10))
        timeout = float(self.params.get("wait_resume_timeout", 60))
        # Notes:
        #    some sub test will pause VM, here need to wait VM resume
        # then check memory info in guest.
        utils_misc.wait_for(lambda: not vm.is_paused(), timeout=timeout)
        utils_misc.verify_dmesg()
        self.os_type = self.params.get("os_type")
        guest_mem_size = super(MemoryHotplugTest, self).get_guest_total_mem(vm)
        vm_mem_size = self.get_vm_mem(vm)
        if abs(guest_mem_size - vm_mem_size) > vm_mem_size * threshold:
            msg = ("Assigned '%s MB' memory to '%s'"
                   "but, '%s MB' memory detect by OS" %
                   (vm_mem_size, vm.name, guest_mem_size))
            raise exceptions.TestFail(msg)

    @error_context.context_aware
    def memory_operate(self, vm, memory, operation='online'):
        error_context.context(
            "%s %s in guest OS" %
            (operation, memory), logging.info)
        mem_sys_path = "/sys/devices/system/memory/%s" % memory
        mem_state_path = os.path.join(mem_sys_path, 'state')
        session = self.get_session(vm)
        session.cmd("echo '%s' > %s" % (operation, mem_state_path))
        output = session.cmd_output_safe("cat %s" % mem_state_path)
        if operation not in output:
            return exceptions.TestFail("Fail to %s %s" % (operation, memory))

    def get_memory_state(self, vm, memory):
        """Get memorys state in guest OS"""
        mem_sys_path = "/sys/devices/system/memory/%s" % memory
        mem_state_path = os.path.join(mem_sys_path, 'state')
        session = self.get_session(vm)
        status, output = session.cmd_status_output("cat %s" % mem_state_path)
        if status != 0:
            raise exceptions.TestError("Fail to read %s state" % memory)
        return output.strip()

    def get_offline_memorys(self, vm):
        """Get unusable memory in guest OS"""
        def is_offline_memory(x):
            return self.get_memory_state(vm, x) == 'offline'

        memorys = self.get_all_memorys(vm)
        return set(filter(is_offline_memory, memorys))

    def get_all_memorys(self, vm):
        """Get all memorys detected in guest OS"""
        mem_sys_path = "/sys/devices/system/memory"
        cmd = "ls %s | grep memory" % mem_sys_path
        session = self.get_session(vm)
        output = session.cmd_output_safe(cmd, timeout=90)
        return set([_ for _ in output.splitlines() if _])
