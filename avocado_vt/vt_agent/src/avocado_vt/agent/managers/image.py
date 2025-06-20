import logging

from avocado_vt.agent.drivers.images import get_image_handler

LOG = logging.getLogger("avocado.service." + __name__)


class ImageHandlerManager(object):
    def __init__(self):
        pass

    def handle_image(self, image_config, config):
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
            LOG.debug("Failed to handle image with cmd %s: %s", cmd, str(e))
        return r, o
