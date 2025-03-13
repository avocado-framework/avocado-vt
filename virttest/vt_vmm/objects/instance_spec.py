import json
from abc import ABCMeta, abstractmethod

import six

from virttest.vt_cluster import cluster


@six.add_metaclass(ABCMeta)
class Spec(object):
    def __init__(self, name, kind, vt_params, node):
        self._kind = kind
        self._name = name
        self._params = vt_params
        self._node = cluster.get_node_by_tag(node)
        # self._spec = self._parse_params()

    @abstractmethod
    def _parse_params(self):
        """
        Parse the parameters to the spec.
        """
        raise NotImplementedError

    # TODO:
    def update(self, spec):
        """Re-assign the value of spec directly."""
        pass

    def to_json(self):
        # return json.dumps(self._spec, indent=4, separators=(",", ": "))
        return json.dumps(self._parse_params())

    def __repr__(self):
        return json.dumps(self._parse_params(), indent=4, separators=(",", ": "))
