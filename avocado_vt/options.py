# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2015
# Author: Lucas Meneghel Rodrigues <lmr@redhat.com>

"""
Avocado VT plugin
"""

import logging
import os

from avocado.utils import path as utils_path

from virttest import cartesian_config
from virttest import data_dir
from virttest import defaults
from virttest import standalone_test
from virttest.compat import get_opt, set_opt, set_opt_from_settings
from virttest.standalone_test import SUPPORTED_DISK_BUSES
from virttest.standalone_test import SUPPORTED_IMAGE_TYPES
from virttest.standalone_test import SUPPORTED_LIBVIRT_DRIVERS
from virttest.standalone_test import SUPPORTED_NET_TYPES
from virttest.standalone_test import SUPPORTED_NIC_MODELS
from virttest.standalone_test import SUPPORTED_TEST_TYPES


LOG = logging.getLogger('avocado.vt.options')


class VirtTestOptionsProcess(object):

    """
    Pick virt test options and parse them to get to a cartesian parser.
    """

    def __init__(self, config):
        """
        Parses options and initializes attributes.
        """
        self.config = config
        # Here we'll inject values from the config file.
        # Doing this makes things configurable yet the number of options
        # is not overwhelming.
        # setup section
        set_opt_from_settings(self.config,
                              'vt.setup', 'backup_image_before_test',
                              key_type=bool, default=True)
        set_opt_from_settings(self.config,
                              'vt.setup', 'restore_image_after_test',
                              key_type=bool, default=True)
        set_opt_from_settings(self.config,
                              'vt.setup', 'keep_guest_running',
                              key_type=bool, default=False)
        # common section
        set_opt_from_settings(self.config,
                              'vt.common', 'data_dir',
                              default=None)
        set_opt_from_settings(self.config,
                              'vt.common', 'tmp_dir',
                              default='')
        set_opt_from_settings(self.config,
                              'vt.common', 'type_specific',
                              key_type=bool, default=False)
        set_opt_from_settings(self.config,
                              'vt.common', 'mem',
                              default=None)
        set_opt_from_settings(self.config,
                              'vt.common', 'nettype',
                              default=None)
        set_opt_from_settings(self.config,
                              'vt.common', 'netdst',
                              default='virbr0')
        # qemu section
        set_opt_from_settings(self.config,
                              'vt.qemu', 'accel',
                              default='kvm')
        set_opt_from_settings(self.config,
                              'vt.qemu', 'vhost',
                              default='off')
        set_opt_from_settings(self.config,
                              'vt.qemu', 'monitor',
                              default=None)
        set_opt_from_settings(self.config,
                              'vt.qemu', 'smp',
                              default='2')
        set_opt_from_settings(self.config,
                              'vt.qemu', 'image_type',
                              default=SUPPORTED_IMAGE_TYPES[0])
        set_opt_from_settings(self.config,
                              'vt.qemu', 'nic_model',
                              default=SUPPORTED_NIC_MODELS[0])
        set_opt_from_settings(self.config,
                              'vt.qemu', 'disk_bus',
                              default=SUPPORTED_DISK_BUSES[0])
        set_opt_from_settings(self.config,
                              'vt.qemu', 'sandbox',
                              default='on')
        set_opt_from_settings(self.config,
                              'vt.qemu', 'defconfig',
                              default='yes')
        set_opt_from_settings(self.config,
                              'vt.qemu', 'malloc_perturb',
                              default='yes')

        # debug section
        set_opt_from_settings(self.config,
                              'vt.debug', 'no_cleanup',
                              key_type=bool, default=False)

        self.cartesian_parser = None

    def _process_qemu_bin(self):
        """
        Puts the value of the qemu bin option in the cartesian parser command.
        """
        qemu_bin_setting = ('option --vt-qemu-bin or '
                            'config vt.qemu.qemu_bin')
        if (get_opt(self.config, 'vt.config') and
                get_opt(self.config, 'vt.qemu.qemu_bin') is None):
            LOG.info("Config provided and no %s set. Not trying "
                     "to automatically set qemu bin.", qemu_bin_setting)
        else:
            (qemu_bin_path, qemu_img_path, qemu_io_path,
             qemu_dst_bin_path) = standalone_test.find_default_qemu_paths(
                 get_opt(self.config, 'vt.qemu.qemu_bin'),
                 get_opt(self.config, 'vt.qemu.qemu_dst_bin'))
            self.cartesian_parser.assign("qemu_binary", qemu_bin_path)
            self.cartesian_parser.assign("qemu_img_binary", qemu_img_path)
            self.cartesian_parser.assign("qemu_io_binary", qemu_io_path)
            if qemu_dst_bin_path is not None:
                self.cartesian_parser.assign("qemu_dst_binary",
                                             qemu_dst_bin_path)

    def _process_qemu_img(self):
        """
        Puts the value of the qemu bin option in the cartesian parser command.
        """
        qemu_img_setting = ('option --vt-qemu-img or '
                            'config vt.qemu.qemu_img')
        if (get_opt(self.config, 'vt.config') and
                get_opt(self.config, 'vt.qemu.bin') is None):
            LOG.info("Config provided and no %s set. Not trying "
                     "to automatically set qemu bin", qemu_img_setting)
        else:
            (_, qemu_img_path,
             _, _) = standalone_test.find_default_qemu_paths(
                 get_opt(self.config, 'vt.qemu.qemu_bin'),
                 get_opt(self.config, 'vt.qemu.qemu_dst_bin'))
            self.cartesian_parser.assign("qemu_img_binary", qemu_img_path)

    def _process_qemu_accel(self):
        """
        Puts the value of the qemu bin option in the cartesian parser command.
        """
        if get_opt(self.config, 'vt.qemu.accel') == 'tcg':
            self.cartesian_parser.assign("disable_kvm", "yes")

    def _process_bridge_mode(self):
        nettype_setting = 'config vt.qemu.nettype'
        if not get_opt(self.config, 'vt.config'):
            # Let's select reasonable defaults depending on vt.type
            if not get_opt(self.config, 'vt.common.nettype'):
                if get_opt(self.config, 'vt.type') == 'qemu':
                    set_opt(self.config, 'vt.common.nettype',
                            ("bridge" if os.getuid() == 0 else "user"))
                elif get_opt(self.config, 'vt.type') == 'spice':
                    set_opt(self.config, 'vt.common.nettype', "none")
                else:
                    set_opt(self.config, 'vt.common.nettype', "bridge")

            if get_opt(self.config, 'vt.common.nettype') not in SUPPORTED_NET_TYPES:
                raise ValueError("Invalid %s '%s'. "
                                 "Valid values: (%s)" %
                                 (nettype_setting,
                                  get_opt(self.config, 'vt.common.nettype'),
                                  ", ".join(SUPPORTED_NET_TYPES)))
            if get_opt(self.config, 'vt.common.nettype') == 'bridge':
                if os.getuid() != 0:
                    raise ValueError("In order to use %s '%s' you "
                                     "need to be root" % (nettype_setting,
                                                          get_opt(self.config, 'vt.common.nettype')))
                self.cartesian_parser.assign("nettype", "bridge")
                self.cartesian_parser.assign("netdst", get_opt(self.config, 'vt.common.netdst'))
            elif get_opt(self.config, 'vt.common.nettype') == 'user':
                self.cartesian_parser.assign("nettype", "user")
        else:
            LOG.info("Config provided, ignoring %s", nettype_setting)

    def _process_monitor(self):
        if not get_opt(self.config, 'vt.config'):
            if not get_opt(self.config, 'vt.qemu.monitor'):
                pass
            elif get_opt(self.config, 'vt.qemu.monitor') == 'qmp':
                self.cartesian_parser.assign("monitor_type", "qmp")
            elif get_opt(self.config, 'vt.qemu.monitor') == 'human':
                self.cartesian_parser.assign("monitor_type", "human")
        else:
            LOG.info("Config provided, ignoring monitor setting")

    def _process_smp(self):
        smp_setting = 'config vt.qemu.smp'
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.qemu.smp') == '1':
                self.cartesian_parser.only_filter("up")
            elif get_opt(self.config, 'vt.qemu.smp') == '2':
                self.cartesian_parser.only_filter("smp2")
            else:
                try:
                    self.cartesian_parser.only_filter("up")
                    self.cartesian_parser.assign(
                        "smp", int(get_opt(self.config, 'vt.qemu.smp')))
                except ValueError:
                    raise ValueError("Invalid %s '%s'. Valid value: (1, 2, "
                                     "or integer)" % get_opt(self.config, 'vt.qemu.smp'))
        else:
            LOG.info("Config provided, ignoring %s", smp_setting)

    def _process_arch(self):
        if get_opt(self.config, 'vt.config'):
            arch_setting = "option --vt-arch or config vt.common.arch"
            LOG.info("Config provided, ignoring %s", arch_setting)
            return

        arch = get_opt(self.config, 'vt.common.arch')
        if arch:
            self.cartesian_parser.only_filter(arch)

    def _process_machine_type(self):
        machine_type_setting = ("option --vt-machine-type or config "
                                "vt.common.machine_type")
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.common.machine_type') is None:
                # TODO: this is x86-specific, instead we can get the default
                # arch from qemu binary and run on all supported machine types
                if ((get_opt(self.config, 'vt.common.arch') is None) and
                        (get_opt(self.config, 'vt.guest_os') is None)):
                    self.cartesian_parser.only_filter(
                        defaults.DEFAULT_MACHINE_TYPE)
            else:
                self.cartesian_parser.only_filter(get_opt(self.config,
                                                          'vt.common.machine_type'))
        else:
            LOG.info("Config provided, ignoring %s", machine_type_setting)

    def _process_image_type(self):
        image_type_setting = 'config vt.qemu.image_type'
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.qemu.image_type') in SUPPORTED_IMAGE_TYPES:
                self.cartesian_parser.only_filter(get_opt(self.config, 'vt.qemu.image_type'))
            else:
                self.cartesian_parser.only_filter("raw")
                # The actual param name is image_format.
                self.cartesian_parser.assign("image_format",
                                             get_opt(self.config, 'vt.qemu.image_type'))
        else:
            LOG.info("Config provided, ignoring %s", image_type_setting)

    def _process_nic_model(self):
        nic_model_setting = 'config vt.qemu.nic_model'
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.qemu.nic_model') in SUPPORTED_NIC_MODELS:
                self.cartesian_parser.only_filter(get_opt(self.config, 'vt.qemu.nic_model'))
            else:
                self.cartesian_parser.only_filter("nic_custom")
                self.cartesian_parser.assign(
                    "nic_model", get_opt(self.config, 'vt.qemu.nic_model'))
        else:
            LOG.info("Config provided, ignoring %s", nic_model_setting)

    def _process_disk_buses(self):
        disk_bus_setting = 'config vt.qemu.disk_bus'
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.qemu.disk_bus') in SUPPORTED_DISK_BUSES:
                self.cartesian_parser.only_filter(get_opt(self.config, 'vt.qemu.disk_bus'))
            else:
                raise ValueError("Invalid %s '%s'. Valid values: %s" %
                                 (disk_bus_setting,
                                  get_opt(self.config, 'vt.qemu.disk_bus'),
                                  SUPPORTED_DISK_BUSES))
        else:
            LOG.info("Config provided, ignoring %s", disk_bus_setting)

    def _process_vhost(self):
        nettype_setting = 'config vt.qemu.nettype'
        vhost_setting = 'config vt.qemu.vhost'
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.common.nettype') == "bridge":
                if get_opt(self.config, 'vt.qemu.vhost') == "on":
                    self.cartesian_parser.assign("vhost", "on")
                elif get_opt(self.config, 'vt.qemu.vhost') == "force":
                    self.cartesian_parser.assign("netdev_extra_params",
                                                 '",vhostforce=on"')
                    self.cartesian_parser.assign("vhost", "on")
            else:
                if get_opt(self.config, 'vt.qemu.vhost') in ["on", "force"]:
                    raise ValueError("%s '%s' is incompatible with %s '%s'"
                                     % (nettype_setting,
                                        get_opt(self.config, 'vt.common.nettype'),
                                        vhost_setting,
                                        get_opt(self.config, 'vt.qemu.vhost')))
        else:
            LOG.info("Config provided, ignoring %s", vhost_setting)

    def _process_qemu_sandbox(self):
        sandbox_setting = 'config vt.qemu.sandbox'
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.qemu.sandbox') == "off":
                self.cartesian_parser.assign("qemu_sandbox", "off")
        else:
            LOG.info("Config provided, ignoring %s", sandbox_setting)

    def _process_qemu_defconfig(self):
        defconfig_setting = 'config vt.qemu.sandbox'
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.qemu.defconfig') == "no":
                self.cartesian_parser.assign("defconfig", "no")
        else:
            LOG.info("Config provided, ignoring %s", defconfig_setting)

    def _process_malloc_perturb(self):
        self.cartesian_parser.assign("malloc_perturb",
                                     get_opt(self.config, 'vt.qemu.malloc_perturb'))

    def _process_qemu_specific_options(self):
        """
        Calls for processing all options specific to the qemu test.

        This method modifies the cartesian set by parsing additional lines.
        """

        self._process_qemu_bin()
        self._process_qemu_accel()
        self._process_monitor()
        self._process_smp()
        self._process_image_type()
        self._process_nic_model()
        self._process_disk_buses()
        self._process_vhost()
        self._process_malloc_perturb()
        self._process_qemu_sandbox()

    def _process_lvsb_specific_options(self):
        """
        Calls for processing all options specific to LVSB test
        """
        set_opt(self.config, 'no_downloads', True)

    def _process_libvirt_specific_options(self):
        """
        Calls for processing all options specific to libvirt test.
        """
        uri_setting = 'config vt.libvirt.connect_uri'
        if get_opt(self.config, 'vt.libvirt.connect_uri'):
            driver_found = False
            for driver in SUPPORTED_LIBVIRT_DRIVERS:
                if get_opt(self.config, 'vt.libvirt.connect_uri').count(driver):
                    driver_found = True
                    self.cartesian_parser.only_filter(driver)
            if not driver_found:
                raise ValueError("Unsupported %s '%s'"
                                 % (uri_setting,
                                    get_opt(self.config,
                                            'vt.libvbirt.connect_uri')))
        else:
            self.cartesian_parser.only_filter("qemu")

    def _process_guest_os(self):
        guest_os_setting = 'option --vt-guest-os'

        if get_opt(self.config, 'vt.type') == 'spice':
            LOG.info("Ignoring predefined OS: %s", guest_os_setting)
            return

        if not get_opt(self.config, 'vt.config'):
            if len(standalone_test.get_guest_name_list(self.config)) == 0:
                raise ValueError("%s '%s' is not on the known guest os for "
                                 "arch '%s' and machine type '%s'. (see "
                                 "--vt-list-guests)"
                                 % (guest_os_setting,
                                    get_opt(self.config, 'vt.guest_os'),
                                    get_opt(self.config, 'vt.common.arch'),
                                    get_opt(self.config, 'vt.common.machine_type')))
            self.cartesian_parser.only_filter(
                get_opt(self.config, 'vt.guest_os') or defaults.DEFAULT_GUEST_OS)
        else:
            LOG.info("Config provided, ignoring %s", guest_os_setting)

    def _process_restart_vm(self):
        if not get_opt(self.config, 'vt.config'):
            if not get_opt(self.config, 'vt.setup.keep_guest_running'):
                self.cartesian_parser.assign("kill_vm", "yes")

    def _process_restore_image(self):
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.setup.backup_image_before_test'):
                self.cartesian_parser.assign("backup_image_before_testing",
                                             "yes")
            if get_opt(self.config, 'vt.setup.restore_image_after_test'):
                self.cartesian_parser.assign("restore_image_after_testing",
                                             "yes")

    def _process_mem(self):
        if not get_opt(self.config, 'vt.config'):
            mem = get_opt(self.config, 'vt.common.mem')
            if mem is not None:
                self.cartesian_parser.assign("mem", mem)

    def _process_tcpdump(self):
        """
        Verify whether we can run tcpdump. If we can't, turn it off.
        """
        try:
            tcpdump_path = utils_path.find_command('tcpdump')
        except utils_path.CmdNotFoundError:
            tcpdump_path = None

        non_root = os.getuid() != 0

        if tcpdump_path is None or non_root:
            self.cartesian_parser.assign("run_tcpdump", "no")

    def _process_no_filter(self):
        if get_opt(self.config, 'vt.no_filter'):
            for item in get_opt(self.config, 'vt.no_filter').split(' '):
                self.cartesian_parser.no_filter(item)

    def _process_only_filter(self):
        if get_opt(self.config, 'vt.only_filter'):
            for item in get_opt(self.config, 'vt.only_filter').split(' '):
                self.cartesian_parser.only_filter(item)

    def _process_extra_params(self):
        if get_opt(self.config, "vt.extra_params"):
            for param in get_opt(self.config, "vt.extra_params"):
                key, value = param.split('=', 1)
                self.cartesian_parser.assign(key, value)

    def _process_only_type_specific(self):
        if not get_opt(self.config, 'vt.config'):
            if get_opt(self.config, 'vt.type_specific'):
                self.cartesian_parser.only_filter("(subtest=type_specific)")

    def _process_general_options(self):
        """
        Calls for processing all generic options.

        This method modifies the cartesian set by parsing additional lines.
        """
        self._process_guest_os()
        self._process_arch()
        self._process_machine_type()
        self._process_restart_vm()
        self._process_restore_image()
        self._process_mem()
        self._process_tcpdump()
        self._process_no_filter()
        self._process_only_filter()
        self._process_qemu_img()
        self._process_bridge_mode()
        self._process_only_type_specific()

    def _process_backend_specific_options(self, vt_type):
        """
        Calls for processing of backend specific options
        """
        backend_specific_options = {
            'qemu': self._process_qemu_specific_options,
            'lvsb': self._process_lvsb_specific_options,
            'openvswitch': self._process_qemu_specific_options,
            'libvirt': self._process_libvirt_specific_options,
            'spice': self._process_spice_specific_options,
            }
        specific_opts = backend_specific_options.get(vt_type, None)
        if specific_opts is not None:
            specific_opts()

    def _process_spice_specific_options(self):
        """
        Calls for processing all options specific to spice test
        """
        # We can call here for self._process_qemu_specific_options()
        # to process some --options, but let SpiceQA tests will be independent
        set_opt(self.config, 'no_downloads', True)

    def _process_options(self):
        """
        Process the options given in the command line.
        """
        cfg = None
        vt_type_setting = 'option --vt-type'
        vt_config_setting = 'option --vt-config'

        vt_type = get_opt(self.config, 'vt.type')
        vt_config = get_opt(self.config, 'vt.config')

        if (not vt_type) and (not vt_config):
            raise ValueError("No %s or %s specified" %
                             (vt_type_setting, vt_config_setting))

        if vt_type:
            if vt_type not in SUPPORTED_TEST_TYPES:
                raise ValueError("Invalid %s %s. Valid values: %s. "
                                 % (vt_type_setting,
                                    vt_type,
                                    " ".join(SUPPORTED_TEST_TYPES)))

        self.cartesian_parser = cartesian_config.Parser(debug=False)

        if vt_config:
            cfg = os.path.abspath(vt_config)
            self.cartesian_parser.parse_file(cfg)
        elif get_opt(self.config, 'vt.filter.default_filters'):
            cfg = data_dir.get_backend_cfg_path(vt_type,
                                                'tests-shared.cfg')
            self.cartesian_parser.parse_file(cfg)
            for arg in ('no_9p_export', 'no_virtio_rng', 'no_pci_assignable',
                        'smallpages', 'default_bios', 'bridge'):
                if arg not in get_opt(self.config, 'vt.filter.default_filters'):
                    self.cartesian_parser.only_filter(arg)
            if 'image_backend' not in get_opt(self.config, 'vt.filter.default_filters'):
                self.cartesian_parser.only_filter('(image_backend='
                                                  'filesystem)')
            if 'multihost' not in get_opt(self.config, 'vt.filter.default_filters'):
                self.cartesian_parser.no_filter('multihost')
        else:
            cfg = data_dir.get_backend_cfg_path(vt_type, 'tests.cfg')
            self.cartesian_parser.parse_file(cfg)

        if vt_type != 'lvsb':
            self._process_general_options()

        self._process_backend_specific_options(vt_type)
        self._process_extra_params()

    def get_parser(self):
        self._process_options()
        return self.cartesian_parser
