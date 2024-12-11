import collections
import copy
import uuid
from abc import ABC, abstractmethod


class _VirImage(ABC):
    """
    The virtual image, in the context of a VM, is mapping to a VM's disk.
    It could be composed of one or more images, e.g. A qemu virtual image
    could have a image chain:
      base ---> sn
    in which "sn" is the top image while "base" is its backing image.
    """

    # Supported image types: qemu
    _IMAGE_TYPE = None
    _EDITABLE_OPTIONS = {"meta": ["name", "owner"]}

    def __init__(self, image_config):
        self._config = image_config
        self.image_meta["uuid"] = uuid.uuid4().hex
        self._images = collections.OrderedDict()
        self._handlers = dict()

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
        return {
            "meta": {
                "uuid": None,
                "name": image_name,
                "type": cls.get_image_type(),
                "owner": None,
                "topology": None,
            },
            "spec": {
                "images": {},
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

    def get_image_info(self, verbose=False):
        config = copy.deepcopy(self.image_config)

        if verbose:
            images = config["spec"]["images"]
            for image in self.images.values():
                images[image.image_name] = image.get_info(verbose=True)

        return config

    @abstractmethod
    def backup(self):
        raise NotImplementedError

    @abstractmethod
    def restore(self):
        raise NotImplementedError

    @abstractmethod
    def clone(self):
        raise NotImplementedError

    def config(self, arguments):
        # FIXME:
        for key, options in self._EDITABLE_OPTIONS.items():
            for opt in options:
                if opt in arguemnts:
                    self._config[key][opt] = arguments[opt]

    def get_image_handler(self, cmd):
        return self._handlers.get(cmd)
