import random
import time
import threading

from avocado.utils import cpu

from virttest import virsh
from virttest import utils_hotplug
from virttest.utils_test import libvirt


class VMStressEvents():
    def __init__(self, params, env):
        """
        :param params: test param
        """
        self.host_cpu_list = cpu.cpu_online_list()
        self.iterations = int(params.get("stress_itrs", 20))
        self.event_sleep_time = int(params.get("event_sleep_time", 10))
        self.current_vcpu = params.get("smp", 32)
        self.max_vcpu = params.get("virsh_maxcpus", 32)
        self.ignore_status = params.get("ignore_status", "no") == "yes"
        self.vms = env.get_all_vms()
        self.events = params.get("stress_events", "reboot").split(',')
        self.threads = []

    def run_threads(self):
        for vm in self.vms:
            for event in self.events:
                self.threads.append(threading.Thread(target=self.vm_stress_events, args=(event, vm)))
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
                for vcpu in range(int(self.current_vcpu)):
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
                    utils_hotplug.check_vcpu_value(vm, exp_vcpu, option="--live")
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
                    utils_hotplug.check_vcpu_value(vm, exp_vcpu, option="--live")
            elif "reboot" in event:
                vm.reboot()
            else:
                raise NotImplementedError
