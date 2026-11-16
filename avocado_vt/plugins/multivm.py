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
# Copyright 2013-2026 Intranet AG and contributors
# Author: Plamen Dimitrov <plamen.dimitrov@intra2net.com>

"""
Multi-VM Cartesian test parameters preparation via command switches.

SUMMARY
------------------------------------------------------


INTERFACE
------------------------------------------------------

"""

import argparse

from avocado.core.output import LOG_JOB as log
from avocado.core.plugin_interfaces import CLI
from avocado.core.settings import settings

from virttest import cmd_parser


class MultiVM(CLI):
    """Prepare multi-VM Cartesian test parameters."""

    name = "multivm"
    description = "Multi-VM Cartesian parsing with optional state handling."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """
        Add the subparser for the run action.

        :param parser: Main test runner parser.
        """
        run_subcommand_parser = parser.subcommands.choices.get("run", None)
        list_subcommand_parser = parser.subcommands.choices.get("list", None)
        msg = "Virt-Test multi-VM Cartesian parameters parsing"

        if run_subcommand_parser:
            option_parser = run_subcommand_parser.add_argument_group(msg)
            settings.register_option(
                section="run",
                key="vt_multi_vm",
                key_type=bool,
                default=False,
                help_msg="Expand VT tests with all selected VM and network objects.",
                parser=option_parser,
                long_arg="--vt-multi-vm",
            )
            settings.register_option(
                section="run",
                key="vt_states",
                key_type=bool,
                default=False,
                help_msg="Enable VM, image, and network state lifecycle hooks.",
                parser=option_parser,
                long_arg="--vt-states",
            )
        if list_subcommand_parser:
            option_parser = list_subcommand_parser.add_argument_group(msg)
            settings.register_option(
                section="list",
                key="vt_multi_vm",
                key_type=bool,
                default=False,
                help_msg="Expand VT tests with all selected VM and network objects.",
                parser=option_parser,
                long_arg="--vt-multi-vm",
            )

    def run(self, config: dict[str, str]) -> None:
        """
        Prepare Cartesian parameters for multi-VM test discovery.

        Keep graph construction and scheduling independent from parameter
        preparation so either the nrunner or traverser suite runner can consume
        the result.
        """
        if not config.get("run.vt_multi_vm") and not config.get("list.vt_multi_vm"):
            return

        reference = None
        if config.get("resolver.references"):
            refs = config["resolver.references"]
            # graph generated tests are not 1-to-1 mapped to test references which is the
            # original invocation notion but N-to-1 and generated from just one test reference
            assert (
                len(refs) == 1
            ), "Cartesian graph run supports maximally one test reference"
            reference = refs[0]

        use_states = bool(config.get("run.vt_states", False))
        extra_params = list(config.get("vt.extra_params") or [])
        extra_params.extend(
            (
                f"vm_type={config.get('vt.type') or 'qemu'}",
                f"use_states={'yes' if use_states else 'no'}",
            )
        )
        if use_states:
            config["vt.common.tmp_dir"] = "/tmp"
            extra_params.extend(("keep_vms_after_test=yes", "job_env_cleanup=no"))
        cmd_parser.params_from_cmd(
            config,
            reference=reference,
            extra_params=extra_params,
        )
        if config.get("run.vt_multi_vm"):
            cmd_parser.configure_runtime(config, use_states=use_states)
        log.debug(
            "Prepared multi-VM parameters for the %s suite runner",
            config.get("run.suite_runner", "nrunner"),
        )
