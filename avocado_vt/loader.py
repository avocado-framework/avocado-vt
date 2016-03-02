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
import sys

from avocado.core import loader
from avocado.core import output

from virttest import bootstrap
from virttest import cartesian_config
from virttest import data_dir
from virttest import standalone_test
from virttest import storage

from .options import VirtTestOptionsProcess
from .test import VirtTest


LOG = logging.getLogger("avocado.app")


def guest_listing(options):
    if options.vt_type == 'lvsb':
        raise ValueError("No guest types available for lvsb testing")
    index = 0
    LOG.debug("Searched %s for guest images\n",
              os.path.join(data_dir.get_data_dir(), 'images'))
    LOG.debug("Available guests in config:\n")
    guest_name_parser = standalone_test.get_guest_name_parser(options)
    guest_name_parser.only_filter('i440fx')
    for params in guest_name_parser.get_dicts():
        index += 1
        base_dir = params.get("images_base_dir", data_dir.get_data_dir())
        image_name = storage.get_image_filename(params, base_dir)
        name = params['name']
        if os.path.isfile(image_name):
            out = name
        else:
            missing = "(missing %s)" % os.path.basename(image_name)
            out = (name + " " + output.term_support.warn_header_str(missing))
        LOG.debug(out)


class VirtTestLoader(loader.TestLoader):

    name = 'vt'

    def __init__(self, args, extra_params):
        super(VirtTestLoader, self).__init__(args, extra_params)
        self._fill_optional_args()

    def _fill_optional_args(self):
        def add_if_not_exist(arg, value):
            if not hasattr(self.args, arg):
                setattr(self.args, arg, value)
        add_if_not_exist('vt_config', None)
        add_if_not_exist('vt_verbose', True)
        add_if_not_exist('vt_log_level', 'debug')
        add_if_not_exist('vt_console_level', 'debug')
        add_if_not_exist('vt_datadir', data_dir.get_data_dir())
        add_if_not_exist('vt_config', None)
        add_if_not_exist('vt_arch', None)
        add_if_not_exist('vt_machine_type', None)
        add_if_not_exist('vt_keep_guest_running', False)
        add_if_not_exist('vt_backup_image_before_test', True)
        add_if_not_exist('vt_restore_image_after_test', True)
        add_if_not_exist('vt_mem', 1024)
        add_if_not_exist('vt_no_filter', '')
        add_if_not_exist('vt_qemu_bin', None)
        add_if_not_exist('vt_dst_qemu_bin', None)
        add_if_not_exist('vt_nettype', 'user')
        add_if_not_exist('vt_only_type_specific', False)
        add_if_not_exist('vt_tests', '')
        add_if_not_exist('vt_connect_uri', 'qemu:///system')
        add_if_not_exist('vt_accel', 'kvm')
        add_if_not_exist('vt_monitor', 'human')
        add_if_not_exist('vt_smp', 1)
        add_if_not_exist('vt_image_type', 'qcow2')
        add_if_not_exist('vt_nic_model', 'virtio_net')
        add_if_not_exist('vt_disk_bus', 'virtio_blk')
        add_if_not_exist('vt_vhost', 'off')
        add_if_not_exist('vt_malloc_perturb', 'yes')
        add_if_not_exist('vt_qemu_sandbox', 'on')
        add_if_not_exist('vt_tests', '')
        add_if_not_exist('show_job_log', False)
        add_if_not_exist('test_lister', True)

    def _get_parser(self):
        bootstrap.create_guest_os_cfg(self.args.vt_type)
        bootstrap.create_subtests_cfg(self.args.vt_type)
        options_processor = VirtTestOptionsProcess(self.args)
        return options_processor.get_parser()

    def get_extra_listing(self):
        if self.args.vt_list_guests:
            guest_listing(self.args)
            sys.exit(0)

    @staticmethod
    def get_type_label_mapping():
        """
        Get label mapping for display in test listing.

        :return: Dict {TestClass: 'TEST_LABEL_STRING'}
        """
        return {VirtTest: 'VT'}

    @staticmethod
    def get_decorator_mapping():
        """
        Get label mapping for display in test listing.

        :return: Dict {TestClass: decorator function}
        """
        term_support = output.TermSupport()
        return {VirtTest: term_support.healthy_str}

    def discover(self, url, which_tests=loader.DEFAULT):
        try:
            cartesian_parser = self._get_parser()
        except Exception, details:
            raise EnvironmentError(details)
        if url is not None:
            try:
                cartesian_parser.only_filter(url)
            # If we have a LexerError, this means
            # the url passed is invalid in the cartesian
            # config parser, hence it should be ignored.
            # just return an empty params list and let
            # the other test plugins to handle the URL.
            except cartesian_config.LexerError:
                return []
        elif which_tests is loader.DEFAULT and not self.args.vt_config:
            # By default don't run anythinig unless vt_config provided
            return []
        # Create test_suite
        test_suite = []
        for params in (_ for _ in cartesian_parser.get_dicts()):
            # We want avocado to inject params coming from its multiplexer into
            # the test params. This will allow users to access avocado params
            # from inside virt tests. This feature would only work if the virt
            # test in question is executed from inside avocado.
            if "subtests.cfg" in params.get("_short_name_map_file"):
                test_name = params.get("_short_name_map_file")["subtests.cfg"]
            if self.args.vt_type == 'spice':
                short_name_map_file = params.get("_short_name_map_file")
                if "tests-variants.cfg" in short_name_map_file:
                    test_name = short_name_map_file["tests-variants.cfg"]

            params['id'] = test_name
            test_parameters = {'name': test_name,
                               'vt_params': params}
            test_suite.append((VirtTest, test_parameters))
        return test_suite
