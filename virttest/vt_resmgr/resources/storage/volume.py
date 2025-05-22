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
    def _define_config_legacy(cls, resource_name, resource_params):
        # TODO: Image params are inherited for the volume resource, we need
        # params defined for volume resource, e.g.
        # volumes = v1 v2
        # volume_size = 1G
        # volume_type_v1 = file
        # volume_type_v2 = block
        size = utils_numeric.normalize_data_size(
            resource_params.get("image_size", "20G"), order_magnitude="B"
        )

        config = super()._define_config_legacy(resource_name, resource_params)
        config["meta"].update(
            {
                "volume-type": cls._VOLUME_TYPE,
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

    def define_config_from_self(self, pool_id):
        config = copy.deepcopy(self.resource_config)

        # Reset options
        filename = config["spec"]["filename"]
        resource_name = config["meta"]["name"]
        postfix = utils_misc.generate_random_string(8)
        config["spec"].update(
            {
                "uri": None,
                "filename": f"{filename}_{postfix}",
                "allocation": 0,
            }
        )
        config["meta"].update(
            {
                "name": f"{resource_name}_{postfix}",
                "pool": pool_id,
                "allocated": False,
                "bindings": dict(),
            }
        )

        return config


class _BlockVolume(_Volume):
    """For disk, lvm, iscsi based volumes"""

    _VOLUME_TYPE = "block"


class _NetworkVolume(_Volume):
    """For rbd, iscsi-direct based volumes"""

    _VOLUME_TYPE = "network"
