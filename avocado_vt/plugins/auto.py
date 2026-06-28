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
Auto plugin as avocado run command switch.

SUMMARY
------------------------------------------------------


INTERFACE
------------------------------------------------------

"""

import os
import argparse

from avocado.core.settings import settings
from avocado.core.output import LOG_UI, LOG_JOB as log
from avocado.core.plugin_interfaces import CLI

from .. import cmd_parser


class Auto(CLI):
    """Class for the auto plugin."""

    name = "auto"
    description = (
        "Autotesting using restriction-generated graph of setup state dependencies."
    )

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """
        Add the subparser for the run action.

        :param parser: Main test runner parser.
        """
        run_subcommand_parser = parser.subcommands.choices.get("run", None)
        list_subcommand_parser = parser.subcommands.choices.get("list", None)
        msg = "test execution using restriction-generated graph of reusable setup state dependencies"

        if run_subcommand_parser:
            cmd_parser = run_subcommand_parser.add_argument_group(msg)
            settings.register_option(
                section="run",
                key="auto",
                key_type=bool,
                default=False,
                help_msg="Run in auto mode.",
                parser=cmd_parser,
                long_arg="--auto",
            )

        if list_subcommand_parser:
            cmd_parser = list_subcommand_parser.add_argument_group(msg)
            settings.register_option(
                section="list",
                key="auto",
                key_type=bool,
                default=False,
                help_msg="List in auto mode.",
                parser=cmd_parser,
                long_arg="--auto",
            )

    def run(self, config: dict[str, str]) -> None:
        """
        Run the auto plugin.

        Take care of command line overwriting, parameter preparation,
        setup and cleanup chains, and paths/utilities for all host controls.
        """
        if not config["run.auto"] and not config["list.auto"]:
            return

        if config.get("resolver.references"):
            refs = config["resolver.references"]
            # graph generated tests are not 1-to-1 mapped to test references which is the
            # original invocation notion but N-to-1 and generated from just one test reference
            assert (
                len(refs) == 1
            ), "Cartesian graph run supports maximally one test reference"
            # test references (here called test restrictions) are mixed with run (overwrite) parameters
            config["params"] = refs[0].split()
        elif not config.get("params"):
            config["params"] = []
        cmd_parser.params_from_cmd(config)

        log.debug(f"Setting test runner to 'traverser'")
        config["run.suite_runner"] = "traverser"
