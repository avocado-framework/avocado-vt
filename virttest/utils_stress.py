import os
import random
import time
import threading
import logging

from avocado.utils import cpu
from avocado.core import exceptions

from virttest import virsh
from virttest import cpu as cpuutil
from virttest import utils_net
from virttest import utils_package
from virttest.utils_test import libvirt
from virttest.libvirt_xml.devices.disk import Disk

LOG = logging.getLogger('avocado.' + __name__)


class VMStressEvents():

    def __init__(self, params, env):
        """
        :param params: test param
        """
        self.host_cpu_list = cpu.online_list() if hasattr(cpu, 'online_list') else cpu.cpu_online_list()
        self.iterations = int(params.get("stress_itrs", 1))
        self.host_iterations = int(params.get("host_event_itrs", 10))
        self.event_sleep_time = int(params.get("event_sleep_time", 10))
        self.itr_sleep_time = int(params.get("itr_sleep_time", 10))
        self.ignore_status = params.get("ignore_status", "no") == "yes"
        self.vms = env.get_all_vms()
        self.params = params
        self.host_events = params.get("host_stress_events", "")
        if self.host_events:
            self.host_events = self.host_events.split(',')
        else:
            self.host_events = []
        self.threads = []

    def run_threads(self):
        for vm in self.vms:
            vm_params = self.params.object_params(vm.name)
            events = vm_params.get("stress_events", "reboot")
            if events:
                events = events.split(',')
            else:
                events = []
            for event in events:
                self.threads.append(threading.Thread(
                    target=self.vm_stress_events, args=(event, vm, vm_params)))
        for event in self.host_events:
            self.threads.append(threading.Thread(target=self.host_stress_event, args=(event,)))
        for thread in self.threads:
            thread.start()

    def wait_for_threads(self):
        for thread in self.threads:
            thread.join()

    def vm_stress_events(self, event, vm, params):
        """
        Stress events

        :param event: event name
        :param vm: vm object
        """
        current_vcpu = int(params.get("smp", 2))
        max_vcpu = int(params.get("vcpu_maxcpus", 2))
        iface_num = params.get("iface_num", '1')
        iface_type = params.get("iface_type", "network")
        iface_model = params.get("iface_model", "virtio")
        iface_source = eval(params.get("iface_source", "{'network':'default'}"))
        attach_option = params.get("attach_option", "")
        detach_option = params.get("detach_option", "")
        disk_size = params.get("virt_disk_device_size", "1")
        disk_type = params.get("disk_type", "file")
        disk_device = params.get("disk_device", "disk")
        disk_format = params.get("disk_format", "qcow2")
        device_target = params.get("virt_disk_device_target", "vda").split()
        path = params.get("path", "")
        device_source_names = params.get("virt_disk_device_source", "").split()
        disk_driver = params.get("driver_name", "qemu")
        self.ignore_status = params.get("ignore_status", "no") == "yes"
        dargs = {'ignore_status': True, 'debug': True}
        for itr in range(self.iterations):
            if "vcpupin" in event:
                for vcpu in range(current_vcpu):
                    result = virsh.vcpupin(vm.name, vcpu,
                                           random.choice(self.host_cpu_list),
                                           **dargs)
                    if not self.ignore_status:
                        libvirt.check_exit_status(result)
            elif "emulatorpin" in event:
                result = virsh.emulatorpin(vm.name,
                                           random.choice(self.host_cpu_list),
                                           **dargs)
                if not self.ignore_status:
                    libvirt.check_exit_status(result)
            elif "suspend" in event:
                result = virsh.suspend(vm.name, **dargs)
                if not self.ignore_status:
                    libvirt.check_exit_status(result)
                time.sleep(self.event_sleep_time)
                result = virsh.resume(vm.name, **dargs)
                if not self.ignore_status:
                    libvirt.check_exit_status(result)
            elif "cpuhotplug" in event:
                result = virsh.setvcpus(vm.name, max_vcpu, "--live",
                                        **dargs)
                if not self.ignore_status:
                    libvirt.check_exit_status(result)
                    exp_vcpu = {'max_config': max_vcpu,
                                'max_live': max_vcpu,
                                'cur_config': current_vcpu,
                                'cur_live': max_vcpu,
                                'guest_live': max_vcpu}
                    cpuutil.check_vcpu_value(
                        vm, exp_vcpu, option="--live")
                time.sleep(self.event_sleep_time)
                result = virsh.setvcpus(vm.name, current_vcpu, "--live",
                                        **dargs)
                if not self.ignore_status:
                    libvirt.check_exit_status(result)
                    exp_vcpu = {'max_config': max_vcpu,
                                'max_live': max_vcpu,
                                'cur_config': current_vcpu,
                                'cur_live': current_vcpu,
                                'guest_live': current_vcpu}
                    cpuutil.check_vcpu_value(
                        vm, exp_vcpu, option="--live")
            elif "reboot" in event:
                vm.reboot()
            elif "nethotplug" in event:
                for iface_num in range(int(iface_num)):
                    LOG.debug("Try to attach interface %d" % iface_num)
                    mac = utils_net.generate_mac_address_simple()
                    options = ("%s %s --model %s --mac %s %s" %
                               (iface_type, iface_source['network'],
                                iface_model, mac, attach_option))
                    LOG.debug("VM name: %s , Options for Network attach: %s", vm.name, options)
                    ret = virsh.attach_interface(vm.name, options,
                                                 ignore_status=True)
                    time.sleep(self.event_sleep_time)
                    if not self.ignore_status:
                        libvirt.check_exit_status(ret)
                    if detach_option:
                        options = ("--type %s --mac %s %s" %
                                   (iface_type, mac, detach_option))
                        LOG.debug("VM name: %s , Options for Network detach: %s", vm.name, options)
                        ret = virsh.detach_interface(vm.name, options,
                                                     ignore_status=True)
                        if not self.ignore_status:
                            libvirt.check_exit_status(ret)
            elif "diskhotplug" in event:
                for disk_num in range(len(device_source_names)):
                    disk = {}
                    disk_attach_error = False
                    disk_name = os.path.join(path, vm.name, device_source_names[disk_num])
                    device_source = libvirt.create_local_disk(disk_type, disk_name, disk_size, disk_format=disk_format)
                    disk.update({"format": disk_format,
                                 "source": device_source})
                    disk_xml = Disk(disk_type)
                    disk_xml.device = disk_device
                    disk_xml.driver = {"name": disk_driver, "type": disk_format}
                    ret = virsh.attach_disk(vm.name, disk["source"], device_target[disk_num], attach_option, debug=True)
                    if not self.ignore_status:
                        libvirt.check_exit_status(ret, disk_attach_error)
                    if detach_option:
                        ret = virsh.detach_disk(vm.name, device_target[disk_num], extra=detach_option)
                        if not self.ignore_status:
                            libvirt.check_exit_status(ret)
                        libvirt.delete_local_disk(disk_type, disk_name)
            else:
                raise NotImplementedError
            time.sleep(self.itr_sleep_time)

    def host_stress_event(self, event):
        """
        Host Stress events

        :param event: event name
        """
        for itr in range(self.host_iterations):
            if "cpu_freq_governor" in event:
                cpu.set_freq_governor() if hasattr(cpu, 'set_freq_governor') else cpu.set_cpufreq_governor()
                LOG.debug("Current governor: %s", cpu.get_freq_governor() if hasattr(cpu, 'get_freq_governor') else cpu.get_cpufreq_governor())
                time.sleep(self.event_sleep_time)
            elif "cpu_idle" in event:
                idlestate = cpu.get_idle_state() if hasattr(cpu, 'get_idle_state') else cpu.get_cpuidle_state()
                cpu.set_idle_state() if hasattr(cpu, 'set_idle_state') else cpu.set_cpuidle_state()
                time.sleep(self.event_sleep_time)
                cpu.set_idle_state(setstate=idlestate) if hasattr(cpu, 'set_idle_state') else cpu.set_cpuidle_state(setstate=idlestate)
                time.sleep(self.event_sleep_time)
            elif "cpuoffline" in event:
                online_count = cpu.online_count() if hasattr(cpu, 'online_count') else cpu.online_cpus_count()
                processor = self.host_cpu_list[random.randint(0, online_count-1)]
                cpu.offline(processor)
                time.sleep(self.event_sleep_time)
                cpu.online(processor)
            else:
                raise NotImplementedError
            time.sleep(self.itr_sleep_time)


def install_stressapptest(vm):
    """
    Install stressapptest cmd

    :param vm: the vm to be installed with stressapptest
    """
    session = vm.wait_for_login(timeout=360)
    name = ["git", "gcc", "gcc-c++", "make"]
    if not utils_package.package_install(name, session, timeout=300):
        raise exceptions.TestError("Installation of packages %s in guest "
                                   "failed" % name)

    app_repo = "git clone https://github.com/stressapptest/" \
               "stressapptest.git"
    stressapptest_install_cmd = "rm -rf stressapptest " \
                                "&& %s" \
                                " && cd stressapptest " \
                                "&& ./configure " \
                                "&& make " \
                                "&& make install" % app_repo
    s, o = session.cmd_status_output(stressapptest_install_cmd)
    if s:
        raise exceptions.TestError("Failed to install stressapptest "
                                   "in guest: '%s'" % o)
    session.close()
