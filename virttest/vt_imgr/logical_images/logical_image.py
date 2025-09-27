import copy
import uuid
from abc import ABC, abstractmethod


class LogicalImage(ABC):
    """
    Abstract base class for logical images in the avocado-vt image management system.

    A logical image represents a complete disk image structure that maps to a VM's
    virtual disk. Logical images can have complex hierarchical topologies composed
    of multiple lower-level images, e.g. the backing chains for the qemu logical
    image, enabling advanced features like snapshots semantics.

    The Qemu Image Hierarchy Example:
        base_image ---> snapshot_1 ---> snapshot_2 (top-level)

    In this chain, 'snapshot_2' is the logical image name(what the VM sees), while
    'base_image' and 'snapshot_1' are its backing images providing the foundation
    data layers. Each layer can be stored on different storage pools and accessed
    through the unified resource management system.
    """

    # The supported image types: qemu
    IMAGE_TYPE = None

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

    def is_owned_by(self, owner):
        return owner == self.image_meta["owner"]

    @classmethod
    def _define_config_legacy(cls, image_name, params):
        """
        Define the logical image configuration in the old way
        """
        return {
            "meta": {
                "uuid": None,
                "name": image_name,
                "type": cls.IMAGE_TYPE,
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
        Define the logical image configuration by its cartesian params
        """
        return cls._define_config_legacy(image_name, params)

    @abstractmethod
    def create_object(self):
        raise NotImplementedError

    @abstractmethod
    def destroy_object(self):
        raise NotImplementedError

    @abstractmethod
    def create(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def destroy(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def clone(self):
        raise NotImplementedError

    @abstractmethod
    def backup(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def restore(self, arguments):
        raise NotImplementedError

    def get_info(self, request=None, verbose=False):
        config = copy.deepcopy(self.image_config)

        if verbose:
            images = config["spec"]["images"]
            for image in self.images.values():
                images[image.image_name] = image.get_info(verbose=True)

        if request is not None:
            item = None
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(request)
            else:
                config = {item: config}
        return config

    def get_image_handler(self, cmd):
        return self._handlers.get(cmd)
