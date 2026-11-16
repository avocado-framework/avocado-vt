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
Specialized test loader for the plugin.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

import logging

from avocado.core.plugin_interfaces import Resolver
from avocado.core.resolver import ReferenceResolution, ReferenceResolutionResult

from virttest.cartgraph import TestGraph

log = logging.getLogger("avocado.job." + __name__)


class TestLoader(Resolver):
    """Test loader for Cartesian graph parsing."""

    name = "cartesian_loader"
    description = "Loads tests from initial Cartesian product"

    def __init__(
        self, config: dict[str, str] = None, extra_params: dict[str, str] = None
    ) -> None:
        """
        Construct the Cartesian loader.

        :param config: command line arguments
        :param extra_params: extra configuration parameters
        """
        super().__init__(config=config)
        extra_params = {} if not extra_params else extra_params
        self.logdir = extra_params.pop("logdir", ".")

    def resolve(self, reference: str | None) -> list[tuple[type, dict[str, str]]]:
        """
        Discover (possible) tests from test references.

        :param reference: tests reference used to produce tests
        :returns: test factories as tuples of the test class and its parameters
        """
        params, restriction = self.config["param_dict"], self.config["tests_str"]
        multi_vm = self.config.get("run.vt_multi_vm") or self.config.get(
            "list.vt_multi_vm"
        )
        suite_runner = self.config.get("run.suite_runner", "nrunner")

        if multi_vm and suite_runner != "traverser":
            flat_net = TestGraph.parse_net_from_object_restrs(
                "net1", self.config.get("vm_strs", {})
            )
            runnables = TestGraph().parse_composite_nodes(
                restriction, flat_net, params=params
            )
        else:
            runnables = TestGraph.parse_flat_nodes(restriction, params)
        log.info(
            "Resolved %d test nodes as runnable(s)",
            len(runnables),
        )

        result = ReferenceResolutionResult.NOTFOUND
        if runnables:
            result = ReferenceResolutionResult.SUCCESS
        return ReferenceResolution(reference, result, runnables)
