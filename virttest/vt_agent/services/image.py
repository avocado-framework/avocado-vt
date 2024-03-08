import logging

from managers import image_handler_mgr

LOG = logging.getLogger("avocado.service." + __name__)


def update_logical_image(logical_image_config, config):
    """
    Update the logical image.
    """

    LOG.info(f"Update the logical image with command: {config}")
    return image_handler_mgr.update_logical_image(logical_image_config, config)
