import logging

# pylint: disable=E0611
from .images import get_image_handler
from .resource_backing_manager import rb_mgr

LOG = logging.getLogger("avocado.service." + __name__)


class _ImageHandlerManager(object):

    def _get_layer_image_volume_config(self, volume_id):
        """
        Get the layer image volume config.
        Note its pool config is also included, which is used for generating
        the image access auth options.
        """
        backing_id = rb_mgr.query_resource_backing(volume_id)
        volume_config = rb_mgr.get_resource_info_by_backing(backing_id, verbose=True)
        return volume_config

    def _extend_logical_image_volumes_config(self, image_config):
        for config in image_config["spec"]["images"].values():
            volume_id = config["spec"]["volume"]
            config["spec"]["volume"] = self._get_layer_image_volume_config(volume_id)

    def clone_logical_image(self, source_image_config, clone_image_config):
        self._extend_logical_image_volumes_config(source_image_config)
        self._extend_logical_image_volumes_config(clone_image_config)

        r, o = 0, dict()
        try:
            image_type = source_image_config["meta"]["type"]
            clone_func = get_image_handler(image_type, "clone")
            ret = clone_func(source_image_config, clone_image_config)
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug("Failed to clone image: %s", str(e))
        return r, o

    def update_logical_image(self, image_config, cmd, arguments):
        self._extend_logical_image_volumes_config(image_config)

        r, o = 0, dict()
        try:
            image_type = image_config["meta"]["type"]
            handler = get_image_handler(image_type, cmd)
            ret = handler(image_config, arguments)
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug("Failed to update image with cmd %s: %s", cmd, str(e))
        return r, o


image_handler_mgr = _ImageHandlerManager()
