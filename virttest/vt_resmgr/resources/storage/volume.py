import os

from virttest import utils_numeric

from ..resource import _Resource


class _Volume(_Resource):
    """
    Storage volumes are abstractions of physical partitions,
    LVM logical volumes, file-based disk images
    """

    _RESOURCE_TYPE = "volume"
    _VOLUME_TYPE = None

    @classmethod
    def volume_type(cls):
        return cls._VOLUME_TYPE

    @classmethod
    def _define_config_legacy(cls, resource_params, node_tags):
        # use a float here for xml-rpc doesn't support big integer
        size = utils_numeric.normalize_data_size(
            resource_params.get("image_size", "20G"), order_magnitude="B"
        )

        config = super()._define_config_legacy(resource_params, node_tags)
        config["meta"].update({
            "type": cls._RESOURCE_TYPE,
            "raw": resource_params.get_boolean("image_raw_device"),
        })
        config["spec"].update({
            "size": size,
            "allocation": None,
        })

        return config


class _FileVolume(_Volume):
    """For file based volumes"""

    _VOLUME_TYPE = "file"

    def __init__(self, resource_config):
        super().__init__(resource_config)
        self._handlers.update({
            "resize": self.resize,
        })

    @classmethod
    def _define_config_legacy(cls, resource_params, node_tags):
        config = super()._define_config_legacy(resource_params, node_tags)

        config["meta"].update({
            "volume-type": cls._VOLUME_TYPE,
        })

        image_name = resource_params.get("image_name", "image")
        if os.path.isabs(image_name):
            config["spec"]["uri"] = image_name
            config["spec"]["filename"] = os.path.basename(image_name)
        else:
            image_format = resource_params.get("image_format", "qcow2")
            config["spec"]["filename"] = "%s.%s" % (image_name, image_format)
            config["spec"]["uri"] =  None

        return config

    def resize(self, arguments):
        raise NotImplemented


class _BlockVolume(_Volume):
    """For disk, lvm, iscsi based volumes"""

    _VOLUME_TYPE = "block"

    @classmethod
    def _define_config_legacy(cls, resource_params, node_tags):
        config = super()._define_config_legacy(resource_params, node_tags)

        config["meta"].update({
            "volume-type": cls._VOLUME_TYPE,
        })
        config["spec"].update({
            "uri": None,
        })

        return config


class _NetworkVolume(_Volume):
    """For rbd, iscsi-direct based volumes"""

    _VOLUME_TYPE = "network"
