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

import argparse
import copy
import logging
import os

from avocado.core import loader
from avocado.core import output

from virttest import cartesian_config
from virttest import data_dir
from virttest import standalone_test
from virttest import storage
from virttest.compat import get_opt, set_opt

from .options import VirtTestOptionsProcess
from .test import VirtTest


LOG = logging.getLogger("avocado.app")


def guest_listing(options):
    """
    List available guest os and info about image availability
    """
    if get_opt(options, 'vt_type') == 'lvsb':
        raise ValueError("No guest types available for lvsb testing")
    LOG.debug("Using %s for guest images\n",
              os.path.join(data_dir.get_data_dir(), 'images'))
    LOG.info("Available guests in config:")
    guest_name_parser = standalone_test.get_guest_name_parser(options)
    for params in guest_name_parser.get_dicts():
        base_dir = params.get("images_base_dir", data_dir.get_data_dir())
        image_name = storage.get_image_filename(params, base_dir)
        machine_type = get_opt(options, 'vt_machine_type')
        name = params['name'].replace('.%s' % machine_type, '')
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
    guest_os = get_opt(options, 'vt_guest_os')
    if guest_os is not None:
        extra = " for guest os \"%s\"" % guest_os
    else:
        extra = ""
    LOG.info("Available arch profiles%s", extra)
    guest_name_parser = standalone_test.get_guest_name_parser(options)
    machine_type = get_opt(options, 'vt_machine_type')
    for params in guest_name_parser.get_dicts():
        LOG.debug(params['name'].replace('.%s' % machine_type, ''))
    LOG.debug("")


class NotAvocadoVTTest(object):

    """
    Not an Avocado-vt test (for reporting purposes)
    """


class VirtTestLoader(loader.TestLoader):

    """
    Avocado loader plugin to load avocado-vt tests
    """

    name = 'vt'

    def __init__(self, args, extra_params):
        """
        Following extra_params are supported:
         * avocado_vt_extra_params: Will override the "vt_extra_params"
           of this plugins "self.args" (extends the --vt-extra-params)
        """
        vt_extra_params = extra_params.pop("avocado_vt_extra_params", None)
        # Compatibility with nrunner Avocado
        if isinstance(args, dict):
            args = argparse.Namespace(**args)
        super(VirtTestLoader, self).__init__(args, extra_params)
        # Avocado has renamed "args" to "config" in 84ae9a5d61, lets
        # keep making the old name available for compatibility with
        # new and old releases
        if hasattr(self, 'config'):
            self.args = self.config
        self._fill_optional_args()
        if vt_extra_params:
            # We don't want to override the original args
            self.args = copy.deepcopy(self.args)
            extra = get_opt(self.args, 'vt_extra_params')
            if extra is not None:
                extra += vt_extra_params
            else:
                extra = vt_extra_params
            set_opt(self.args, 'vt_extra_params', extra)

    def _fill_optional_args(self):
        def _add_if_not_exist(arg, value):
            if not get_opt(self.args, arg):
                set_opt(self.args, arg, value)
        _add_if_not_exist('vt_config', None)
        _add_if_not_exist('vt_verbose', True)
        _add_if_not_exist('vt_log_level', 'debug')
        _add_if_not_exist('vt_console_level', 'debug')
        _add_if_not_exist('vt_datadir', data_dir.get_data_dir())
        _add_if_not_exist('vt_tmp_dir', '')
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
        if get_opt(self.args, 'vt_list_guests'):
            args = copy.copy(self.args)
            set_opt(args, 'vt_config', None)
            set_opt(args, 'vt_guest_os', None)
            guest_listing(args)
        if get_opt(self.args, 'vt_list_archs'):
            args = copy.copy(self.args)
            set_opt(args, 'vt_machine_type', None)
            set_opt(args, 'vt_arch', None)
            arch_listing(args)

    @staticmethod
    def get_type_label_mapping():
        """
        Get label mapping for display in test listing.

        :return: Dict {TestClass: 'TEST_LABEL_STRING'}
        """
        return {VirtTest: 'VT', NotAvocadoVTTest: "!VT"}

    @staticmethod
    def get_decorator_mapping():
        """
        Get label mapping for display in test listing.

        :return: Dict {TestClass: decorator function}
        """
        term_support = output.TermSupport()
        return {VirtTest: term_support.healthy_str,
                NotAvocadoVTTest: term_support.fail_header_str}

    @staticmethod
    def _report_bad_discovery(name, reason, which_tests):
        if which_tests is loader.DiscoverMode.ALL:
            return [(NotAvocadoVTTest, {"name": "%s: %s" % (name, reason)})]
        else:
            return []

    def discover(self, url, which_tests=loader.DiscoverMode.DEFAULT):
        try:
            cartesian_parser = self._get_parser()
        except Exception as details:
            return self._report_bad_discovery(url, details, which_tests)
        if url is not None:
            try:
                cartesian_parser.only_filter(url)
            # If we have a LexerError, this means
            # the url passed is invalid in the cartesian
            # config parser, hence it should be ignored.
            # just return an empty params list and let
            # the other test plugins to handle the URL.
            except cartesian_config.ParserError as details:
                return self._report_bad_discovery(url, details, which_tests)
        elif (which_tests is loader.DiscoverMode.DEFAULT and
              not get_opt(self.args, 'vt_config')):
            # By default don't run anythinig unless vt_config provided
            return []
        # Create test_suite
        test_suite = []
        for params in (_ for _ in cartesian_parser.get_dicts()):
            # Evaluate the proper avocado-vt test name
            test_name = None
            if get_opt(self.args, 'vt_config'):
                test_name = params.get("shortname")
            elif get_opt(self.args, 'vt_type') == "spice":
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
        if which_tests is loader.DiscoverMode.ALL and not test_suite:
            return self._report_bad_discovery(url, "No matching tests",
                                              which_tests)
        return test_suite
