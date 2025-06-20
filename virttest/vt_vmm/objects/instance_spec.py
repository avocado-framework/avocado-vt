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
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>


import json
from abc import ABCMeta, abstractmethod

import six

from virttest.vt_cluster import cluster


@six.add_metaclass(ABCMeta)
class Spec(object):  # TODO: Implement it by UserDict class
    def __init__(self, vm_name, vm_params, node):
        self._name = vm_name
        self._params = vm_params
        self._node = cluster.get_node_by_tag(node)
        self._spec = {}  # TODO: come up with a better name or class for spec

    @property
    def spec(self):
        return self._spec

    @abstractmethod
    def _parse_params(self):
        """
        Parse the parameters to the spec(self._spec).
        """
        raise NotImplementedError

    # TODO:
    def update(self, spec):
        """Re-assign the value of spec directly."""
        pass

    def to_json(self):
        return json.dumps(self.spec)

    def to_xml(self):
        raise NotImplementedError

    def __repr__(self):
        return json.dumps(self.spec, indent=4, separators=(",", ": "))

    def __eq__(self, other):
        if isinstance(other, Spec):
            return self.spec == other.spec
        return False
