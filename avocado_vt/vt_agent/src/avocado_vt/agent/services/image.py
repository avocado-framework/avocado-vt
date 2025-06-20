import logging

from avocado_vt.agent.managers import image_handler_mgr

LOG = logging.getLogger("avocado.service." + __name__)


def handle_image(image_config, config):
    """
    Handle the upper-level image.
    """

    LOG.info(f"Handle image with command: {config}")
    return image_handler_mgr.handle_image(image_config, config)
