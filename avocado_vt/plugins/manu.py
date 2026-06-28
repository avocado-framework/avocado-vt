# Copyright 2013-2020 Intranet AG and contributors
#
# avocado-i2n is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# avocado-i2n is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with avocado-i2n.  If not, see <http://www.gnu.org/licenses/>.

"""
Manu plugin as a separate avocado command.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

import os
import argparse
import traceback

from avocado.core.settings import settings
from avocado.core.output import LOG_UI, LOG_JOB as log
from avocado.core.plugin_interfaces import CLICmd
from virttest.utils_params import Params

from .. import cmd_parser
from .. import params_parser as param
from .. import intertest_setup as intertest


class Manu(CLICmd):
    """Class for the manu plugin."""

    name = "manu"
    description = (
        "Tools using setup chains of manual steps with Cartesian graph manipulation."
    )

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """
        Add the parser for the manual action.

        :param parser: Main test runner parser.
        """
        parser = super(Manu, self).configure(parser)

        settings.register_option(
            section="i2n.manu",
            key="params",
            key_type=list,
            default=[],
            metavar="PARAM=VALUE",
            help_msg="List of 'key=value' pairs passed to a Cartesian parser.",
            parser=parser,
            nargs="*",
            positional_arg=True,
        )

    def run(self, config: Params) -> int:
        """
        Run the manu plugin.

        Take care of command line overwriting, parameter preparation for all host controls,
        setup and cleanup chains, and paths/utilities for all host controls.
        """
        log.info("Manual setup chain started.")
        # set English environment (command output might be localized, need to be safe)
        os.environ["LANG"] = "en_US.UTF-8"

        config["run.suite_runner"] = "traverser"
        config["params"] = config["i2n.manu.params"]
        try:
            cmd_parser.params_from_cmd(config)
        except (ValueError, param.EmptyCartesianProduct) as error:
            LOG_UI.error(error)
            return 1
        intertest.load_addons_tools()
        run_params = config["vms_params"]

        # prepare a setup step or a chain of such
        setup_chain = run_params.objects("setup")
        retcode = 0
        for i, setup_step in enumerate(setup_chain):
            run_params["count"] = i
            setup_func = getattr(intertest, setup_step)
            try:
                # TODO: drop the consideration of None in the future if the
                # functions from the intertest module do not return this value.
                if setup_func(config, "0m%s" % i) not in [None, 0]:
                    # return 1 if at least one of the steps fails
                    retcode = 1
            except Exception as error:
                tb_list = traceback.format_exception(error)
                for item in tb_list:
                    log.error(item.rstrip())
                LOG_UI.error(error)
                LOG_UI.error("Use 'export AVOCADO_LOG_EARLY=1' for further details.")
                retcode = 1

        log.info("Manual setup chain finished.")
        return retcode
