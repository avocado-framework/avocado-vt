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
from virttest import cmd_parser
from virttest import params_parser as param
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
        if reference is not None:
            assert reference.split() == self.config["params"]

        params, restriction = self.config["param_dict"], self.config["tests_str"]
        return ReferenceResolution(
            reference,
            ReferenceResolutionResult.SUCCESS,
            TestGraph.parse_flat_nodes(restriction, params),
        )
