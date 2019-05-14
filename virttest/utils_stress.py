import os
import random
import time
import threading
import logging

from avocado.utils import cpu

from virttest import virsh
from virttest import utils_hotplug
from virttest import utils_net
from virttest.utils_test import libvirt
from virttest.libvirt_xml.devices.disk import Disk


class VMStressEvents():

    def __init__(self, params, env):
        """
        :param params: test param
        """
        self.host_cpu_list = cpu.cpu_online_list()
        self.iterations = int(params.get("stress_itrs", 1))
        self.host_iterations = int(params.get("host_event_itrs", 10))
        self.event_sleep_time = int(params.get("event_sleep_time", 10))
        self.itr_sleep_time = int(params.get("itr_sleep_time", 10))
        self.current_vcpu = params.get("smp", 32)
        self.max_vcpu = params.get("vcpu_maxcpus", 32)
        self.ignore_status = params.get("ignore_status", "no") == "yes"
        self.vms = env.get_all_vms()
        self.events = params.get("stress_events", "reboot")
        if self.events:
            self.events = self.events.split(',')
        else:
            self.events = []
        self.host_events = params.get("host_stress_events", "")
        if self.host_events:
            self.host_events = self.host_events.split(',')
        else:
            self.host_events = []
        self.threads = []
        self.iface_num = params.get("iface_num", '1')
        self.iface_type = params.get("iface_type", "network")
        self.iface_model = params.get("iface_model", "virtio")
        self.iface_source = eval(params.get("iface_source",
                                            "{'network':'default'}"))
        self.attach_option = params.get("attach_option", "")
        self.detach_option = params.get("detach_option", "")
        self.disk_size = params.get("virt_disk_device_size", "1")
        self.disk_type = params.get("disk_type", "file")
        self.disk_device = params.get("disk_device", "disk")
        self.disk_format = params.get("disk_format", "qcow2")
        self.device_target = params.get(
            "virt_disk_device_target", "vda").split()
        self.path = params.get("path", "")
        self.device_source_names = params.get(
            "virt_disk_device_source", "").split()
        self.disk_driver = params.get("driver_name", "qemu")

    def run_threads(self):
        for vm in self.vms:
            for event in self.events:
                self.threads.append(threading.Thread(
                    target=self.vm_stress_events, args=(event, vm)))
        for event in self.host_events:
            self.threads.append(threading.Thread(target=self.host_stress_event, args=(event,)))
        for thread in self.threads:
            thread.start()

    def wait_for_threads(self):
        for thread in self.threads:
            thread.join()

    def vm_stress_events(self, event, vm):
        """
        Stress events

        :param event: event name
        :param vm: vm object
        """
        dargs = {'ignore_status': True, 'debug': True}
        for itr in range(self.iterations):
            if "vcpupin" in event:
                for vcpu in range(int(self.current_vcpu)):
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
                result = virsh.setvcpus(vm.name, self.max_vcpu, "--live",
                                        **dargs)
                if not self.ignore_status:
                    libvirt.check_exit_status(result)
                    exp_vcpu = {'max_config': self.max_vcpu,
                                'max_live': self.max_vcpu,
                                'cur_config': self.current_vcpu,
                                'cur_live': self.max_vcpu,
                                'guest_live': self.max_vcpu}
                    utils_hotplug.check_vcpu_value(
                        vm, exp_vcpu, option="--live")
                time.sleep(self.event_sleep_time)
                result = virsh.setvcpus(vm.name, self.current_vcpu, "--live",
                                        **dargs)
                if not self.ignore_status:
                    libvirt.check_exit_status(result)
                    exp_vcpu = {'max_config': self.max_vcpu,
                                'max_live': self.max_vcpu,
                                'cur_config': self.current_vcpu,
                                'cur_live': self.current_vcpu,
                                'guest_live': self.current_vcpu}
                    utils_hotplug.check_vcpu_value(
                        vm, exp_vcpu, option="--live")
            elif "reboot" in event:
                vm.reboot()
            elif "nethotplug" in event:
                for iface_num in range(int(self.iface_num)):
                    logging.debug("Try to attach interface %d" % iface_num)
                    mac = utils_net.generate_mac_address_simple()
                    options = ("%s %s --model %s --mac %s %s" %
                               (self.iface_type, self.iface_source['network'],
                                self.iface_model, mac, self.attach_option))
                    logging.debug("VM name: %s , Options for Network attach: %s", vm.name, options)
                    ret = virsh.attach_interface(vm.name, options,
                                                 ignore_status=True)
                    time.sleep(self.event_sleep_time)
                    if not self.ignore_status:
                        libvirt.check_exit_status(ret)
                    if self.detach_option:
                        options = ("--type %s --mac %s %s" %
                                   (self.iface_type, mac, self.detach_option))
                        logging.debug("VM name: %s , Options for Network detach: %s", vm.name, options)
                        ret = virsh.detach_interface(vm.name, options,
                                                     ignore_status=True)
                        if not self.ignore_status:
                            libvirt.check_exit_status(ret)
            elif "diskhotplug" in event:
                for disk_num in range(len(self.device_source_names)):
                    disk = {}
                    disk_attach_error = False
                    disk_name = os.path.join(self.path, vm.name, self.device_source_names[disk_num])
                    device_source = libvirt.create_local_disk(
                        self.disk_type, disk_name, self.disk_size, disk_format=self.disk_format)
                    disk.update({"format": self.disk_format,
                                 "source": device_source})
                    disk_xml = Disk(self.disk_type)
                    disk_xml.device = self.disk_device
                    disk_xml.driver = {"name": self.disk_driver, "type": self.disk_format}
                    ret = virsh.attach_disk(vm.name, disk["source"], self.device_target[disk_num], self.attach_option, debug=True)
                    if not self.ignore_status:
                        libvirt.check_exit_status(ret, disk_attach_error)
                    if self.detach_option:
                        ret = virsh.detach_disk(vm.name, self.device_target[disk_num], extra=self.detach_option)
                        if not self.ignore_status:
                            libvirt.check_exit_status(ret)
                        libvirt.delete_local_disk(self.disk_type, disk_name)
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
                cpu.set_cpufreq_governor()
                logging.debug("Current governor: %s", cpu.get_cpufreq_governor())
                time.sleep(self.event_sleep_time)
            elif "cpu_idle" in event:
                idlestate = cpu.get_cpuidle_state()
                cpu.set_cpuidle_state()
                time.sleep(self.event_sleep_time)
                cpu.set_cpuidle_state(setstate=idlestate)
                time.sleep(self.event_sleep_time)
            elif "cpuoffline" in event:
                processor = self.host_cpu_list[random.randint(0, cpu.online_cpus_count()-1)]
                cpu.offline(processor)
                time.sleep(self.event_sleep_time)
                cpu.online(processor)
            else:
                raise NotImplementedError
            time.sleep(self.itr_sleep_time)
