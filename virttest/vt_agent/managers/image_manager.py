import logging

from .images import get_image_handler

LOG = logging.getLogger("avocado.service." + __name__)


class ImageHandlerManager(object):
    def __init__(self):
        pass

    def clone_logical_image(self, image_config):
        r, o = 0, dict()
        try:
            image_type = image_config["meta"]["type"]
            clone_func = get_image_handler(image_type, "clone")
            ret = clone_func(image_config)
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug("Failed to clone image: %s", str(e))
        return r, o

    def update_logical_image(self, image_config, config):
        r, o = 0, dict()
        try:
            cmd, arguments = config.popitem()
            image_type = image_config["meta"]["type"]
            handler = get_image_handler(image_type, cmd)
            ret = handler(image_config, arguments)
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug("Failed to update image with cmd %s: %s", cmd, str(e))
        return r, o
