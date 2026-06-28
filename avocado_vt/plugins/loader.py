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

from .. import cmd_parser
from .. import params_parser as param
from ..cartgraph import TestGraph

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
