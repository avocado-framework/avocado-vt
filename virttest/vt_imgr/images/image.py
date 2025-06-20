import collections
import uuid
from abc import ABC, abstractmethod


class _Image(ABC):
    """
    The image, in the context of a VM, is mapping to the VM's disk.
    It can have one or more volumes, e.g. A qemu image can have a
    volume chain:
      base ---> sn
    in which "sn" is the top volume name while "base" is its backing
    volume name.
    """

    # Supported image types: qemu
    _IMAGE_TYPE = None

    def __init__(self, image_config):
        self._config = image_config
        self.image_meta["uuid"] = uuid.uuid4().hex
        self._virt_images = collections.OrderedDict()
        self._handlers = dict()

    @classmethod
    def get_image_type(cls):
        return cls._IMAGE_TYPE

    @property
    def image_id(self):
        return self.image_meta["uuid"]

    @property
    def image_config(self):
        return self._config

    @property
    def image_meta(self):
        return self.image_config["meta"]

    @property
    def image_spec(self):
        return self.image_config["spec"]

    @property
    def image_name(self):
        return self.image_meta["name"]

    @image_name.setter
    def image_name(self, name):
        self.image_meta["name"] = name

    def is_used_by(self, vm_name):
        return vm_name == self.image_meta["user"]

    @classmethod
    def _define_config_legacy(cls, image_name, params):
        return {
            "meta": {
                "uuid": None,
                "name": image_name,
                "type": cls.get_image_type(),
                "user": None,
                "topology": None,
            },
            "spec": {
                "virt-images": {},
            },
        }

    @classmethod
    def define_config(cls, image_name, params):
        """
        Define the image configuration by its cartesian params
        """
        return cls._define_config_legacy(image_name, params)

    @abstractmethod
    def create_object(self):
        raise NotImplementedError

    @abstractmethod
    def destroy_object(self):
        raise NotImplementedError

    @abstractmethod
    def get_info(self, request):
        raise NotImplementedError

    @abstractmethod
    def backup(self):
        raise NotImplementedError

    def get_image_handler(self, cmd):
        return self._handlers.get(cmd)
