import copy
import uuid
from abc import ABC, abstractmethod

from virttest.vt_resmgr import resmgr


class _Image(ABC):
    """
    The image, which has a storage resource(aka volume), is defined by the
    cartesian params beginning with 'image_', e.g. image_format
    """

    _IMAGE_FORMAT = None

    def __init__(self, config):
        self._config = config
        self.image_meta["uuid"] = uuid.uuid4().hex

    @classmethod
    def get_image_format(cls):
        return cls._IMAGE_FORMAT

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        return {
            "meta": {
                "uuid": None,
                "name": image_name,
            },
            "spec": {
                "backup": None,
                "format": cls.get_image_format(),
                "volume": None,  # Volume uuid
            },
        }

    @classmethod
    def define_config(cls, image_name, image_params):
        """
        Define the virt image configuration by its cartesian params.
        Currently use the existing image params, in future, we'll
        design a new set of params to describe a lower-level image.
        """
        return cls._define_config_legacy(image_name, image_params)

    @property
    def volume_id(self):
        return self.image_spec["volume"]

    @property
    def image_access_nodes(self):
        d = resmgr.get_resource_info(self.volume_id, "meta.bindings")
        return list(d["bindings"].keys())

    @property
    def image_id(self):
        return self.image_meta["uuid"]

    @property
    def image_name(self):
        return self.image_meta["name"]

    @property
    def image_config(self):
        return self._config

    @property
    def image_spec(self):
        return self.image_config["spec"]

    @property
    def image_meta(self):
        return self.image_config["meta"]

    @property
    @abstractmethod
    def keep(self):
        raise NotImplementedError

    @abstractmethod
    def create_object_from_self(self, image_pool_id=None):
        raise NotImplementedError

    @abstractmethod
    def create_object(self):
        raise NotImplementedError

    @abstractmethod
    def destroy_object(self):
        raise NotImplementedError

    def get_info(self, verbose=False):
        config = copy.deepcopy(self.image_config)
        if verbose:
            config["spec"]["volume"] = resmgr.get_resource_info(
                self.volume_id, verbose=True
            )

        return config

    @abstractmethod
    def create(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def destroy(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def bind_volume(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def allocate_volume(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def release_volume(self, arguments):
        raise NotImplementedError

    @property
    def volume_allocated(self):
        d = resmgr.get_resource_info(self.volume_id, "meta.allocated")
        return d["allocated"]
