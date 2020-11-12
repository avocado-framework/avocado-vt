from avocado.core import plugin_interfaces
from avocado.core.settings import settings
from avocado.utils import path as utils_path
from virttest.compat import is_registering_settings_required
from virttest.defaults import DEFAULT_MACHINE_TYPE
from virttest.standalone_test import (SUPPORTED_DISK_BUSES,
                                      SUPPORTED_IMAGE_TYPES,
                                      SUPPORTED_NIC_MODELS,
                                      find_default_qemu_paths)

if hasattr(plugin_interfaces, 'Init'):
    class VtInit(plugin_interfaces.Init):

        name = 'vt-init'
        description = "VT plugin initilization"

        def initialize(self):
            if not is_registering_settings_required():
                return

            # [vt.setup] section
            section = 'vt.setup'
            help_msg = 'Backup image before testing (if not already backed up)'
            settings.register_option(section, 'backup_image_before_test',
                                     help_msg=help_msg, key_type=bool,
                                     default=True)

            help_msg = 'Restore image after testing (if backup present)'
            settings.register_option(section, 'restore_image_after_test',
                                     help_msg=help_msg, key_type=bool,
                                     default=True)

            help_msg = 'Keep guest running between tests (faster, but unsafe)'
            settings.register_option(section, 'keep_guest_running',
                                     help_msg=help_msg, key_type=bool,
                                     default=False)

            # [vt.common] section
            section = 'vt.common'

            help_msg = ('Data dir path. If none specified, the default '
                        'virt-test data dir will be used')
            settings.register_option(section, 'data_dir',
                                     help_msg=help_msg,
                                     default='')

            help_msg = ('Make the temporary dir path persistent across jobs if'
                        ' needed. By default the data in the temporary '
                        'directory will be wiped after each test in some cases'
                        ' and after each job in others.')
            settings.register_option(section, 'tmp_dir',
                                     help_msg=help_msg,
                                     default='')

            help_msg = ('Enable only type specific tests. Shared tests will '
                        'not be tested')
            settings.register_option(section, 'type_specific_only',
                                     help_msg=help_msg, key_type=bool,
                                     default=False)

            help_msg = ('RAM dedicated to the main VM. Usually defaults to '
                        '1024, as set in "base.cfg", but can be a different '
                        'value depending on the various other configuration '
                        'files such as configuration files under "guest-os" '
                        'and test provider specific files')
            settings.register_option(section, 'mem',
                                     help_msg=help_msg,
                                     default=None)

            help_msg = 'Architecture under test'
            settings.register_option(section, 'arch',
                                     help_msg=help_msg,
                                     default=None)

            help_msg = 'Machine type under test'
            settings.register_option(section, 'machine_type',
                                     help_msg=help_msg,
                                     default=DEFAULT_MACHINE_TYPE)

            help_msg = 'Nettype (bridge, user, none)'
            settings.register_option(section, 'nettype',
                                     help_msg=help_msg,
                                     default='')

            help_msg = 'Bridge name to be used if you select bridge as a nettype'
            settings.register_option(section, 'netdst',
                                     help_msg=help_msg,
                                     default='virbr0')

            # [vt.qemu] section
            section = 'vt.qemu'

            try:
                default_qemu_bin_path = find_default_qemu_paths()[0]
            except (RuntimeError, utils_path.CmdNotFoundError):
                default_qemu_bin_path = None
            help_msg = 'Path to a custom qemu binary to be tested'
            settings.register_option(section, 'qemu_bin',
                                     help_msg=help_msg,
                                     default=default_qemu_bin_path)

            help_msg = ('Path to a custom qemu binary to be tested for the '
                        'destination of a migration, overrides qemu_bin for '
                        'that particular purpose')
            settings.register_option(section, 'qemu_dst_bin',
                                     help_msg=help_msg,
                                     default=default_qemu_bin_path)

            help_msg = 'Accelerator used to run qemu (kvm or tcg)'
            settings.register_option(section, 'accel',
                                     help_msg=help_msg,
                                     default='kvm')

            help_msg = ('Whether to enable vhost for qemu (on/off/force). '
                        'Depends on nettype=bridge')
            settings.register_option(section, 'vhost',
                                     help_msg=help_msg,
                                     default='off')

            help_msg = 'Monitor type (human or qmp)'
            settings.register_option(section, 'monitor',
                                     help_msg=help_msg,
                                     default='')

            help_msg = 'Number of virtual cpus to use (1 or 2)'
            settings.register_option(section, 'smp',
                                     help_msg=help_msg,
                                     default='2')

            help_msg = 'Image format type to use (any valid qemu format)'
            settings.register_option(section, 'image_type',
                                     help_msg=help_msg,
                                     default=SUPPORTED_IMAGE_TYPES[0])

            help_msg = 'Guest network card model (any valid qemu card)'
            settings.register_option(section, 'nic_model',
                                     help_msg=help_msg,
                                     default=SUPPORTED_NIC_MODELS[0])

            help_msg = ('Guest disk bus for main image. One of ide, scsi, '
                        'virtio_blk, virtio_scsi, lsi_scsi, ahci, usb2 '
                        'or xenblk. Note: Older qemu versions and/or '
                        'operating systems (such as WinXP) might not support '
                        'virtio_scsi. Please use virtio_blk or ide instead.')
            settings.register_option(section, 'disk_bus',
                                     help_msg=help_msg,
                                     default=SUPPORTED_DISK_BUSES[0])

            help_msg = 'Enable qemu sandboxing (on/off)'
            settings.register_option(section, 'sandbox',
                                     help_msg=help_msg,
                                     default='on')

            help_msg = ('Prevent qemu from loading sysconfdir/qemu.conf '
                        'and sysconfdir/target-ARCH.conf at startup (yes/no)')
            settings.register_option(section, 'defconfig',
                                     help_msg=help_msg,
                                     default='yes')

            help_msg = ('Use MALLOC_PERTURB_ env variable set to 1 to help '
                        'catch memory allocation problems on qemu (yes/no)')
            settings.register_option(section, 'malloc_perturb',
                                     help_msg=help_msg,
                                     default='yes')

            # [vt.libvirt] section
            help_msg = ('Test connect URI for libvirt (qemu:///system, '
                        'lxc:///)')
            settings.register_option('vt.libvirt', 'connect_uri',
                                     help_msg=help_msg,
                                     default='qemu:///session')

            # [vt.debug] section
            help_msg = ('Do not clean up tmp files or VM processes at the end '
                        'of a virt-test execution')
            settings.register_option('vt.debug', 'no_cleanup',
                                     help_msg=help_msg, key_type=bool,
                                     default=False)

            # [plugins.vtjoblock] section
            help_msg = 'Directory in which to write the lock file'
            settings.register_option('plugins.vtjoblock', 'dir',
                                     help_msg=help_msg,
                                     default='/tmp')
