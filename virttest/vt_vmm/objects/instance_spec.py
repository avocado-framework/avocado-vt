import json
from abc import ABCMeta, abstractmethod

import six


@six.add_metaclass(ABCMeta)
class Spec(object):
    def __init__(self, name, kind, vt_params):
        self._kind = kind
        self._name = name
        self._params = vt_params
        self._spec = self._parse_params()

    @abstractmethod
    def _parse_params(self):
        """
        Parse the parameters to the spec.
        """
        raise NotImplementedError

    def update(self, spec):
        """Re-assign the value of spec directly."""
        self._spec = spec

    def to_json(self):
        # return json.dumps(self._spec, indent=4, separators=(",", ": "))
        return json.dumps(self._spec)

    def __repr__(self):
        return json.dumps(self._spec, indent=4, separators=(",", ": "))
