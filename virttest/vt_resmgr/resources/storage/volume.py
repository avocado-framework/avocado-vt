import copy
import os

from virttest import utils_numeric, utils_misc

from ..resource import _Resource


class _Volume(_Resource):
    """
    Storage volumes are abstractions of physical partitions,
    LVM logical volumes, file-based disk images
    """

    _RESOURCE_TYPE = "volume"
    _VOLUME_TYPE = None

    @classmethod
    def get_volume_type(cls):
        return cls._VOLUME_TYPE

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        size = utils_numeric.normalize_data_size(
            resource_params.get("image_size", "20G"), order_magnitude="B"
        )

        config = super()._define_config_legacy(resource_name, resource_params)
        config["meta"].update(
            {
                "type": cls._RESOURCE_TYPE,
                "volume-type": cls.get_volume_type(),
                "raw": resource_params.get_boolean("image_raw_device"),
            }
        )
        config["spec"].update(
            {
                "size": size,
                "allocation": None,
                "uri": None,
            }
        )

        return config


class _FileVolume(_Volume):
    """For file based volumes"""

    _VOLUME_TYPE = "file"

    def __init__(self, resource_config):
        super().__init__(resource_config)
        self._handlers.update(
            {
                "resize": self.resize,
            }
        )

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        config = super()._define_config_legacy(resource_name, resource_params)

        image_name = resource_params.get("image_name", "image")
        if os.path.isabs(image_name):
            # FIXME: the image file may not come from this pool
            config["spec"]["uri"] = image_name
            config["spec"]["filename"] = os.path.basename(image_name)
        else:
            image_format = resource_params.get("image_format", "qcow2")
            config["spec"]["filename"] = "%s.%s" % (image_name, image_format)
            config["spec"]["uri"] = None

        return config

    def resize(self, arguments):
        raise NotImplementedError

    def clone(self):
        config = copy.deepcopy(self.resource_config)

        # Reset options
        filename = config["spec"]["filename"]
        postfix = utils_misc.generate_random_string(4)
        config["spec"].update(
            {
                "uri": None,
                "filename": f"{filename}.clone-{postfix}",
            }
        )
        config["meta"].update(
            {
                "allocated": False,
                "bindings": {k: None for k in self.resource_bindings},
            }
        )

        # Allocate storage without data copy
        obj = self.__class__(config)
        obj.create_object()
        obj.bind(dict())

        # Copy the file based volume by default
        args = {
            "how": "copy",
            "source": self.resource_spec["uri"],
        }
        obj.allocate(args)

        return obj


class _BlockVolume(_Volume):
    """For disk, lvm, iscsi based volumes"""

    _VOLUME_TYPE = "block"


class _NetworkVolume(_Volume):
    """For rbd, iscsi-direct based volumes"""

    _VOLUME_TYPE = "network"
