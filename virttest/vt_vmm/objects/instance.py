from . import instance_exception
from .instance_spec import Spec
from .instance_state import States


class Instance(object):
    def __init__(self, uuid, name, kind, spec):
        self._uuid = uuid
        self._name = name
        self._kind = kind  # virt driver type. e.g: libvirt, qemu
        self._spec = spec
        self._state = None
        self.node = None  # binding node

    @property
    def uuid(self):
        return self._uuid

    @property
    def name(self):
        return self._name

    @property
    def kind(self):
        return self._kind

    @property
    def spec(self):
        return self._spec

    def update(self, updated_spec):
        if isinstance(updated_spec, Spec):
            self._spec.update(updated_spec)
        else:
            raise instance_exception.InstanceError("No support this type of spec.")

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        if isinstance(state, States):
            self._state = state
        else:
            raise ValueError
