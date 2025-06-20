from abc import ABC, abstractmethod


class _VirtImage(ABC):
    """
    The volume, which has a storage resource(container), is
    defined by the cartesian params beginning with 'image_'. One or
    more lower-level images can represent a upper-level image.
    """

    _VIRT_IMAGE_FORMAT = None

    def __init__(self, config):
        self._config = config
        self._backup_volumes = dict()

    @classmethod
    def get_virt_image_format(cls):
        return cls._VIRT_IMAGE_FORMAT

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        return {
            "meta": {
                "name": image_name,
            },
            "spec": {
                "format": cls.get_virt_image_format(),
                "volume": {},
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
        return self.virt_image_spec["volume"]["meta"]["uuid"]

    @property
    def virt_image_access_nodes(self):
        volume_config = self.virt_image_spec["volume"]
        bindings = volume_config["meta"]["bindings"]
        return list(bindings.keys())

    @property
    def virt_image_name(self):
        return self.virt_image_meta["name"]

    @property
    def virt_image_config(self):
        return self._config

    @property
    def virt_image_spec(self):
        return self.virt_image_config["spec"]

    @property
    def virt_image_meta(self):
        return self.virt_image_config["meta"]

    @property
    @abstractmethod
    def keep(self):
        raise NotImplementedError

    @abstractmethod
    def create_object(self):
        raise NotImplementedError

    @abstractmethod
    def destroy_object(self):
        raise NotImplementedError

    @abstractmethod
    def info(self):
        raise NotImplementedError

    @abstractmethod
    def allocate_volume(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def release_volume(self, arguments):
        raise NotImplementedError

    @property
    def volume_allocated(self):
        volume_config = self.virt_image_spec["volume"]
        return volume_config["meta"]["allocated"]
