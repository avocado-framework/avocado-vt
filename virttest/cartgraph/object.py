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
Utility for the main test suite substructures like test objects.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

from __future__ import annotations

import logging

from virttest.utils_params import Params

from .. import params_parser as param


class TestObject(object):
    """A wrapper for a test object used in one or more test nodes."""

    @property
    def params(self) -> Params:
        """Parameters (cache) property."""
        if self._params_cache is None:
            self.regenerate_params()
        return self._params_cache

    @property
    def component_form(self) -> str:
        """Component form of the test object name."""
        return self.params["name"].replace(self.key + ".", "")

    @property
    def long_suffix(self) -> str:
        """Sufficiently unique suffix to identify a variantless test object."""
        return self._long_suffix

    @property
    def id(self) -> str:
        """Use unique ID to identify a test object."""
        return self.long_suffix + "-" + self.params["name"]

    def __init__(self, suffix: str, recipe: param.Reparsable) -> None:
        """
        Construct a test object (vm) for any test nodes (tests).

        :param suffix: name of the test object
        :param recipe: variant configuration for the test object
        """
        self.suffix = suffix.split("_")[0]
        self._long_suffix = suffix
        self.recipe = recipe
        self._params_cache = None
        self.restrs = {}
        # TODO: Cartesian parser needs support for restrictions after join operations
        self.dict_index = 0

        # TODO: integrate these features better
        self.current_state = "unknown"

        self.composites = []
        self.components = []

        self.key = "objects"

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        shortname = self.params.get("shortname", "<unknown>")
        return f"[object] longsuffix='{self.long_suffix}', shortname='{shortname}'"

    def is_flat(self) -> bool:
        """Check if the test object is flat and does not yet have components to evaluate."""
        return len(self.components) == 0

    def is_permanent(self) -> bool:
        """
        Check if the object is permanent.

        If permanent, it can only be created manually (possibly through the use of manual setup steps).

        On states on permanent test object are treated differently than
        on states on normal test object since they are preserved through
        test runs and even host shutdowns.
        """
        return self.params.get("permanent_vm", "no") == "yes"

    def object_typed_params(self, params: Params) -> Params:
        """
        Return object and type filtered parameters using the current object type.

        :param params: whether to show generated parameter dictionaries
        """
        # TODO: we don't support recursion at the moment but this is fine
        # for the current implicit assumption of nets->vms->images
        for composite in self.composites:
            params = params.object_params(composite.suffix)
        return params.object_params(self.suffix).object_params(self.key)

    def update_restrs(self, object_restrs: dict[str, str]) -> None:
        """
        Update any restrictions with further filters.

        :param object_restrs: multi-line object restrictions to append
        """
        for suffix, restriction in object_restrs.items():
            self.restrs[suffix] = self.restrs.get(suffix, "")
            if restriction != "":
                if restriction.rstrip() not in self.restrs[suffix].splitlines():
                    self.restrs[suffix] += restriction

    def regenerate_params(self, verbose: bool = False) -> None:
        """
        Regenerate all parameters from the current reparsable recipe.

        :param verbose: whether to show generated parameter dictionaries
        """
        generic_params = self.recipe.get_params(
            dict_index=self.dict_index, show_dictionaries=verbose
        )
        self._params_cache = self.object_typed_params(generic_params)
        for key, value in list(self._params_cache.items()):
            if key.startswith("only_") or key.startswith("no_"):
                restr_type, suffix = key.split("_", maxsplit=1)
                restr_line = restr_type + " " + value + "\n" if value != "" else ""
                self.update_restrs({suffix: restr_line})
                del self._params_cache[key]


class NetObject(TestObject):
    """A Net wrapper for a test object used in one or more test nodes."""

    def component_form(self) -> str:
        """Component form of the test object name."""
        # TODO: an unexpected order of joining in the Cartesian config requires us to override base property
        return self.params["name"]

    component_form = property(fget=component_form)

    def __init__(self, name: str, recipe: param.Reparsable) -> None:
        """
        Construct a test object (vm) for any test nodes (tests).

        All arguments are inherited from the base class.
        """
        super().__init__(name, recipe)
        self.key = "nets"
        self.components = []


class VMObject(TestObject):
    """A VM wrapper for a test object used in one or more test nodes."""

    def __init__(self, name: str, recipe: param.Reparsable) -> None:
        """
        Construct a test object (vm) for any test nodes (tests).

        All arguments are inherited from the base class.
        """
        super().__init__(name, recipe)
        self.key = "vms"
        self.components = []


class ImageObject(TestObject):
    """An image wrapper for a test object used in one or more test nodes."""

    def id(self) -> str:
        """Sufficiently unique ID to identify a test object."""
        assert len(self.composites) == 1, "Image objects need a unique composite"
        return self.long_suffix + "-" + self.composites[0].params["name"]

    id = property(fget=id)

    def component_form(self) -> str:
        """Component form of the test object name."""
        return self.composites[0].component_form

    component_form = property(fget=component_form)

    def __init__(self, name: str, recipe: param.Reparsable) -> None:
        """
        Construct a test object (vm) for any test nodes (tests).

        All arguments are inherited from the base class.
        """
        super().__init__(name, recipe)
        self.key = "images"
        self.params["main_vm"] = "none"
