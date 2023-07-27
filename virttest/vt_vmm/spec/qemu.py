import arch

from . import SpecHelper


class QemuSpecHelper(SpecHelper):
    def __init__(self):
        super(QemuSpecHelper, self).__init__("qemu")
        self._params = None
        
    def _define_uuid(self):
        return self._params.get("uuid")
        
    def _define_preconfig(self):
        return self._params.get_boolean("qemu_preconfig")

    def _define_sandbox(self):
        return self._params.get("qemu_sandbox")

    def _define_defaults(self):
        return self._params.get("defaults", "no")
    
    def _define_machine(self):
        machine = {}
        machine["type"] = self._params.get("machine_type")
        machine["accel"] = self._params.get("vm_accelerator")
        return machine
    
    def _define_launch_security(self):
        launch_security = {}
        
        if self._params.get("vm_secure_guest_type"):
            launch_security["id"] = "lsec0"
            launch_security["type"] = self._params.get("vm_secure_guest_type")
            if launch_security["type"] == "sev":
                launch_security["policy"] = int(self._params.get("vm_sev_policy"))
                launch_security['cbitpos'] = int(self._params.get("vm_sev_cbitpos"))
                launch_security['reduced_phys_bits'] = int(self._params.get("vm_sev_reduced_phys_bits"))
                launch_security['session_file'] = self._params.get("vm_sev_session_file")
                launch_security['dh_cert_file'] = self._params.get("vm_sev_dh_cert_file")
                launch_security['kernel_hashes'] = self._params.get("vm_sev_kernel_hashes")
            elif launch_security["type"] == "tdx":
                pass
        return launch_security
    
    def _define_iommu(self):
        iommu = {}
        
        if self._params.get("intel_iommu"):
            iommu["type"] = "intel_iommu"
        elif self._params.get("virtio_iommu"):
            iommu["type"] = "virtio_iommu"
        iommu["prps"] = {}
        iommu["bus"] = "pci.0"
        
        return iommu
    
    def _define_vga(self):
        vga = {}
        
        if self._params.get("vga"):
            vga["type"] = self._params.get("vga")
            vga["bus"] = "pci.0"
            
        return vga
    
    def _define_watchdog(self):
        watchdog = {}
        
        if self._params.get("enable_watchdog", "no") == "yes":
            watchdog["type"] = self._params.get("watchdog_device_type")
            watchdog["bus"] = "pci.0"
            watchdog["action"] = self._params.get("watchdog_action", "reset")
            
        return watchdog
    
    def _define_pci_controller(self):
        pci_controller = {}
        return pci_controller
    
    def _define_memory(self):
        memory = {}
        return memory
    
    def _define_cpu(self):
        cpu = {}
        return cpu
    
    def _define_numa(self):
        numa = []
        return numa
    
    def _define_soundcards(self):
        soundcards = []
        
        for sound_device in self._params.get("soundcards").split(","):
            soundcard = {}
            if "hda" in sound_device:
                soundcard["type"] = "intel-hba"
            elif sound_device in ("es1370", "ac97"):
                soundcard["type"] = sound_device.upper()
            else:
                soundcard["type"] = sound_device
            
            soundcard["bus"] = {'aobject': self._params.get('pci_bus', 'pci.0')}
            soundcards.append(soundcard)
        
        return soundcards
    
    def _define_monitors(self):
        monitors = []
    
        for monitor_name in self._params.objects("monitors"):
            monitor_params = self._params.object_params(monitor_name)
            monitor = {}
            monitor["type"] = monitor_params.get("monitor_type")
            monitor["bus"] = {'aobject': self._params.get('pci_bus', 'pci.0')}
            monitors.append(monitor)
        
        return monitors
    
    def _define_pvpanic(self):
        pvpanic = {}
        
        if self._params.get("enable_pvpanic") == "yes":
            if 'aarch64' in self._params.get('vm_arch_name', arch.ARCH):
                pvpanic["type"] = 'pvpanic-pci'
            else:
                pvpanic["type"] = 'pvpanic'
            pvpanic["bus"] = ""
            pvpanic["props"] = ""
            
        return pvpanic
    
    def _define_vmcoreinfo(self):
        return ""
    
    def _define_serials(self):
        serials = []
        for serial_id in self._params.objects('serials'):
            serial = {}
            serial_params = self._params.object_params(serial_id)
            serial["id"] = serial_id
            serial["type"] = serial_params.get('serial_type')
            serial["bus"] = ""
            serial["props"] = {}
            if serial["type"] == "spapr-vty":
                serial["props"]["serial_reg"] = ""

            backend = serial_params.get('chardev_backend',
                                        'unix_socket')

            if backend in ['udp', 'tcp_socket']:
                serial_params['chardev_host'] = ""
                serial_params['chardev_port'] = ""

            serial["props"]["name"] = serial_params.get('serial_name')
            serials.append(serial)
        return serials

    def _define_rngs(self):
        rngs = []
        return rngs
            
    def _parse_params(self, params):
        self._params = params
        spec = {}
        spec["uuid"] = self._define_uuid()
        spec["preconfig"] = self._define_preconfig()
        spec["sandbox"] = self._define_sandbox()
        spec["defaults"] = self._define_defaults()
        spec["machine"] = self._define_machine()
        spec["launch_security"] = self._define_launch_security()
        spec["iommu"] = self._define_iommu()
        spec["vga"] = self._define_vga()
        spec["watchdog"] = self._define_watchdog()
        spec["pci_controller"] = self._define_pci_controller()
        spec["memory"] = self._define_memory()
        spec["cpu"] = self._define_cpu()
        spec["numa"] = self._define_numa()
        spec["soundcards"] = self._define_soundcards()
        spec["monitors"] = self._define_monitors()
        spec["pvpanic"] = self._define_pvpanic()
        spec["vmcoreinfo"] = self._define_vmcoreinfo()
        spec["serials"] = self._define_serials()
        spec["rngs"] = self._define_rngs()

