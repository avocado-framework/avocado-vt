import logging

from managers import image_handler_mgr

LOG = logging.getLogger("avocado.service." + __name__)


def update_image(image_config, config):
    """
    Handle the virtual image.
    """

    LOG.info(f"Update image with command: {config}")
    return image_handler_mgr.update_image(image_config, config)
