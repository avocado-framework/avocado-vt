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

import copy
import logging
import os

from avocado.core import loader
from avocado.core import output

from virttest import cartesian_config
from virttest import data_dir
from virttest import standalone_test
from virttest import storage

from .options import VirtTestOptionsProcess
from .test import VirtTest


LOG = logging.getLogger("avocado.app")


def guest_listing(options):
    """
    List available guest os and info about image availability
    """
    if options.vt_type == 'lvsb':
        raise ValueError("No guest types available for lvsb testing")
    LOG.debug("Using %s for guest images\n",
              os.path.join(data_dir.get_data_dir(), 'images'))
    LOG.info("Available guests in config:")
    guest_name_parser = standalone_test.get_guest_name_parser(options)
    for params in guest_name_parser.get_dicts():
        base_dir = params.get("images_base_dir", data_dir.get_data_dir())
        image_name = storage.get_image_filename(params, base_dir)
        name = params['name']
        if os.path.isfile(image_name):
            out = name
        else:
            missing = "(missing %s)" % os.path.basename(image_name)
            out = (name + " " + output.TERM_SUPPORT.warn_header_str(missing))
        LOG.debug(out)
    LOG.debug("")


def arch_listing(options):
    """
    List available machine/archs for given guest os
    """
    if options.vt_guest_os:
        extra = " for guest os \"%s\"" % options.vt_guest_os
    else:
        extra = ""
    LOG.info("Available machine_type/arch profiles%s", extra)
    guest_name_parser = standalone_test.get_guest_name_parser(options)
    for params in guest_name_parser.get_dicts():
        LOG.debug(params["name"])
    LOG.debug("")


class VirtTestLoader(loader.TestLoader):

    """
    Avocado loader plugin to load avocado-vt tests
    """

    name = 'vt'

    def __init__(self, args, extra_params):
        super(VirtTestLoader, self).__init__(args, extra_params)
        self._fill_optional_args()

    def _fill_optional_args(self):
        def _add_if_not_exist(arg, value):
            if not hasattr(self.args, arg):
                setattr(self.args, arg, value)
        _add_if_not_exist('vt_config', None)
        _add_if_not_exist('vt_verbose', True)
        _add_if_not_exist('vt_log_level', 'debug')
        _add_if_not_exist('vt_console_level', 'debug')
        _add_if_not_exist('vt_datadir', data_dir.get_data_dir())
        _add_if_not_exist('vt_config', None)
        _add_if_not_exist('vt_arch', None)
        _add_if_not_exist('vt_machine_type', None)
        _add_if_not_exist('vt_keep_guest_running', False)
        _add_if_not_exist('vt_backup_image_before_test', True)
        _add_if_not_exist('vt_restore_image_after_test', True)
        _add_if_not_exist('vt_mem', 1024)
        _add_if_not_exist('vt_no_filter', '')
        _add_if_not_exist('vt_qemu_bin', None)
        _add_if_not_exist('vt_dst_qemu_bin', None)
        _add_if_not_exist('vt_nettype', 'user')
        _add_if_not_exist('vt_only_type_specific', False)
        _add_if_not_exist('vt_tests', '')
        _add_if_not_exist('vt_connect_uri', 'qemu:///system')
        _add_if_not_exist('vt_accel', 'kvm')
        _add_if_not_exist('vt_monitor', 'human')
        _add_if_not_exist('vt_smp', 1)
        _add_if_not_exist('vt_image_type', 'qcow2')
        _add_if_not_exist('vt_nic_model', 'virtio_net')
        _add_if_not_exist('vt_disk_bus', 'virtio_blk')
        _add_if_not_exist('vt_vhost', 'off')
        _add_if_not_exist('vt_malloc_perturb', 'yes')
        _add_if_not_exist('vt_qemu_sandbox', 'on')
        _add_if_not_exist('vt_tests', '')
        _add_if_not_exist('show_job_log', False)
        _add_if_not_exist('test_lister', True)

    def _get_parser(self):
        options_processor = VirtTestOptionsProcess(self.args)
        return options_processor.get_parser()

    def get_extra_listing(self):
        if self.args.vt_list_guests:
            args = copy.copy(self.args)
            args.vt_config = None
            args.vt_guest_os = None
            guest_listing(args)
        if self.args.vt_list_archs:
            args = copy.copy(self.args)
            args.vt_machine_type = None
            args.vt_arch = None
            arch_listing(args)

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
            except cartesian_config.ParserError:
                return []
        elif which_tests is loader.DEFAULT and not self.args.vt_config:
            # By default don't run anythinig unless vt_config provided
            return []
        # Create test_suite
        test_suite = []
        for params in (_ for _ in cartesian_parser.get_dicts()):
            # Evaluate the proper avocado-vt test name
            test_name = None
            if self.args.vt_config:
                test_name = params.get("shortname")
            elif self.args.vt_type == "spice":
                short_name_map_file = params.get("_short_name_map_file")
                if "tests-variants.cfg" in short_name_map_file:
                    test_name = short_name_map_file["tests-variants.cfg"]
            if test_name is None:
                test_name = params.get("_short_name_map_file")["subtests.cfg"]
            # We want avocado to inject params coming from its multiplexer into
            # the test params. This will allow users to access avocado params
            # from inside virt tests. This feature would only work if the virt
            # test in question is executed from inside avocado.
            params['id'] = test_name
            test_parameters = {'name': test_name,
                               'vt_params': params}
            test_suite.append((VirtTest, test_parameters))
        return test_suite
