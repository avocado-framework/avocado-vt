import logging

from virttest.utils_numeric import normalize_data_size

from ..resource import _Resource

LOG = logging.getLogger("avocado." + __name__)


class _Volume(_Resource):
    """
    Storage volumes are abstractions of physical partitions,
    LVM logical volumes, file-based disk images
    """

    _RESOURCE_TYPE = "volume"
    _VOLUME_TYPE = None

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        size = normalize_data_size(
            resource_params.get("image_size", "20G"), order_magnitude="B"
        )

        config = super()._define_config_legacy(resource_name, resource_params)
        config["meta"].update(
            {
                "volume-type": cls._VOLUME_TYPE,
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
