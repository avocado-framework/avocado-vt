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
# Copyright: Red Hat Inc. 2021
# Authors: Cleber Rosa <crosa@redhat.com>
#          Lucas Meneghel Rodrigues <lmr@redhat.com>

"""
Avocado VT plugin
"""

from virttest.compat import get_opt
from .options import VirtTestOptionsProcess


class DiscoveryMixIn:

    def _get_parser(self):
        options_processor = VirtTestOptionsProcess(self.config)
        return options_processor.get_parser()

    def _save_parser_cartesian_config(self, parser):
        path = get_opt(self.config, 'vt.save_config')
        if path is None:
            return
        with open(path, 'w') as cartesian_config:
            cartesian_config.write("include %s\n" % parser.filename)
            for statement in (parser.only_filters + parser.no_filters +
                              parser.assignments):
                cartesian_config.write("%s\n" % statement)

    def convert_parameters(self, params):
        """
        Evaluates the proper avocado-vt test name and params.

        :param params: cartesian config parameters
        :type params: dict
        :return: dict with test name and vt parameters
        """
        test_name = params.get("_short_name_map_file")["subtests.cfg"]
        if (get_opt(self.config, 'vt.config')
                and get_opt(self.config, 'vt.short_names_when_config')):
            test_name = params.get("shortname")
        elif get_opt(self.config, 'vt.type') == "spice":
            short_name_map_file = params.get("_short_name_map_file")
            if "tests-variants.cfg" in short_name_map_file:
                test_name = short_name_map_file.get("tests-variants.cfg",
                                                    test_name)
        # We want avocado to inject params coming from its multiplexer into
        # the test params. This will allow users to access avocado params
        # from inside virt tests. This feature would only work if the virt
        # test in question is executed from inside avocado.
        params['id'] = test_name
        test_parameters = {'name': test_name,
                           'vt_params': params}
        return test_parameters
