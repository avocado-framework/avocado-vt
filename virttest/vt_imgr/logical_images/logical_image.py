import copy
import uuid
from abc import ABC, abstractmethod


class _LogicalImage(ABC):
    """
    The top-level image, in the context of a VM, is mapping to a VM's disk.
    It could be composed of one or more lower-level images, e.g. A qemu
    virtual image could have a lower-level image chain:
      base ---> sn
    in which "sn" is the top image while "base" is its backing image.
    """

    # Supported image types: qemu
    _IMAGE_TYPE = None

    def __init__(self, image_config):
        self._config = image_config
        self.image_meta["uuid"] = uuid.uuid4().hex
        self._images = dict()
        self._handlers = {
            "create": self.create,
            "destroy": self.destroy,
            "backup": self.backup,
            "restore": self.restore,
        }

    @classmethod
    def get_image_type(cls):
        return cls._IMAGE_TYPE

    @property
    def images(self):
        return self._images

    @property
    def image_config(self):
        return self._config

    @property
    def image_meta(self):
        return self._config["meta"]

    @property
    def image_spec(self):
        return self._config["spec"]

    @property
    def image_id(self):
        return self.image_meta["uuid"]

    @property
    def image_name(self):
        return self.image_meta["name"]

    @image_name.setter
    def image_name(self, name):
        self.image_meta["name"] = name

    def is_owned_by(self, vm_name):
        return vm_name == self.image_meta["owner"]

    @classmethod
    def _define_config_legacy(cls, image_name, params):
        """
        Define the virt image configuration in the old way
        """
        return {
            "meta": {
                "uuid": None,
                "name": image_name,
                "type": cls.get_image_type(),
                "owner": params.object_params(image_name).get("image_owner"),
                "topology": {"type": None, "value": None},
            },
            "spec": {
                "images": dict(),
            },
        }

    @classmethod
    def define_config(cls, image_name, params):
        """
        Define the virt image configuration by its cartesian params
        """
        return cls._define_config_legacy(image_name, params)

    @abstractmethod
    def create_object(self):
        raise NotImplementedError

    @abstractmethod
    def destroy_object(self):
        raise NotImplementedError

    @abstractmethod
    def create(self):
        raise NotImplementedError

    @abstractmethod
    def destroy(self):
        raise NotImplementedError

    @abstractmethod
    def clone(self):
        raise NotImplementedError

    @abstractmethod
    def backup(self):
        raise NotImplementedError

    @abstractmethod
    def restore(self):
        raise NotImplementedError

    def get_info(self, verbose=False):
        config = copy.deepcopy(self.image_config)

        if verbose:
            images = config["spec"]["images"]
            for image in self.images.values():
                images[image.image_name] = image.get_info(verbose=True)

        return config

    def get_image_handler(self, cmd):
        return self._handlers.get(cmd)
