from .spec import QemuSpec
from .auth_spec import QemuSpecAuth
from .balloon_spec import QemuSpecBalloon, QemuSpecBalloons
from .controller_spec import (QemuSpecControllers, QemuSpecPCIController,
                              QemuSpecUSBController, QemuSpecPCIeExtraController)
from .cpu_spec import (QemuSpecCPU, QemuSpecCPUDevice,
                       QemuSpecCPUTopology, QemuSpecCPUInfo)
from .debug_spec import QemuSpecDebug
from .defaults_spec import QemuSpecDefaults
from .disk_spec import QemuSpecDisk, QemuSpecDisks
from .encryption_spec import QemuSpecEncryption
from .filesystem_spec import QemuSpecFilesystem, QemuSpecFilesystems
from .firmware_spec import QemuSpecFirmware
from .graphic_spec import QemuSpecGraphics, QemuSpecGraphic
from .input_spec import QemuSpecInput, QemuSpecInputs
from .iommu_spec import QemuSpecIOMMU
from .iothread_spec import QemuSpecIOThreads, QemuSpecIOThread
from .keyboard_layout_spec import QemuSpecKeyboardLayout
from .launch_security_spec import QemuSpecLaunchSecurity
from .machine_spec import QemuSpecMachine
from .memory_spec import (QemuSpecMemory, QemuSpecMemoryMachine,
                          QemuSpecMemoryDevice)
from .monitor_spec import QemuSpecMonitors, QemuSpecMonitor
from .name_spec import QemuSpecName
from .net_spec import QemuSpecNet, QemuSpecNets
from .numa_spec import QemuSpecNuma
from .os_spec import QemuSpecOS
from .panic_spec import QemuSpecPanic, QemuSpecPanics
from .power_management_spec import QemuSpecPowerManagement
from .preconfig_spec import QemuSpecPreConfig
from .rng_spec import QemuSpecRng, QemuSpecRngs
from .rtc_spec import QemuSpecRTC
from .sandbox_spec import QemuSpecSandbox
from .secret_spec import QemuSpecSecret
from .serial_spec import QemuSpecSerials, QemuSpecSerial
from .sound_card_spec import QemuSpecSoundCard, QemuSpecSoundCards
from .throttle_group_spec import QemuSpecThrottleGroup, QemuSpecThrottleGroups
from .tpm_spec import QemuSpecTPM, QemuSpecTPMs
from .usb_spec import QemuSpecUSB, QemuSpecUSBDevs
from .uuid_spec import QemuSpecUUID
from .vga_spec import QemuSpecVGA
from .vm_core_info_spec import QemuSpecVMCoreInfo
from .vsock_spec import QemuSpecVsock, QemuSpecVsocks
from .watchdog_spec import QemuSpecWatchDog
